//! HTTP response ownership for the request ledger. EOF alone is not validation.
use crate::request_ledger::{Attempt, LedgerError};

#[derive(Debug)]
pub enum HttpLedgerError {
    Ledger(LedgerError),
    Transport(reqwest::Error),
    UnexpectedStatus(u16),
    BodyNotComplete,
}

/// Owns admission through dispatch, body consumption, and application validation.
/// Dropping any dispatched owner without `validated` retains uncertainty.
pub struct LedgerResponse {
    response: Option<reqwest::Response>,
    attempt: Option<Attempt>,
    eof: bool,
}

impl LedgerResponse {
    pub async fn send(
        request: reqwest::RequestBuilder,
        mut attempt: Attempt,
    ) -> Result<Self, HttpLedgerError> {
        // Build first: malformed local requests are demonstrably not dispatched.
        let (client, request) = request.build_split();
        let request = request.map_err(HttpLedgerError::Transport)?;
        attempt.mark_dispatched().map_err(HttpLedgerError::Ledger)?;
        let response = client
            .execute(request)
            .await
            .map_err(HttpLedgerError::Transport)?
            .error_for_status()
            .map_err(HttpLedgerError::Transport)?;
        if !response.status().is_success() {
            return Err(HttpLedgerError::UnexpectedStatus(
                response.status().as_u16(),
            ));
        }
        Ok(Self {
            response: Some(response),
            attempt: Some(attempt),
            eof: false,
        })
    }

    pub async fn chunk(&mut self) -> Result<Option<Vec<u8>>, HttpLedgerError> {
        let Some(response) = self.response.as_mut() else {
            return Err(HttpLedgerError::BodyNotComplete);
        };
        if self.eof {
            return Ok(None);
        }
        match response.chunk().await {
            Ok(Some(bytes)) => Ok(Some(bytes.to_vec())),
            Ok(None) => {
                self.eof = true;
                Ok(None)
            }
            Err(error) => {
                self.response.take();
                self.attempt.take();
                Err(HttpLedgerError::Transport(error))
            }
        }
    }

    /// Caller attests that the entire response passed its schema/model/rubric
    /// contract. Never call this for mere HTTP success, or a partial body.
    pub fn validated(mut self) -> Result<(), HttpLedgerError> {
        if !self.eof {
            return Err(HttpLedgerError::BodyNotComplete);
        }
        self.attempt
            .take()
            .ok_or(HttpLedgerError::BodyNotComplete)?
            .response_received()
            .map_err(HttpLedgerError::Ledger)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::request_ledger::{LedgerConfig, RequestLedger};
    use std::time::Duration;

    #[test]
    fn invalid_request_build_is_not_sent() {
        let ledger = RequestLedger::new(LedgerConfig {
            admission_limit: 1,
            tracking_limit: 2,
            uncertainty_ttl: Duration::ZERO,
        })
        .unwrap();
        let runtime = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        let result = runtime.block_on(LedgerResponse::send(
            reqwest::Client::new().get("not a URL"),
            ledger.try_admit().unwrap(),
        ));
        assert!(matches!(result, Err(HttpLedgerError::Transport(_))));
        let s = ledger.snapshot();
        assert_eq!(
            (s.not_sent_total, s.uncertainty_total, s.tracked()),
            (1, 0, 0)
        );
    }

    #[test]
    fn validation_before_eof_cannot_claim_completion() {
        let ledger = RequestLedger::new(LedgerConfig {
            admission_limit: 1,
            tracking_limit: 2,
            uncertainty_ttl: Duration::ZERO,
        })
        .unwrap();
        let mut attempt = ledger.try_admit().unwrap();
        attempt.mark_dispatched().unwrap();
        let body = LedgerResponse {
            response: None,
            attempt: Some(attempt),
            eof: false,
        };
        assert!(matches!(
            body.validated(),
            Err(HttpLedgerError::BodyNotComplete)
        ));
        let s = ledger.snapshot();
        assert_eq!((s.response_received_total, s.expired_unconfirmed), (0, 1));
    }
}
