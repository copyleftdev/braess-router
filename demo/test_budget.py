from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import tempfile
import unittest
from budget import Budget, BudgetError, usd_units

PRICE = 'a'*64
REQUEST = 'b'*64
RECEIPT = 'c'*64


def reserve_process(args):
    path, attempt = args
    ledger = Budget(path, pricing_sha256=PRICE)
    try:
        ledger.reserve(str(attempt), request_sha256=REQUEST, estimate_usd='0.01')
        return True
    except BudgetError:
        return False


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'budget'
        self.budget = Budget.create(self.path, cap_usd='0.05', max_attempts=10, pricing_sha256=PRICE)

    def test_concurrent_processes_cannot_oversubscribe(self):
        with ProcessPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(reserve_process, [(self.path, n) for n in range(20)]))
        self.assertEqual(sum(results), 5)
        self.assertEqual(self.budget.inspect()['accounted_usd'], '0.05')

    def test_restart_retains_unknown_charge(self):
        self.budget.reserve('one', request_sha256=REQUEST, estimate_usd='0.05')
        reopened = Budget(self.path, pricing_sha256=PRICE)
        self.assertEqual(reopened.inspect()['unresolved'], 1)
        with self.assertRaises(BudgetError):
            reopened.reserve('two', request_sha256=REQUEST, estimate_usd='0.000000001')

    def test_forced_process_exit_after_reservation_retains_charge(self):
        import subprocess
        import sys
        source = "from budget import Budget; import os,sys; b=Budget(sys.argv[1],pricing_sha256='a'*64); b.reserve('crashed',request_sha256='b'*64,estimate_usd='0.05'); os._exit(23)"
        result = subprocess.run([sys.executable, '-c', source, str(self.path)],
                                cwd=Path(__file__).resolve().parent, timeout=10, capture_output=True)
        self.assertEqual(result.returncode, 23)
        state = Budget(self.path, pricing_sha256=PRICE).inspect()
        self.assertEqual(state['available_usd'], '0')
        self.assertEqual(state['pending'][0]['attempt_id'], 'crashed')

    def test_duplicate_id_never_authorizes_another_dispatch(self):
        self.budget.reserve('one', request_sha256=REQUEST, estimate_usd='0.01')
        with self.assertRaises(BudgetError):
            self.budget.reserve('one', request_sha256=REQUEST, estimate_usd='0.01')
        self.assertEqual(self.budget.inspect()['attempts'], 1)

    def test_receipt_releases_only_unused_estimate_and_is_idempotent(self):
        self.budget.reserve('one', request_sha256=REQUEST, estimate_usd='0.05')
        for _ in range(2):
            self.budget.settle('one', receipt_sha256=RECEIPT, actual_usd='0.012345678')
        state = self.budget.inspect()
        self.assertEqual(state['available_usd'], '0.037654322')
        self.assertEqual(state['unresolved'], 0)
        with self.assertRaises(BudgetError):
            self.budget.settle('one', receipt_sha256=RECEIPT, actual_usd='0')

    def test_underestimate_is_recorded_and_freezes_further_admission(self):
        self.budget.reserve('one', request_sha256=REQUEST, estimate_usd='0.01')
        self.budget.settle('one', receipt_sha256=RECEIPT, actual_usd='0.07')
        state = self.budget.inspect()
        self.assertTrue(state['frozen'])
        self.assertEqual(state['over_cap_usd'], '0.02')
        with self.assertRaises(BudgetError):
            self.budget.reserve('two', request_sha256=REQUEST, estimate_usd='0.01')
        self.assertTrue(Budget(self.path, pricing_sha256=PRICE).inspect()['frozen'])

    def test_precision_and_nonfinite_amounts(self):
        self.assertEqual(usd_units('0.0000000001'), 1)
        self.assertEqual(usd_units('0.0000000010000000000000000000000000001'), 2)
        self.assertEqual(usd_units('1e-1000000000'), 1)
        for value in [0.1, 'NaN', 'Infinity', '-1', '1e9999', 'invalid']:
            with self.assertRaises(BudgetError):
                usd_units(value)

    def test_missing_or_mismatched_state_refused(self):
        with self.assertRaises(BudgetError):
            Budget(self.path, pricing_sha256='d'*64)
        with self.assertRaises(BudgetError):
            Budget(self.path.parent/'absent', pricing_sha256=PRICE)
        with self.assertRaises(FileExistsError):
            Budget.create(self.path, cap_usd='0.05', max_attempts=10, pricing_sha256=PRICE)

    def test_attempt_cap_never_refunded(self):
        for n in range(10):
            self.budget.reserve(str(n), request_sha256=REQUEST, estimate_usd='0.001')
            self.budget.settle(str(n), receipt_sha256=RECEIPT, actual_usd='0')
        with self.assertRaises(BudgetError):
            self.budget.reserve('extra', request_sha256=REQUEST, estimate_usd='0.001')


if __name__ == '__main__':
    unittest.main()
