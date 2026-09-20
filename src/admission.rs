//! In-process mock admission and body ownership for lifecycle experiments.
use serde::Serialize;
use std::sync::{Arc, Mutex};
use tokio::sync::{OwnedSemaphorePermit, Semaphore};

#[derive(Clone, Debug, Serialize)]
pub struct Event {
    pub request: usize,
    pub kind: &'static str,
}

pub struct Backend {
    permits: Arc<Semaphore>,
    events: Mutex<Vec<Event>>,
}

impl Backend {
    pub fn new(limit: usize) -> Arc<Self> {
        assert!(limit > 0);
        Arc::new(Self {
            permits: Arc::new(Semaphore::new(limit)),
            events: Mutex::new(Vec::new()),
        })
    }

    /// Admission is immediate. Client load observations never grant a permit.
    pub fn try_start(self: &Arc<Self>, request: usize) -> Option<Body> {
        let mut events = self.events.lock().unwrap();
        match self.permits.clone().try_acquire_owned() {
            Ok(permit) => {
                events.push(Event {
                    request,
                    kind: "admit",
                });
                events.push(Event {
                    request,
                    kind: "headers",
                });
                Some(Body {
                    backend: self.clone(),
                    request,
                    permit: Some(permit),
                    chunk_sent: false,
                })
            }
            Err(_) => {
                events.push(Event {
                    request,
                    kind: "reject",
                });
                None
            }
        }
    }

    pub fn available(&self) -> usize {
        self.permits.available_permits()
    }

    pub fn events(&self) -> Vec<Event> {
        self.events.lock().unwrap().clone()
    }
}

/// The response body owns admission through EOF, error, or destruction.
/// There is no detached producer: dropping this mock stops its work immediately.
pub struct Body {
    backend: Arc<Backend>,
    request: usize,
    permit: Option<OwnedSemaphorePermit>,
    chunk_sent: bool,
}

impl Body {
    pub async fn chunk(&mut self) -> Option<&'static [u8]> {
        self.permit.as_ref()?;
        if self.chunk_sent {
            self.finish();
            return None;
        }
        tokio::task::yield_now().await;
        self.backend.events.lock().unwrap().push(Event {
            request: self.request,
            kind: "chunk",
        });
        self.chunk_sent = true;
        Some(b"mock chunk")
    }

    pub fn finish(&mut self) {
        self.release("eof");
    }

    pub fn fail(&mut self) {
        self.release("body_error");
    }

    fn release(&mut self, kind: &'static str) {
        let mut events = self.backend.events.lock().unwrap();
        if let Some(permit) = self.permit.take() {
            events.push(Event {
                request: self.request,
                kind,
            });
            // Serialize trace ordering with both permit acquisition and release.
            drop(permit);
        }
    }
}

impl Drop for Body {
    fn drop(&mut self) {
        self.release("cancelled");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn headers_hold_capacity_and_terminal_release_is_idempotent() {
        let backend = Backend::new(1);
        let mut body = backend.try_start(0).unwrap();
        assert!(backend.try_start(1).is_none());
        body.finish();
        body.finish();
        body.fail();
        drop(body);
        assert_eq!(backend.available(), 1);
        assert_eq!(
            backend.events().iter().filter(|e| e.kind == "eof").count(),
            1
        );
        assert!(backend.try_start(2).is_some());
    }

    #[test]
    fn dropping_unread_body_releases_capacity() {
        let backend = Backend::new(1);
        drop(backend.try_start(0).unwrap());
        assert_eq!(backend.available(), 1);
        assert_eq!(backend.events().last().unwrap().kind, "cancelled");
    }
}
