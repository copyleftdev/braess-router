//! Deterministic discrete-event experiment; not a production service model.
use poise_core::{
    Backend, Policy, Status,
    policy::{LeastLoaded, PowerOfTwoChoices, RoundRobin},
};
use rand::{RngExt, SeedableRng, rngs::StdRng};
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;

pub const POLICIES: [&str; 3] = ["round_robin", "least_inflight", "p2c_inflight"];

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub version: String,
    pub requests_per_run: usize,
    pub seeds: Vec<u64>,
    pub deadline_us: u64,
    pub capacity_per_backend: usize,
    pub scenarios: Vec<Scenario>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub latency: Option<LatencyConfig>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub admission: Option<AdmissionConfig>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AdmissionConfig {
    pub limits: Vec<usize>,
    pub selectors: Vec<String>,
    pub primary_limit: usize,
    pub reference_limit: usize,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LatencyConfig {
    pub default_rtt_us: u64,
    pub half_lives_us: Vec<u64>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Scenario {
    pub name: String,
    pub service_us: Vec<u64>,
    pub arrival_gap_us: u64,
    pub burst_gap_us: Option<u64>,
    pub clients: usize,
    pub observation_refresh_us: u64,
    pub slowdown_at_us: Option<u64>,
}

impl Config {
    fn base_policies(&self) -> Vec<String> {
        let mut names: Vec<_> = POLICIES.iter().map(|s| s.to_string()).collect();
        if let Some(latency) = &self.latency {
            for half in &latency.half_lives_us {
                names.push(format!("least_peak_{half}"));
                names.push(format!("p2c_peak_{half}"));
            }
        }
        names
    }

    pub fn policies(&self) -> Vec<String> {
        if let Some(admission) = &self.admission {
            admission
                .selectors
                .iter()
                .flat_map(|selector| {
                    admission
                        .limits
                        .iter()
                        .map(move |limit| format!("{selector}__cap_{limit}"))
                })
                .collect()
        } else {
            self.base_policies()
        }
    }

    pub fn validate(&self) -> Result<(), String> {
        if let Some(admission) = &self.admission {
            let limits: std::collections::BTreeSet<_> = admission.limits.iter().collect();
            let selectors: std::collections::BTreeSet<_> = admission.selectors.iter().collect();
            let allowed = self.base_policies();
            if !(1..=16).contains(&admission.limits.len())
                || !(1..=16).contains(&admission.selectors.len())
                || limits.len() != admission.limits.len()
                || selectors.len() != admission.selectors.len()
                || !admission
                    .limits
                    .iter()
                    .all(|n| (1..=self.capacity_per_backend).contains(n))
                || !admission.selectors.iter().all(|s| allowed.contains(s))
                || !admission.limits.contains(&admission.primary_limit)
                || !admission.limits.contains(&admission.reference_limit)
                || admission.reference_limit != self.capacity_per_backend
            {
                return Err("Invalid admission configuration".into());
            }
        }
        if let Some(l) = &self.latency {
            let unique: std::collections::BTreeSet<_> = l.half_lives_us.iter().collect();
            if !(1..=60_000_000).contains(&l.default_rtt_us)
                || !(1..=8).contains(&l.half_lives_us.len())
                || unique.len() != l.half_lives_us.len()
                || !l.half_lives_us.iter().all(|h| (1..=60_000_000).contains(h))
            {
                return Err("Invalid latency estimator configuration".into());
            }
        }
        if self.version.is_empty()
            || !(1..=100_000).contains(&self.requests_per_run)
            || !(1..=64).contains(&self.seeds.len())
            || !(1..=20).contains(&self.scenarios.len())
            || !(1..=1024).contains(&self.capacity_per_backend)
            || !(1..=60_000_000).contains(&self.deadline_us)
        {
            return Err("Invalid or unbounded experiment configuration".into());
        }
        let mut names = std::collections::BTreeSet::new();
        let unique_seeds: std::collections::BTreeSet<_> = self.seeds.iter().collect();
        if unique_seeds.len() != self.seeds.len() {
            return Err("Duplicate seeds".into());
        }
        for s in &self.scenarios {
            if s.name.is_empty()
                || !s
                    .name
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'_')
                || !names.insert(&s.name)
                || !(1..=128).contains(&s.service_us.len())
                || !s.service_us.iter().all(|t| (1..=60_000_000).contains(t))
                || !(1..=60_000_000).contains(&s.arrival_gap_us)
                || s.burst_gap_us
                    .is_some_and(|t| !(1..=60_000_000).contains(&t))
                || !(1..=64).contains(&s.clients)
                || s.observation_refresh_us > 60_000_000
            {
                return Err("Invalid scenario".into());
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Request {
    pub id: usize,
    pub arrival_us: u64,
    pub work_per_thousand: u64,
    pub client: usize,
}

pub fn workload(config: &Config, scenario: &Scenario, seed: u64) -> Vec<Request> {
    let mut rng = StdRng::seed_from_u64(seed);
    let mut now = 0;
    (0..config.requests_per_run)
        .map(|id| {
            let burst =
                (config.requests_per_run / 3..2 * config.requests_per_run / 3).contains(&id);
            let gap = if burst {
                scenario.burst_gap_us.unwrap_or(scenario.arrival_gap_us)
            } else {
                scenario.arrival_gap_us
            };
            now += rng.random_range(1..=gap * 2);
            Request {
                id,
                arrival_us: now,
                work_per_thousand: rng.random_range(500..=1500),
                client: id % scenario.clients,
            }
        })
        .collect()
}

enum Selector {
    RoundRobin(RoundRobin),
    Least(LeastLoaded),
    P2c(Box<PowerOfTwoChoices>),
}

impl Selector {
    fn new(name: &str, seed: u64) -> Self {
        match name {
            "round_robin" => Self::RoundRobin(RoundRobin::new()),
            "least_inflight" => Self::Least(LeastLoaded::new()),
            "p2c_inflight" => Self::P2c(Box::new(PowerOfTwoChoices::seeded(seed))),
            name if name.starts_with("least_peak_") => Self::Least(LeastLoaded::new()),
            name if name.starts_with("p2c_peak_") => {
                Self::P2c(Box::new(PowerOfTwoChoices::seeded(seed)))
            }
            _ => panic!("unknown policy"),
        }
    }
    fn pick(&mut self, candidates: &[Backend<usize, (), u64>]) -> Option<usize> {
        let result = match self {
            Self::RoundRobin(p) => p.pick(candidates, &()),
            Self::Least(p) => p.pick(candidates, &()),
            Self::P2c(p) => p.pick(candidates, &()),
        };
        result.ok().map(|s| s.index())
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Outcome {
    pub id: usize,
    pub backend: Option<usize>,
    pub status: &'static str,
    pub start_us: Option<u64>,
    pub finish_us: Option<u64>,
    pub occupancy_after: usize,
    pub selected_score: Option<u64>,
}

/// Clock-adapted arithmetic only: does not run Poise's real Instant-based tracker.
#[derive(Clone)]
struct SimulatedPeak {
    cost_us: f64,
    updated_us: u64,
    floor_us: f64,
    half_life_us: f64,
}

impl SimulatedPeak {
    fn new(floor_us: u64, half_life_us: u64) -> Self {
        Self {
            cost_us: floor_us as f64,
            updated_us: 0,
            floor_us: floor_us as f64,
            half_life_us: half_life_us as f64,
        }
    }
    fn advance(&mut self, now_us: u64) -> f64 {
        assert!(now_us >= self.updated_us);
        self.cost_us = (self.cost_us
            * (-((now_us - self.updated_us) as f64) / self.half_life_us).exp2())
        .max(self.floor_us);
        self.updated_us = now_us;
        self.cost_us
    }
    fn observe(&mut self, finish_us: u64, response_us: u64) {
        self.cost_us = self.advance(finish_us).max(response_us as f64);
    }
    fn score(&mut self, now_us: u64, observed_inflight: usize) -> u64 {
        (self.advance(now_us) * (observed_inflight as f64 + 1.0) * 1000.0).round() as u64
    }
}

#[derive(Clone)]
struct Pending {
    finish_us: u64,
    arrival_us: u64,
    client: usize,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Summary {
    pub scenario: String,
    pub seed: u64,
    pub policy: String,
    pub offered: usize,
    pub accepted: usize,
    pub rejected: usize,
    pub late: usize,
    pub within_deadline: usize,
    pub deadline_success: f64,
    pub within_deadline_per_offered_second: f64,
    pub latency_p50_us: Option<u64>,
    pub latency_p95_us: Option<u64>,
    pub latency_p99_us: Option<u64>,
    pub queue_p95_us: Option<u64>,
    pub max_backend_occupancy: usize,
    pub accepted_per_backend: Vec<usize>,
    pub drain_finish_us: u64,
}

fn percentile(values: &mut [u64], p: usize) -> Option<u64> {
    if values.is_empty() {
        return None;
    }
    values.sort_unstable();
    Some(values[(values.len() * p).div_ceil(100) - 1])
}

pub fn run(
    config: &Config,
    scenario: &Scenario,
    seed: u64,
    policy: &str,
    trace: &[Request],
) -> (Vec<Outcome>, Summary) {
    let (selector_name, admission_limit) = policy
        .split_once("__cap_")
        .map(|(name, limit)| {
            (
                name,
                limit.parse::<usize>().expect("validated admission limit"),
            )
        })
        .unwrap_or((policy, config.capacity_per_backend));
    assert!((1..=config.capacity_per_backend).contains(&admission_limit));
    let count = scenario.service_us.len();
    let mut queues: Vec<VecDeque<Pending>> = vec![VecDeque::new(); count];
    let half_life = selector_name
        .split_once("_peak_")
        .map(|(_, n)| n.parse::<u64>().expect("validated policy"));
    let mut estimators = half_life.map(|half| {
        vec![
            vec![
                SimulatedPeak::new(
                    config
                        .latency
                        .as_ref()
                        .expect("latency config")
                        .default_rtt_us,
                    half
                );
                count
            ];
            scenario.clients
        ]
    });
    let mut selectors: Vec<_> = (0..scenario.clients)
        .map(|i| Selector::new(selector_name, seed ^ 0xd1b54a32d192ed03 ^ i as u64))
        .collect();
    let mut snapshots = vec![vec![0; count]; scenario.clients];
    let mut refreshed = vec![None; scenario.clients];
    let mut outcomes = Vec::with_capacity(trace.len());
    let mut latencies = Vec::new();
    let mut queue_times = Vec::new();
    let mut assigned = vec![0; count];
    let mut max_occupancy = 0;
    let mut within = 0;
    let mut drain = 0;
    for request in trace {
        for (i, queue) in queues.iter_mut().enumerate() {
            while queue
                .front()
                .is_some_and(|p| p.finish_us <= request.arrival_us)
            {
                let pending = queue.pop_front().unwrap();
                if let Some(trackers) = &mut estimators {
                    trackers[pending.client][i]
                        .observe(pending.finish_us, pending.finish_us - pending.arrival_us);
                }
            }
        }
        let c = request.client;
        if refreshed[c]
            .is_none_or(|last| request.arrival_us - last >= scenario.observation_refresh_us)
        {
            snapshots[c] = queues.iter().map(VecDeque::len).collect();
            refreshed[c] = Some(request.arrival_us);
        }
        let candidates: Vec<_> = snapshots[c]
            .iter()
            .enumerate()
            .map(|(i, &load)| {
                let score = if let Some(trackers) = &mut estimators {
                    trackers[c][i].score(request.arrival_us, load)
                } else {
                    load as u64
                };
                Backend::new(i)
                    .with_load(score)
                    .with_status(if load < admission_limit {
                        Status::Ready
                    } else {
                        Status::Unavailable
                    })
            })
            .collect();
        let selected = selectors[c].pick(&candidates);
        let Some(i) = selected else {
            outcomes.push(Outcome {
                id: request.id,
                backend: None,
                status: "no_eligible",
                start_us: None,
                finish_us: None,
                occupancy_after: 0,
                selected_score: None,
            });
            continue;
        };
        if queues[i].len() >= admission_limit {
            outcomes.push(Outcome {
                id: request.id,
                backend: Some(i),
                status: if admission_limit < config.capacity_per_backend {
                    "admission_rejected"
                } else {
                    "capacity_rejected"
                },
                start_us: None,
                finish_us: None,
                occupancy_after: queues[i].len(),
                selected_score: Some(*candidates[i].load()),
            });
            continue;
        }
        let start = queues[i]
            .back()
            .map(|p| p.finish_us)
            .unwrap_or(0)
            .max(request.arrival_us);
        let slowdown = if i < count / 2 && scenario.slowdown_at_us.is_some_and(|t| start >= t) {
            4
        } else {
            1
        };
        let service =
            (scenario.service_us[i] * request.work_per_thousand * slowdown).div_ceil(1000);
        let finish = start + service;
        let latency = finish - request.arrival_us;
        queues[i].push_back(Pending {
            finish_us: finish,
            arrival_us: request.arrival_us,
            client: c,
        });
        snapshots[c][i] += 1;
        assigned[i] += 1;
        max_occupancy = max_occupancy.max(queues[i].len());
        drain = drain.max(finish);
        let on_time = latency <= config.deadline_us;
        within += usize::from(on_time);
        latencies.push(latency);
        queue_times.push(start - request.arrival_us);
        outcomes.push(Outcome {
            id: request.id,
            backend: Some(i),
            status: if on_time { "on_time" } else { "late" },
            start_us: Some(start),
            finish_us: Some(finish),
            occupancy_after: queues[i].len(),
            selected_score: Some(*candidates[i].load()),
        });
    }
    let accepted = latencies.len();
    let summary = Summary {
        scenario: scenario.name.clone(),
        seed,
        policy: policy.into(),
        offered: trace.len(),
        accepted,
        rejected: trace.len() - accepted,
        late: accepted - within,
        within_deadline: within,
        deadline_success: within as f64 / trace.len() as f64,
        within_deadline_per_offered_second: within as f64 * 1_000_000.0
            / trace.last().unwrap().arrival_us as f64,
        latency_p50_us: percentile(&mut latencies, 50),
        latency_p95_us: percentile(&mut latencies, 95),
        latency_p99_us: percentile(&mut latencies, 99),
        queue_p95_us: percentile(&mut queue_times, 95),
        max_backend_occupancy: max_occupancy,
        accepted_per_backend: assigned,
        drain_finish_us: drain,
    };
    (outcomes, summary)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn config() -> Config {
        serde_json::from_str(include_str!("../eval/simulation-v1.json")).unwrap()
    }
    fn request(id: usize, t: u64) -> Request {
        Request {
            id,
            arrival_us: t,
            work_per_thousand: 1000,
            client: 0,
        }
    }

    #[test]
    fn analytically_known_fifo_and_deadline() {
        let mut cfg = config();
        cfg.deadline_us = 19;
        let mut s = cfg.scenarios[0].clone();
        s.service_us = vec![10];
        let trace = vec![request(0, 1), request(1, 2), request(2, 3)];
        let (out, summary) = run(&cfg, &s, 11, "round_robin", &trace);
        assert_eq!(
            out.iter().map(|o| o.finish_us.unwrap()).collect::<Vec<_>>(),
            vec![11, 21, 31]
        );
        assert_eq!(summary.within_deadline, 2);
        assert_eq!(summary.late, 1);
        assert_eq!(summary.latency_p95_us, Some(28));
        assert_eq!(summary.queue_p95_us, Some(18));
    }

    #[test]
    fn fresh_capacity_and_completion_at_arrival() {
        let mut cfg = config();
        cfg.capacity_per_backend = 1;
        let mut s = cfg.scenarios[0].clone();
        s.service_us = vec![10];
        let (out, sum) = run(
            &cfg,
            &s,
            11,
            "round_robin",
            &[request(0, 1), request(1, 2), request(2, 11)],
        );
        assert_eq!(out[1].status, "no_eligible");
        assert_eq!(out[2].finish_us, Some(21));
        assert_eq!(sum.accepted, 2);
    }

    #[test]
    fn stale_client_cannot_exceed_capacity() {
        let mut cfg = config();
        cfg.capacity_per_backend = 1;
        let mut s = cfg.scenarios[0].clone();
        s.service_us = vec![10];
        s.clients = 2;
        s.observation_refresh_us = 100;
        // Client 1 sees only its own first request in its cached snapshot;
        // client 0 then fills the second slot before client 1 selects again.
        cfg.capacity_per_backend = 2;
        let mut a = request(0, 1);
        a.client = 1;
        let trace2 = [a, request(1, 2), {
            let mut r = request(2, 3);
            r.client = 1;
            r
        }];
        let (out, sum) = run(&cfg, &s, 11, "least_inflight", &trace2);
        assert_eq!(out[2].status, "capacity_rejected");
        assert_eq!(sum.max_backend_occupancy, 2);
    }

    #[test]
    fn slowdown_applies_at_service_start_not_arrival() {
        let cfg = config();
        let mut s = cfg.scenarios[0].clone();
        s.service_us = vec![10, 10];
        s.slowdown_at_us = Some(11);
        let trace = [request(0, 1), request(1, 2), request(2, 3)];
        let (out, _) = run(&cfg, &s, 11, "round_robin", &trace);
        assert_eq!(out[0].finish_us, Some(11));
        assert_eq!(out[2].start_us, Some(11));
        assert_eq!(out[2].finish_us, Some(51));
    }

    #[test]
    fn deterministic_and_conservative_all_scenarios() {
        let mut cfg = config();
        cfg.requests_per_run = 100;
        cfg.validate().unwrap();
        for s in &cfg.scenarios {
            for p in POLICIES {
                let trace = workload(&cfg, s, 11);
                assert_eq!(trace, workload(&cfg, s, 11));
                let first = run(&cfg, s, 11, p, &trace);
                assert_eq!(first, run(&cfg, s, 11, p, &trace));
                let sum = first.1;
                assert_eq!(sum.offered, sum.accepted + sum.rejected);
                assert_eq!(sum.accepted, sum.within_deadline + sum.late);
                assert_eq!(sum.accepted, sum.accepted_per_backend.iter().sum::<usize>());
                assert!(sum.max_backend_occupancy <= cfg.capacity_per_backend);
            }
        }
    }

    #[test]
    fn peak_decay_floor_and_concurrency_are_analytic() {
        let mut tracker = SimulatedPeak::new(10, 100);
        tracker.observe(0, 80);
        assert_eq!(tracker.score(100, 0), 40_000);
        assert_eq!(tracker.score(200, 2), 60_000);
        assert_eq!(tracker.score(1000, 0), 10_000);
        tracker.observe(1000, 100);
        assert_eq!(tracker.score(1000, 1), 200_000);
        tracker.observe(1000, 20);
        assert_eq!(tracker.score(1000, 0), 100_000);
    }

    #[test]
    fn unfinished_requests_do_not_reveal_their_latency() {
        let mut cfg = config();
        cfg.latency = Some(LatencyConfig {
            default_rtt_us: 10,
            half_lives_us: vec![100],
        });
        let mut s = cfg.scenarios[0].clone();
        s.service_us = vec![100, 100];
        let trace = vec![request(0, 1), request(1, 2), request(2, 3)];
        let mut changed = trace.clone();
        changed[0].work_per_thousand = 1500;
        let (a, _) = run(&cfg, &s, 11, "least_peak_100", &trace);
        let (b, _) = run(&cfg, &s, 11, "least_peak_100", &changed);
        for (left, right) in a.iter().zip(b.iter()) {
            assert_eq!(left.backend, right.backend);
            assert_eq!(left.selected_score, right.selected_score);
        }
    }

    #[test]
    fn completion_feedback_is_private_to_the_sending_client() {
        let mut cfg = config();
        cfg.latency = Some(LatencyConfig {
            default_rtt_us: 1,
            half_lives_us: vec![1000],
        });
        let mut s = cfg.scenarios[0].clone();
        s.service_us = vec![10, 10];
        s.clients = 2;
        let mut second = request(1, 12);
        second.client = 1;
        let (out, _) = run(&cfg, &s, 11, "least_peak_1000", &[request(0, 1), second]);
        assert_eq!(out[1].backend, Some(0));
        assert_eq!(out[1].selected_score, Some(1000));
    }

    #[test]
    fn latency_configuration_is_bounded_and_reproducible() {
        let mut cfg: Config =
            serde_json::from_str(include_str!("../eval/simulation-v2.json")).unwrap();
        cfg.requests_per_run = 100;
        cfg.validate().unwrap();
        assert_eq!(cfg.policies().len(), 9);
        for s in &cfg.scenarios {
            for policy in cfg.policies() {
                let trace = workload(&cfg, s, 11);
                assert_eq!(
                    run(&cfg, s, 11, &policy, &trace),
                    run(&cfg, s, 11, &policy, &trace)
                );
            }
        }
        cfg.latency.as_mut().unwrap().half_lives_us.push(0);
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn admission_one_has_no_wait_slot_and_reuses_completed_capacity() {
        let cfg = config();
        let mut s = cfg.scenarios[0].clone();
        s.service_us = vec![10];
        let trace = [request(0, 1), request(1, 2), request(2, 11)];
        let (out, summary) = run(&cfg, &s, 11, "least_inflight__cap_1", &trace);
        assert_eq!(out[1].status, "no_eligible");
        assert_eq!(out[1].finish_us, None);
        assert_eq!(out[2].start_us, Some(11));
        assert_eq!(summary.accepted, 2);
        assert_eq!(summary.max_backend_occupancy, 1);
        assert_eq!(summary.queue_p95_us, Some(0));
    }

    #[test]
    fn stale_admission_rejections_do_not_enqueue_or_update_latency() {
        let mut cfg = config();
        cfg.latency = Some(LatencyConfig {
            default_rtt_us: 1,
            half_lives_us: vec![1000],
        });
        let mut s = cfg.scenarios[0].clone();
        s.service_us = vec![100];
        s.clients = 2;
        s.observation_refresh_us = 1000;
        let mut first = request(0, 1);
        first.client = 1;
        let mut third = request(2, 3);
        third.client = 1;
        let mut fourth = request(3, 4);
        fourth.client = 1;
        let (out, summary) = run(
            &cfg,
            &s,
            11,
            "least_peak_1000__cap_2",
            &[first, request(1, 2), third, fourth],
        );
        for result in &out[2..] {
            assert_eq!(result.status, "admission_rejected");
            assert_eq!(result.occupancy_after, 2);
            assert_eq!(result.selected_score, Some(2000));
            assert_eq!(result.finish_us, None);
        }
        assert_eq!(summary.accepted, 2);
        assert_eq!(summary.drain_finish_us, 201);
    }

    #[test]
    fn admission_at_physical_limit_preserves_original_behavior() {
        let cfg: Config = serde_json::from_str(include_str!("../eval/simulation-v3.json")).unwrap();
        for s in &cfg.scenarios {
            let trace = workload(&cfg, s, 11);
            for selector in &cfg.admission.as_ref().unwrap().selectors {
                let (old_out, mut old_summary) = run(&cfg, s, 11, selector, &trace);
                let (new_out, new_summary) =
                    run(&cfg, s, 11, &format!("{selector}__cap_16"), &trace);
                old_summary.policy = new_summary.policy.clone();
                assert_eq!(old_out, new_out);
                assert_eq!(old_summary, new_summary);
            }
        }
    }

    #[test]
    fn admission_config_and_occupancy_are_bounded() {
        let mut cfg: Config =
            serde_json::from_str(include_str!("../eval/simulation-v3.json")).unwrap();
        cfg.requests_per_run = 100;
        cfg.validate().unwrap();
        assert_eq!(cfg.policies().len(), 10);
        for s in &cfg.scenarios {
            for policy in cfg.policies() {
                let limit = policy
                    .split_once("__cap_")
                    .unwrap()
                    .1
                    .parse::<usize>()
                    .unwrap();
                let trace = workload(&cfg, s, 11);
                let (out, summary) = run(&cfg, s, 11, &policy, &trace);
                assert!(out.iter().all(|r| r.occupancy_after <= limit));
                assert!(summary.max_backend_occupancy <= limit);
                assert_eq!(
                    summary.offered,
                    summary.rejected + summary.late + summary.within_deadline
                );
            }
        }
        cfg.admission.as_mut().unwrap().limits.push(17);
        assert!(cfg.validate().is_err());
        cfg.admission.as_mut().unwrap().limits = vec![0];
        assert!(cfg.validate().is_err());
        cfg.admission.as_mut().unwrap().limits = vec![1, 4, 16];
        cfg.admission.as_mut().unwrap().selectors = vec!["invented".into()];
        assert!(cfg.validate().is_err());
    }
}
