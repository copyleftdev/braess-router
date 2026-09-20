//! Process-local dispatch authorization, not wire-arrival or cluster-wide quota.
//! Outstanding reservations never expire. A committed reservation is charged
//! from its commit time, immediately before the caller hands work to transport.
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::VecDeque,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RateConfig {
    pub max_requests: usize,
    pub window_ms: u64,
}
impl RateConfig {
    pub fn validate(&self) -> Result<(), String> {
        if !(1..=100_000).contains(&self.max_requests) || !(1..=60_000).contains(&self.window_ms) {
            return Err("invalid local dispatch rate limits".into());
        }
        Ok(())
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RateError {
    Limited { retry_after_ms: Option<u64> },
    Unavailable,
}

struct State {
    pending: usize,
    started: VecDeque<Instant>,
}
pub struct RateLimiter {
    config: RateConfig,
    window: Duration,
    initialized: Instant,
    state: Mutex<State>,
}
#[must_use = "dropping an uncommitted rate lease releases its reservation"]
pub struct RateLease {
    limiter: Arc<RateLimiter>,
    committed: bool,
}
impl RateLimiter {
    /// A full-window startup cooldown prevents immediate quota reuse on restart.
    pub fn new(config: RateConfig) -> Result<Arc<Self>, String> {
        Self::new_at(config, Instant::now())
    }
    fn new_at(config: RateConfig, initialized: Instant) -> Result<Arc<Self>, String> {
        config.validate()?;
        Ok(Arc::new(Self {
            config,
            window: Duration::from_millis(config.window_ms),
            initialized,
            state: Mutex::new(State {
                pending: 0,
                started: VecDeque::with_capacity(config.max_requests),
            }),
        }))
    }
    fn expire(&self, state: &mut State, now: Instant) {
        while state
            .started
            .front()
            .is_some_and(|start| now.saturating_duration_since(*start) >= self.window)
        {
            state.started.pop_front();
        }
    }
    /// Atomically reserves pending + committed capacity. Caller must commit only
    /// immediately before dispatch; dropping before commit releases capacity.
    pub fn try_reserve(self: &Arc<Self>) -> Result<RateLease, RateError> {
        self.reserve_with_clock(Instant::now)
    }
    fn reserve_with_clock(
        self: &Arc<Self>,
        clock: impl FnOnce() -> Instant,
    ) -> Result<RateLease, RateError> {
        let mut state = self.state.lock().map_err(|_| RateError::Unavailable)?;
        let now = clock();
        self.expire(&mut state, now);
        if now.saturating_duration_since(self.initialized) < self.window
            || state.pending + state.started.len() >= self.config.max_requests
        {
            return Err(RateError::Limited {
                retry_after_ms: self.retry_after(&state, now),
            });
        }
        state.pending += 1;
        Ok(RateLease {
            limiter: self.clone(),
            committed: false,
        })
    }
    fn retry_after(&self, state: &State, now: Instant) -> Option<u64> {
        let elapsed = now.saturating_duration_since(self.initialized);
        let duration = if elapsed < self.window {
            Some(self.window.saturating_sub(elapsed))
        } else if state.pending + state.started.len() >= self.config.max_requests {
            state.started.front().map(|start| {
                self.window
                    .saturating_sub(now.saturating_duration_since(*start))
            })
        } else {
            None
        };
        duration.map(|duration| {
            duration.as_millis() as u64 + u64::from(duration.subsec_nanos() % 1_000_000 != 0)
        })
    }
    pub fn snapshot(&self) -> Value {
        self.snapshot_with_clock(Instant::now)
    }
    fn snapshot_with_clock(&self, clock: impl FnOnce() -> Instant) -> Value {
        let Ok(mut state) = self.state.lock() else {
            return json!({"healthy":false,"max_requests":self.config.max_requests,"window_ms":self.config.window_ms,"remaining":0,"cooling":false,"retry_after_ms":null});
        };
        let now = clock();
        self.expire(&mut state, now);
        let startup_elapsed = now.saturating_duration_since(self.initialized);
        let cooling = startup_elapsed < self.window;
        let remaining = if cooling {
            0
        } else {
            self.config
                .max_requests
                .saturating_sub(state.pending + state.started.len())
        };
        let retry_ms = self.retry_after(&state, now);
        json!({"healthy":true,"max_requests":self.config.max_requests,"window_ms":self.config.window_ms,"pending":state.pending,"started":state.started.len(),"remaining":remaining,"cooling":cooling,"retry_after_ms":retry_ms})
    }
}
impl RateLease {
    /// This marks local authorization, not proof that a remote server received
    /// the request. Failed sends remain charged for the entire sliding window.
    pub fn commit(self) -> Result<(), RateError> {
        self.commit_with_clock(Instant::now)
    }
    fn commit_with_clock(mut self, clock: impl FnOnce() -> Instant) -> Result<(), RateError> {
        {
            let mut state = self
                .limiter
                .state
                .lock()
                .map_err(|_| RateError::Unavailable)?;
            let now = clock();
            self.limiter.expire(&mut state, now);
            // This lease already owns a slot; it never expires while pending.
            state.pending = state.pending.checked_sub(1).ok_or(RateError::Unavailable)?;
            state.started.push_back(now);
            self.committed = true;
        }
        Ok(())
    }
}
impl Drop for RateLease {
    fn drop(&mut self) {
        if !self.committed
            && let Ok(mut state) = self.limiter.state.lock()
        {
            state.pending = state.pending.saturating_sub(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn limiter(max: usize) -> (Arc<RateLimiter>, Instant) {
        let now = Instant::now();
        (
            RateLimiter::new_at(
                RateConfig {
                    max_requests: max,
                    window_ms: 100,
                },
                now,
            )
            .unwrap(),
            now,
        )
    }
    #[test]
    fn retry_hint_is_rounded_up_and_absent_for_pending_only_capacity() {
        let (limiter, now) = limiter(1);
        let almost = now + Duration::from_millis(100) - Duration::from_nanos(1);
        assert_eq!(
            limiter.reserve_with_clock(|| almost).err(),
            Some(RateError::Limited {
                retry_after_ms: Some(1)
            })
        );
        let lease = limiter
            .reserve_with_clock(|| now + Duration::from_millis(100))
            .unwrap();
        assert_eq!(
            limiter
                .reserve_with_clock(|| now + Duration::from_millis(101))
                .err(),
            Some(RateError::Limited {
                retry_after_ms: None
            })
        );
        lease
            .commit_with_clock(|| now + Duration::from_millis(200))
            .unwrap();
        assert_eq!(
            limiter
                .reserve_with_clock(|| now + Duration::from_millis(300) - Duration::from_nanos(1))
                .err(),
            Some(RateError::Limited {
                retry_after_ms: Some(1)
            })
        );
    }
    #[test]
    fn poisoned_owner_reports_unavailable_instead_of_quota_exhaustion() {
        let (limiter, now) = limiter(1);
        let lease = limiter
            .reserve_with_clock(|| now + Duration::from_millis(100))
            .unwrap();
        let poisoned = limiter.clone();
        assert!(
            std::thread::spawn(move || {
                let _guard = poisoned.state.lock().unwrap();
                panic!("injected owner failure");
            })
            .join()
            .is_err()
        );
        assert_eq!(limiter.try_reserve().err(), Some(RateError::Unavailable));
        assert_eq!(lease.commit(), Err(RateError::Unavailable));
        assert_eq!(limiter.snapshot()["healthy"], false);
    }
    #[test]
    fn config_and_startup_window_fail_closed_at_exact_boundary() {
        for config in [
            RateConfig {
                max_requests: 0,
                window_ms: 1,
            },
            RateConfig {
                max_requests: 100001,
                window_ms: 1,
            },
            RateConfig {
                max_requests: 1,
                window_ms: 0,
            },
            RateConfig {
                max_requests: 1,
                window_ms: 60001,
            },
        ] {
            assert!(RateLimiter::new(config).is_err());
        }
        assert!(
            serde_json::from_value::<RateConfig>(
                json!({"max_requests":1,"window_ms":100,"extra":true})
            )
            .is_err()
        );
        let (limiter, now) = limiter(1);
        assert!(
            limiter
                .reserve_with_clock(|| now + Duration::from_millis(100) - Duration::from_nanos(1))
                .is_err()
        );
        let lease = limiter
            .reserve_with_clock(|| now + Duration::from_millis(100))
            .unwrap();
        let status = limiter.snapshot_with_clock(|| now + Duration::from_millis(100));
        assert_eq!(status["cooling"], false);
        assert_eq!(status["remaining"], 0);
        assert_eq!(status["retry_after_ms"], Value::Null);
        drop(lease);
    }
    #[test]
    fn held_leases_survive_multiple_windows_and_cancellation_releases() {
        let (limiter, now) = limiter(1);
        let lease = limiter
            .reserve_with_clock(|| now + Duration::from_millis(100))
            .unwrap();
        assert!(
            limiter
                .reserve_with_clock(|| now + Duration::from_secs(60))
                .is_err()
        );
        assert_eq!(
            limiter.snapshot_with_clock(|| now + Duration::from_secs(60))["pending"],
            1
        );
        drop(lease);
        assert!(
            limiter
                .reserve_with_clock(|| now + Duration::from_secs(60))
                .is_ok()
        );
    }
    #[test]
    fn commit_window_starts_at_dispatch_authorization_not_reservation() {
        let (limiter, now) = limiter(1);
        let lease = limiter
            .reserve_with_clock(|| now + Duration::from_millis(100))
            .unwrap();
        lease
            .commit_with_clock(|| now + Duration::from_millis(500))
            .unwrap();
        let just_before = now + Duration::from_millis(600) - Duration::from_nanos(1);
        assert!(limiter.reserve_with_clock(|| just_before).is_err());
        assert_eq!(
            limiter.snapshot_with_clock(|| just_before)["retry_after_ms"],
            1
        );
        assert!(
            limiter
                .reserve_with_clock(|| now + Duration::from_millis(600))
                .is_ok()
        );
    }
    #[test]
    fn committed_and_pending_slots_share_one_atomic_limit() {
        let (limiter, now) = limiter(2);
        let t = now + Duration::from_millis(100);
        let first = limiter.reserve_with_clock(|| t).unwrap();
        let second = limiter.reserve_with_clock(|| t).unwrap();
        first.commit_with_clock(|| t).unwrap();
        assert!(limiter.reserve_with_clock(|| t).is_err());
        let state = limiter.snapshot_with_clock(|| t);
        assert_eq!(state["pending"], 1);
        assert_eq!(state["started"], 1);
        drop(second);
        assert!(limiter.reserve_with_clock(|| t).is_ok());
        assert_eq!(limiter.snapshot_with_clock(|| t)["started"], 1);
    }
    #[test]
    fn concurrent_reservations_and_commits_respect_maximum() {
        let (limiter, now) = limiter(4);
        let at = now + Duration::from_millis(100);
        let start = Arc::new(std::sync::Barrier::new(33));
        let hold = Arc::new(std::sync::Barrier::new(33));
        let workers: Vec<_> = (0..32)
            .map(|_| {
                let (limiter, start, hold) = (limiter.clone(), start.clone(), hold.clone());
                std::thread::spawn(move || {
                    start.wait();
                    let lease = limiter.reserve_with_clock(|| at);
                    hold.wait();
                    lease
                        .map(|lease| lease.commit_with_clock(|| at).unwrap())
                        .is_ok()
                })
            })
            .collect();
        start.wait();
        hold.wait();
        assert_eq!(
            workers
                .into_iter()
                .filter_map(|w| w.join().ok())
                .filter(|accepted| *accepted)
                .count(),
            4
        );
        assert_eq!(limiter.snapshot_with_clock(|| at)["started"], 4);
        assert!(limiter.reserve_with_clock(|| at).is_err());
    }
    #[test]
    fn snapshot_before_initialization_time_is_safe_and_rounds_up() {
        let (limiter, now) = limiter(1);
        let status = limiter.snapshot_with_clock(|| now - Duration::from_secs(1));
        assert_eq!(status["cooling"], true);
        assert_eq!(status["retry_after_ms"], 100);
    }
}
