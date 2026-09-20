//! Bounded, process-local accounting. Expiry releases an admission charge, never
//! evidence of backend completion. This module neither authenticates provider
//! acknowledgments nor enforces remote/provider-wide capacity.
use std::{
    collections::BTreeMap,
    sync::{
        Arc, Mutex,
        atomic::{AtomicU64, Ordering},
    },
    time::{Duration, Instant},
};

static NEXT_LEDGER: AtomicU64 = AtomicU64::new(0);

/// Opaque identity scoped to one ledger incarnation. Never reused or persisted.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RequestId {
    ledger: u64,
    sequence: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RequestState {
    Active,
    Unconfirmed,
    ExpiredUnconfirmed,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LedgerError {
    InvalidLimits,
    IdentityExhausted,
    AdmissionFull,
    TrackingFull,
    UnknownRequest,
    InvalidTransition,
}

#[derive(Clone, Copy, Debug)]
pub struct LedgerConfig {
    /// Maximum active + unconfirmed charges. Expired uncertainty is excluded.
    pub admission_limit: usize,
    /// Maximum detailed records, including expired uncertainty. Never evicted.
    pub tracking_limit: usize,
    /// Local policy only; not a backend execution-time guarantee. Zero means
    /// immediate reuse while preserving an expired-unconfirmed record.
    pub uncertainty_ttl: Duration,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, serde::Serialize)]
pub struct Snapshot {
    pub active: usize,
    pub unconfirmed: usize,
    pub expired_unconfirmed: usize,
    pub admitted_total: u64,
    pub not_sent_total: u64,
    pub response_received_total: u64,
    pub backend_acknowledged_total: u64,
    pub uncertainty_total: u64,
    pub expiry_total: u64,
}

impl Snapshot {
    pub fn charged(&self) -> usize {
        self.active + self.unconfirmed
    }
    pub fn unresolved(&self) -> usize {
        self.unconfirmed + self.expired_unconfirmed
    }
    pub fn tracked(&self) -> usize {
        self.active + self.unresolved()
    }
}

struct Record {
    state: RequestState,
    dispatched: bool,
    uncertain_since: Option<Instant>,
}
struct Inner {
    records: BTreeMap<u64, Record>,
    totals: Snapshot,
}

pub struct RequestLedger {
    identity: u64,
    config: LedgerConfig,
    inner: Mutex<Inner>,
}

impl RequestLedger {
    pub fn new(config: LedgerConfig) -> Result<Arc<Self>, LedgerError> {
        if config.admission_limit == 0 || config.tracking_limit < config.admission_limit {
            return Err(LedgerError::InvalidLimits);
        }
        let identity = NEXT_LEDGER
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |n| n.checked_add(1))
            .map_err(|_| LedgerError::IdentityExhausted)?;
        Ok(Arc::new(Self {
            identity,
            config,
            inner: Mutex::new(Inner {
                records: BTreeMap::new(),
                totals: Snapshot::default(),
            }),
        }))
    }

    fn expire(&self, inner: &mut Inner, now: Instant) {
        for record in inner.records.values_mut() {
            if record.state == RequestState::Unconfirmed
                && now.saturating_duration_since(
                    record.uncertain_since.expect("uncertainty timestamp"),
                ) >= self.config.uncertainty_ttl
            {
                record.state = RequestState::ExpiredUnconfirmed;
                inner.totals.expiry_total += 1;
            }
        }
    }

    fn counts(inner: &Inner) -> Snapshot {
        let mut s = inner.totals;
        for record in inner.records.values() {
            match record.state {
                RequestState::Active => s.active += 1,
                RequestState::Unconfirmed => s.unconfirmed += 1,
                RequestState::ExpiredUnconfirmed => s.expired_unconfirmed += 1,
            }
        }
        s
    }

    pub fn snapshot(&self) -> Snapshot {
        let mut inner = self.inner.lock().expect("ledger lock poisoned");
        self.expire(&mut inner, Instant::now());
        Self::counts(&inner)
    }

    pub fn state(&self, id: RequestId) -> Result<RequestState, LedgerError> {
        self.check_identity(id)?;
        let mut inner = self.inner.lock().expect("ledger lock poisoned");
        self.expire(&mut inner, Instant::now());
        inner
            .records
            .get(&id.sequence)
            .map(|r| r.state)
            .ok_or(LedgerError::UnknownRequest)
    }

    fn check_identity(&self, id: RequestId) -> Result<(), LedgerError> {
        if id.ledger == self.identity {
            Ok(())
        } else {
            Err(LedgerError::UnknownRequest)
        }
    }

    pub fn try_admit(self: &Arc<Self>) -> Result<Attempt, LedgerError> {
        let mut inner = self.inner.lock().expect("ledger lock poisoned");
        self.expire(&mut inner, Instant::now());
        if inner.records.len() >= self.config.tracking_limit {
            return Err(LedgerError::TrackingFull);
        }
        if Self::counts(&inner).charged() >= self.config.admission_limit {
            return Err(LedgerError::AdmissionFull);
        }
        let sequence = inner.totals.admitted_total;
        let next = sequence
            .checked_add(1)
            .ok_or(LedgerError::IdentityExhausted)?;
        inner.records.insert(
            sequence,
            Record {
                state: RequestState::Active,
                dispatched: false,
                uncertain_since: None,
            },
        );
        inner.totals.admitted_total = next;
        Ok(Attempt {
            ledger: self.clone(),
            id: RequestId {
                ledger: self.identity,
                sequence,
            },
            ended: false,
        })
    }

    /// Caller must supply trustworthy terminal evidence for this exact request.
    /// TypeSafe's reviewed public API provides no such post-disconnect channel.
    /// A timeout, local abort, or accepted cancellation command is not evidence.
    /// Active bodies must finish via their owner, not an out-of-band acknowledgment.
    pub fn acknowledge_backend_completion(&self, id: RequestId) -> Result<(), LedgerError> {
        self.check_identity(id)?;
        let mut inner = self.inner.lock().expect("ledger lock poisoned");
        self.expire(&mut inner, Instant::now());
        let record = inner
            .records
            .get(&id.sequence)
            .ok_or(LedgerError::UnknownRequest)?;
        if record.state == RequestState::Active {
            return Err(LedgerError::InvalidTransition);
        }
        inner.records.remove(&id.sequence);
        inner.totals.backend_acknowledged_total += 1;
        Ok(())
    }

    fn abandon(&self, id: RequestId, now: Instant) {
        let mut inner = self.inner.lock().expect("ledger lock poisoned");
        let record = inner
            .records
            .get_mut(&id.sequence)
            .expect("live attempt record");
        assert_eq!(record.state, RequestState::Active);
        if record.dispatched {
            record.state = RequestState::Unconfirmed;
            record.uncertain_since = Some(now);
            inner.totals.uncertainty_total += 1;
            self.expire(&mut inner, now);
        } else {
            inner.records.remove(&id.sequence);
            inner.totals.not_sent_total += 1;
        }
    }
}

/// Keep this owner through the entire response body and validation. Dropping it
/// before dispatch records not-sent; dropping after dispatch retains uncertainty.
/// Mark dispatch BEFORE handing work to transport, including spawned transports.
#[must_use = "dropping an attempt ends its local lifetime"]
pub struct Attempt {
    ledger: Arc<RequestLedger>,
    id: RequestId,
    ended: bool,
}

impl Attempt {
    pub fn id(&self) -> RequestId {
        self.id
    }

    pub fn mark_dispatched(&mut self) -> Result<(), LedgerError> {
        let mut inner = self.ledger.inner.lock().expect("ledger lock poisoned");
        let record = inner
            .records
            .get_mut(&self.id.sequence)
            .ok_or(LedgerError::UnknownRequest)?;
        if record.dispatched {
            return Err(LedgerError::InvalidTransition);
        }
        record.dispatched = true;
        Ok(())
    }

    /// Only call after the complete response passes the adapter's contract.
    /// Does not assert task success or provider-wide capacity recovery.
    pub fn response_received(mut self) -> Result<(), LedgerError> {
        {
            let mut inner = self.ledger.inner.lock().expect("ledger lock poisoned");
            let record = inner
                .records
                .get(&self.id.sequence)
                .ok_or(LedgerError::UnknownRequest)?;
            if !record.dispatched {
                return Err(LedgerError::InvalidTransition);
            }
            inner.records.remove(&self.id.sequence);
            inner.totals.response_received_total += 1;
            self.ended = true;
        }
        Ok(())
    }
}

impl Drop for Attempt {
    fn drop(&mut self) {
        if !self.ended {
            self.ledger.abandon(self.id, Instant::now());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn ledger(ttl: Duration, tracking: usize) -> Arc<RequestLedger> {
        RequestLedger::new(LedgerConfig {
            admission_limit: 1,
            tracking_limit: tracking,
            uncertainty_ttl: ttl,
        })
        .unwrap()
    }
    fn sent(l: &Arc<RequestLedger>) -> Attempt {
        let mut a = l.try_admit().unwrap();
        a.mark_dispatched().unwrap();
        a
    }
    fn expire_at(l: &RequestLedger, now: Instant) {
        l.expire(&mut l.inner.lock().unwrap(), now);
    }

    #[test]
    fn pre_dispatch_drop_and_valid_response_are_distinct() {
        let l = ledger(Duration::from_secs(60), 2);
        drop(l.try_admit().unwrap());
        sent(&l).response_received().unwrap();
        let s = l.snapshot();
        assert_eq!(
            (
                s.admitted_total,
                s.not_sent_total,
                s.response_received_total,
                s.tracked()
            ),
            (2, 1, 1, 0)
        );
    }

    #[test]
    fn abandonment_holds_charge_until_exact_expiry_without_completion() {
        let l = ledger(Duration::from_secs(60), 2);
        let mut a = sent(&l);
        let id = a.id();
        let now = Instant::now();
        l.abandon(id, now);
        a.ended = true;
        assert_eq!(l.try_admit().err(), Some(LedgerError::AdmissionFull));
        expire_at(&l, now + Duration::from_secs(60) - Duration::from_nanos(1));
        assert_eq!(l.state(id).unwrap(), RequestState::Unconfirmed);
        expire_at(&l, now + Duration::from_secs(60));
        let s = l.snapshot();
        assert_eq!(
            (
                s.charged(),
                s.unresolved(),
                s.expiry_total,
                s.response_received_total
            ),
            (0, 1, 1, 0)
        );
        assert_eq!(l.state(id).unwrap(), RequestState::ExpiredUnconfirmed);
        expire_at(&l, now + Duration::from_secs(120));
        assert_eq!(l.snapshot().expiry_total, 1);
    }

    #[test]
    fn tracking_budget_refuses_admission_without_erasing_expired_records() {
        let l = ledger(Duration::ZERO, 2);
        let a = sent(&l);
        let first = a.id();
        drop(a);
        let a = sent(&l);
        let second = a.id();
        drop(a);
        assert_eq!(l.try_admit().err(), Some(LedgerError::TrackingFull));
        assert_eq!(l.snapshot().expired_unconfirmed, 2);
        l.acknowledge_backend_completion(first).unwrap();
        let replacement = sent(&l);
        assert_eq!(
            l.acknowledge_backend_completion(first),
            Err(LedgerError::UnknownRequest)
        );
        assert_eq!(l.state(replacement.id()).unwrap(), RequestState::Active);
        assert_eq!(l.state(second).unwrap(), RequestState::ExpiredUnconfirmed);
        replacement.response_received().unwrap();
        assert_eq!(l.snapshot().unresolved(), 1);
    }

    #[test]
    fn acknowledgments_are_request_specific_and_cannot_release_active_bodies() {
        let l = ledger(Duration::ZERO, 3);
        let other = ledger(Duration::ZERO, 3);
        let a = sent(&l);
        let id = a.id();
        assert_eq!(
            l.acknowledge_backend_completion(id),
            Err(LedgerError::InvalidTransition)
        );
        let b = sent(&other);
        assert_eq!(
            other.acknowledge_backend_completion(id),
            Err(LedgerError::UnknownRequest)
        );
        assert_eq!(other.state(b.id()).unwrap(), RequestState::Active);
        drop(a);
        l.acknowledge_backend_completion(id).unwrap();
        assert_eq!(l.snapshot().backend_acknowledged_total, 1);
    }

    #[test]
    fn acknowledgment_before_expiry_resolves_only_its_uncertainty() {
        let l = ledger(Duration::from_secs(60), 2);
        let a = sent(&l);
        let id = a.id();
        drop(a);
        assert_eq!(l.state(id).unwrap(), RequestState::Unconfirmed);
        l.acknowledge_backend_completion(id).unwrap();
        let s = l.snapshot();
        assert_eq!((s.unresolved(), s.charged(), s.expiry_total), (0, 0, 0));
        assert_eq!(s.backend_acknowledged_total, 1);
        assert_eq!(s.response_received_total, 0);
        assert!(l.try_admit().is_ok());
    }

    #[test]
    fn invalid_completion_before_dispatch_and_double_dispatch() {
        let l = ledger(Duration::ZERO, 2);
        assert_eq!(
            l.try_admit().unwrap().response_received(),
            Err(LedgerError::InvalidTransition)
        );
        assert_eq!(l.snapshot().not_sent_total, 1);
        let mut a = sent(&l);
        assert_eq!(a.mark_dispatched(), Err(LedgerError::InvalidTransition));
        a.response_received().unwrap();
    }

    #[test]
    fn task_abort_retains_uncertainty() {
        let l = ledger(Duration::ZERO, 2);
        let a = sent(&l);
        let id = a.id();
        let rt = tokio::runtime::Builder::new_current_thread()
            .build()
            .unwrap();
        rt.block_on(async {
            let (tx, rx) = tokio::sync::oneshot::channel();
            let task = tokio::spawn(async move {
                let _owner = a;
                tx.send(()).unwrap();
                std::future::pending::<()>().await;
            });
            rx.await.unwrap();
            task.abort();
            assert!(task.await.unwrap_err().is_cancelled());
        });
        assert_eq!(l.state(id).unwrap(), RequestState::ExpiredUnconfirmed);
        assert_eq!(l.snapshot().uncertainty_total, 1);
    }

    #[test]
    fn concurrent_admission_is_atomic_and_conserves_records() {
        let l = RequestLedger::new(LedgerConfig {
            admission_limit: 4,
            tracking_limit: 8,
            uncertainty_ttl: Duration::ZERO,
        })
        .unwrap();
        let start = Arc::new(std::sync::Barrier::new(33));
        let hold = Arc::new(std::sync::Barrier::new(33));
        let mut tasks = Vec::new();
        for _ in 0..32 {
            let (l, start, hold) = (l.clone(), start.clone(), hold.clone());
            tasks.push(std::thread::spawn(move || {
                start.wait();
                let a = l.try_admit();
                hold.wait();
                a
            }));
        }
        start.wait();
        hold.wait();
        let mut owners = Vec::new();
        for task in tasks {
            if let Ok(a) = task.join().unwrap() {
                owners.push(a);
            }
        }
        assert_eq!(owners.len(), 4);
        assert_eq!(l.snapshot().active, 4);
        for mut a in owners {
            a.mark_dispatched().unwrap();
            drop(a);
        }
        let s = l.snapshot();
        assert_eq!(
            (s.active, s.expired_unconfirmed, s.admitted_total),
            (0, 4, 4)
        );
        assert_eq!(
            s.admitted_total,
            s.not_sent_total
                + s.response_received_total
                + s.backend_acknowledged_total
                + s.tracked() as u64
        );
    }

    #[test]
    fn invalid_limits_and_identity_exhaustion_do_not_mutate_records() {
        assert!(matches!(
            RequestLedger::new(LedgerConfig {
                admission_limit: 2,
                tracking_limit: 1,
                uncertainty_ttl: Duration::ZERO
            }),
            Err(LedgerError::InvalidLimits)
        ));
        let l = ledger(Duration::ZERO, 2);
        l.inner.lock().unwrap().totals.admitted_total = u64::MAX;
        assert_eq!(l.try_admit().err(), Some(LedgerError::IdentityExhausted));
        assert_eq!(l.snapshot().tracked(), 0);
    }
}
