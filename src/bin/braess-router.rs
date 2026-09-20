//! Loopback-only first gateway. Explicit bounds before JSON extraction/dispatch.
use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, Request, State, rejection::JsonRejection},
    http::{StatusCode, header},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use braess_router::{
    Rubric,
    gateway::{Config, Gateway, GatewayRequest, Mode},
};
use serde_json::json;
use std::{
    future::Future,
    io,
    net::SocketAddr,
    pin::Pin,
    sync::{
        Arc,
        atomic::{AtomicU64, Ordering},
    },
    task::{Context, Poll},
    time::{Duration, Instant},
};
use tokio::{
    io::{AsyncRead, AsyncWrite, ReadBuf},
    net::{TcpListener, TcpStream},
    sync::{OwnedSemaphorePermit, Semaphore},
    time::Sleep,
};

#[derive(Clone)]
struct App {
    gateway: Arc<Gateway>,
    ingress: Arc<Semaphore>,
    deadline: Duration,
    request_ids: Arc<AtomicU64>,
}
#[derive(Clone)]
struct ErrorCode(String);
fn error(status: StatusCode, code: &str) -> Response {
    let mut response = (status, Json(json!({"error":code}))).into_response();
    response.extensions_mut().insert(ErrorCode(code.into()));
    response
}
struct Audit {
    id: u64,
    start: Instant,
    finished: bool,
}
impl Drop for Audit {
    fn drop(&mut self) {
        if !self.finished {
            eprintln!(
                "{}",
                json!({"event":"request_cancelled","request_id":self.id,"elapsed_ms":self.start.elapsed().as_secs_f64()*1000.0})
            );
        }
    }
}
async fn bound_request(State(state): State<App>, request: Request, next: Next) -> Response {
    let Ok(id) = state
        .request_ids
        .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |n| n.checked_add(1))
    else {
        return error(StatusCode::SERVICE_UNAVAILABLE, "request_id_exhausted");
    };
    let mut audit = Audit {
        id,
        start: Instant::now(),
        finished: false,
    };
    let mut response = match state.ingress.clone().try_acquire_owned() {
        Ok(_permit) => match tokio::time::timeout(state.deadline, next.run(request)).await {
            Ok(response) => response,
            Err(_) => error(StatusCode::GATEWAY_TIMEOUT, "deadline_exceeded"),
        },
        Err(_) => error(StatusCode::SERVICE_UNAVAILABLE, "ingress_full"),
    };
    let code = response
        .extensions()
        .get::<ErrorCode>()
        .map(|c| c.0.as_str());
    eprintln!(
        "{}",
        json!({"event":"response_ready","request_id":id,"status":response.status().as_u16(),"error":code,"elapsed_ms":audit.start.elapsed().as_secs_f64()*1000.0})
    );
    audit.finished = true;
    response
        .headers_mut()
        .insert("x-request-id", id.to_string().parse().unwrap());
    // This milestone deliberately has no pooled inbound connections.
    response
        .headers_mut()
        .insert(header::CONNECTION, "close".parse().unwrap());
    response
}
async fn route(
    State(state): State<App>,
    input: Result<Json<GatewayRequest>, JsonRejection>,
) -> Response {
    let request = match input {
        Ok(Json(request)) => request,
        Err(rejection) => {
            return error(
                if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE {
                    StatusCode::PAYLOAD_TOO_LARGE
                } else {
                    StatusCode::BAD_REQUEST
                },
                "invalid_request",
            );
        }
    };
    match state.gateway.execute(request).await {
        Ok(response) => Json(response).into_response(),
        Err(failure) => {
            let mut response = error(
                StatusCode::from_u16(failure.status).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
                &failure.code,
            );
            if let Some(seconds) = failure.retry_after_seconds {
                response
                    .headers_mut()
                    .insert(header::RETRY_AFTER, seconds.into());
            }
            response
        }
    }
}
async fn status(State(state): State<App>) -> Json<serde_json::Value> {
    Json(state.gateway.status())
}
async fn ready(State(state): State<App>) -> Response {
    let mut report = state.gateway.readiness();
    if state.ingress.available_permits() == 0 {
        report["ready"] = json!(false);
        report["reasons"]
            .as_array_mut()
            .unwrap()
            .push(json!("ingress_full"));
    }
    let code = if report["ready"] == true {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };
    let mut response = (code, Json(report)).into_response();
    response
        .headers_mut()
        .insert(header::CACHE_CONTROL, "no-store".parse().unwrap());
    response
}

// Limit accepted connection tasks, including peers that never finish headers.
// Every connection has an absolute lifetime, including header/body I/O.
struct BoundedListener {
    socket: TcpListener,
    slots: Arc<Semaphore>,
    lifetime: Duration,
}
struct BoundedIo {
    socket: TcpStream,
    _permit: OwnedSemaphorePermit,
    timer: Pin<Box<Sleep>>,
}
impl BoundedIo {
    fn expired(&mut self, cx: &mut Context<'_>) -> bool {
        self.timer.as_mut().poll(cx).is_ready()
    }
}
fn expired_error() -> io::Error {
    io::Error::new(io::ErrorKind::TimedOut, "connection lifetime exceeded")
}
impl AsyncRead for BoundedIo {
    fn poll_read(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        if self.expired(cx) {
            return Poll::Ready(Err(expired_error()));
        }
        Pin::new(&mut self.socket).poll_read(cx, buf)
    }
}
impl AsyncWrite for BoundedIo {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &[u8],
    ) -> Poll<io::Result<usize>> {
        if self.expired(cx) {
            return Poll::Ready(Err(expired_error()));
        }
        Pin::new(&mut self.socket).poll_write(cx, buf)
    }
    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if self.expired(cx) {
            return Poll::Ready(Err(expired_error()));
        }
        Pin::new(&mut self.socket).poll_flush(cx)
    }
    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.socket).poll_shutdown(cx)
    }
}
impl axum::serve::Listener for BoundedListener {
    type Io = BoundedIo;
    type Addr = SocketAddr;
    async fn accept(&mut self) -> (Self::Io, Self::Addr) {
        loop {
            let permit = self
                .slots
                .clone()
                .acquire_owned()
                .await
                .expect("private connection semaphore");
            match self.socket.accept().await {
                Ok((socket, addr)) => {
                    return (
                        BoundedIo {
                            socket,
                            _permit: permit,
                            timer: Box::pin(tokio::time::sleep(self.lifetime)),
                        },
                        addr,
                    );
                }
                Err(_) => tokio::time::sleep(Duration::from_millis(100)).await,
            }
        }
    }
    fn local_addr(&self) -> io::Result<Self::Addr> {
        self.socket.local_addr()
    }
}

fn main() {
    if let Err(code) = run() {
        eprintln!("{code}");
        std::process::exit(1);
    }
}
fn run() -> Result<(), String> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.len() != 2 || args[0] != "--config" {
        return Err("usage: braess-router --config PATH".into());
    }
    let bytes = std::fs::read(&args[1]).map_err(|_| "config_read_failed")?;
    if bytes.len() > 65536 {
        return Err("config_too_large".into());
    }
    let config: Config = serde_json::from_slice(&bytes).map_err(|_| "invalid_config_json")?;
    config.validate()?;
    let bind: SocketAddr = config.bind.parse().map_err(|_| "invalid_bind")?;
    if !bind.ip().is_loopback() {
        return Err("bind_must_be_loopback".into());
    }
    let rubric_bytes = std::fs::read(&config.rubric_path).map_err(|_| "rubric_read_failed")?;
    if rubric_bytes.len() > 65536 {
        return Err("rubric_too_large".into());
    }
    let rubric: Rubric =
        serde_json::from_slice(&rubric_bytes).map_err(|_| "invalid_rubric_json")?;
    let admission = config.admission_limit;
    let body_limit = config.max_request_bytes;
    let deadline = Duration::from_millis(config.deadline_ms);
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(4)
        .enable_all()
        .build()
        .map_err(|_| "runtime_failed")?;
    runtime.block_on(async move {
        let key = if config.mode == Mode::Live {
            std::env::var("TYPESAFE_API_KEY").ok()
        } else {
            None
        };
        let gateway = Gateway::new(config, rubric, key)?;
        let state = App {
            gateway,
            ingress: Arc::new(Semaphore::new(admission)),
            deadline,
            request_ids: Arc::new(AtomicU64::new(0)),
        };
        let routes = Router::new()
            .route("/route", post(route))
            .layer(DefaultBodyLimit::max(body_limit))
            .route_layer(middleware::from_fn_with_state(state.clone(), bound_request));
        let app = Router::new()
            .merge(routes)
            .route("/health", get(|| async { Json(json!({"status":"ok"})) }))
            .route("/status", get(status))
            .route("/ready", get(ready))
            .with_state(state);
        let socket = TcpListener::bind(bind).await.map_err(|_| "bind_failed")?;
        eprintln!(
            "braess-router listening on {}",
            socket.local_addr().map_err(|_| "bind_failed")?
        );
        let listener = BoundedListener {
            socket,
            slots: Arc::new(Semaphore::new(
                admission.saturating_mul(2).saturating_add(8),
            )),
            lifetime: deadline.saturating_mul(2).max(Duration::from_secs(1)),
        };
        #[cfg(unix)]
        let mut terminate =
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
                .map_err(|_| "signal_registration_failed")?;
        axum::serve(listener, app)
            .with_graceful_shutdown(async move {
                #[cfg(unix)]
                tokio::select! {
                    _ = tokio::signal::ctrl_c() => {},
                    _ = terminate.recv() => {},
                }
                #[cfg(not(unix))]
                let _ = tokio::signal::ctrl_c().await;
            })
            .await
            .map_err(|_| "serve_failed".into())
    })
}
