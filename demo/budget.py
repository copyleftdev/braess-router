"""Shared durable run budget. Integer nanodollars; unknown attempts stay reserved.

This enforces admission against configured estimates, not a provider invoice cap.
The caller must derive conservative estimates from a pinned pricing manifest.
"""
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_CEILING, localcontext
import os
from pathlib import Path
import re
import sqlite3

SCALE = 1_000_000_000
ID = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}\Z')
HASH = re.compile(r'[0-9a-f]{64}\Z')


class BudgetError(ValueError):
    pass


def usd_units(value):
    """Round estimates upward; never use binary floating-point money."""
    if not isinstance(value, str) or len(value) > 64:
        raise BudgetError('USD amount must be a decimal string')
    try:
        number = Decimal(value)
        if not number.is_finite() or number < 0 or number > 1_000_000:
            raise BudgetError('USD amount outside bounds')
        if number != 0 and number.adjusted() < -80:
            return 1
        with localcontext() as context:
            context.prec = 80
            return int((number * SCALE).to_integral_value(rounding=ROUND_CEILING))
    except (InvalidOperation, OverflowError) as error:
        raise BudgetError('invalid USD amount') from error


def usd_string(units):
    return format(Decimal(units) / SCALE, 'f')


def valid_id(value):
    return isinstance(value, str) and ID.fullmatch(value) is not None


def valid_hash(value):
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Budget:
    @classmethod
    def create(cls, directory, *, cap_usd, max_attempts, pricing_sha256):
        cap = usd_units(cap_usd)
        if cap <= 0 or type(max_attempts) is not int or not 1 <= max_attempts <= 100_000 or not valid_hash(pricing_sha256):
            raise BudgetError('invalid budget policy')
        directory = Path(directory)
        # Parent must already exist: no implicit creation of an entire durable hierarchy.
        directory.mkdir(mode=0o700, exist_ok=False)
        fd = os.open(directory/'budget.sqlite', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        db = sqlite3.connect(directory/'budget.sqlite', isolation_level=None)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE policy (
                  id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL,
                  cap INTEGER NOT NULL CHECK(cap>0), max_attempts INTEGER NOT NULL,
                  pricing_sha256 TEXT NOT NULL, frozen INTEGER NOT NULL CHECK(frozen IN (0,1)));
                CREATE TABLE attempts (
                  attempt_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,
                  reserved INTEGER NOT NULL CHECK(reserved>0),
                  charged INTEGER CHECK(charged>=0), receipt_sha256 TEXT,
                  CHECK((charged IS NULL) = (receipt_sha256 IS NULL)));
            ''')
            db.execute('INSERT INTO policy VALUES (1,1,?,?,?,0)', (cap, max_attempts, pricing_sha256))
            db.execute('COMMIT')
        finally:
            db.close()
        sync_dir(directory)
        sync_dir(directory.parent)
        return cls(directory, pricing_sha256=pricing_sha256)

    def __init__(self, directory, *, pricing_sha256):
        self.path = Path(directory)/'budget.sqlite'
        if not valid_hash(pricing_sha256) or self.path.is_symlink() or not self.path.is_file():
            raise BudgetError('existing regular budget required')
        self.pricing = pricing_sha256
        with self._transaction() as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise BudgetError('invalid budget database')
            self._policy(db)

    @contextmanager
    def _transaction(self):
        # rw refuses to silently create a missing state file on reopen.
        db = sqlite3.connect(self.path.resolve().as_uri()+'?mode=rw', uri=True, isolation_level=None, timeout=5)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def _policy(self, db):
        row = db.execute('SELECT version,cap,max_attempts,pricing_sha256,frozen FROM policy WHERE id=1').fetchone()
        if row is None or row[0] != 1 or row[3] != self.pricing:
            raise BudgetError('budget policy mismatch')
        return row

    @staticmethod
    def _totals(db):
        count = committed = unresolved = 0
        for reserved, charged in db.execute('SELECT reserved,charged FROM attempts'):
            count += 1
            committed += reserved if charged is None else charged
            unresolved += charged is None
        return count, committed, unresolved

    def reserve(self, attempt_id, *, request_sha256, estimate_usd):
        estimate = usd_units(estimate_usd)
        if not valid_id(attempt_id) or not valid_hash(request_sha256) or estimate <= 0:
            raise BudgetError('invalid reservation')
        with self._transaction() as db:
            _, cap, limit, _, frozen = self._policy(db)
            if db.execute('SELECT 1 FROM attempts WHERE attempt_id=?', (attempt_id,)).fetchone():
                # Never return dispatch permission for an already-reserved request.
                raise BudgetError('attempt already reserved; dispatch prohibited')
            count, committed, _ = self._totals(db)
            if frozen:
                raise BudgetError('budget frozen after estimate overrun')
            if count >= limit:
                raise BudgetError('attempt limit exhausted')
            if committed + estimate > cap:
                raise BudgetError('insufficient unreserved budget')
            db.execute('INSERT INTO attempts VALUES (?,?,?,NULL,NULL)', (attempt_id, request_sha256, estimate))
        return {'attempt_id': attempt_id, 'reserved_usd': usd_string(estimate)}

    def settle(self, attempt_id, *, receipt_sha256, actual_usd):
        actual = usd_units(actual_usd)
        if not valid_id(attempt_id) or not valid_hash(receipt_sha256):
            raise BudgetError('invalid completion receipt')
        with self._transaction() as db:
            self._policy(db)
            row = db.execute('SELECT reserved,charged,receipt_sha256 FROM attempts WHERE attempt_id=?', (attempt_id,)).fetchone()
            if row is None:
                raise BudgetError('unreserved attempt')
            reserved, charged, receipt = row
            if receipt is not None:
                if receipt != receipt_sha256 or charged != actual:
                    raise BudgetError('conflicting completion receipt')
                return  # Replay of exactly the same receipt is idempotent.
            db.execute('UPDATE attempts SET charged=?,receipt_sha256=? WHERE attempt_id=?', (actual, receipt_sha256, attempt_id))
            if actual > reserved:
                # Persist the real overrun; never hide it by rejecting the receipt.
                db.execute('UPDATE policy SET frozen=1 WHERE id=1')

    def inspect(self):
        with self._transaction() as db:
            _, cap, limit, pricing, frozen = self._policy(db)
            count, committed, unresolved = self._totals(db)
            charged = sum(row[0] for row in db.execute('SELECT charged FROM attempts WHERE charged IS NOT NULL'))
            pending = db.execute('SELECT attempt_id,reserved FROM attempts WHERE charged IS NULL ORDER BY attempt_id').fetchall()
            return {'cap_usd': usd_string(cap), 'accounted_usd': usd_string(committed),
                    'reported_charge_usd': usd_string(charged),
                    'available_usd': usd_string(max(0, cap-committed)),
                    'over_cap_usd': usd_string(max(0, committed-cap)), 'frozen': bool(frozen),
                    'attempts': count, 'max_attempts': limit, 'unresolved': unresolved or 0,
                    'pricing_sha256': pricing,
                    'pending': [{'attempt_id': key, 'reserved_usd': usd_string(value)} for key, value in pending]}
