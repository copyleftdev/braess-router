//! Local handler service; generation admission is durable inside Adapter.
use super::{Adapter, Config, Request};
use crate::local_http::BoundedListener;
use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, Path, State, rejection::JsonRejection},
    http::StatusCode,
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use serde_json::json;
use std::{sync::Arc, time::Duration};
use tokio::{net::TcpListener, sync::Semaphore};
#[derive(Clone)]
struct App {
    adapter: Arc<Adapter>,
    ingress: Arc<Semaphore>,
    deadline: Duration,
}
fn error(status: u16, code: &str) -> Response {
    (
        StatusCode::from_u16(status).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
        Json(json!({"error":code})),
    )
        .into_response()
}
async fn bounds(State(state): State<App>, request: axum::extract::Request, next: Next) -> Response {
    let Ok(_permit) = state.ingress.try_acquire() else {
        return error(503, "ingress_full");
    };
    let mut response = match tokio::time::timeout(state.deadline, next.run(request)).await {
        Ok(response) => response,
        Err(_) => error(504, "handler_deadline_exceeded"),
    };
    response.headers_mut().insert(
        axum::http::header::CONNECTION,
        axum::http::HeaderValue::from_static("close"),
    );
    response
}
async fn generate(
    State(state): State<App>,
    input: Result<Json<Request>, JsonRejection>,
) -> Response {
    let input = match input {
        Ok(Json(input)) => input,
        Err(rejection) => {
            return error(
                if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE {
                    413
                } else {
                    400
                },
                "invalid_request",
            );
        }
    };
    match state.adapter.execute(input).await {
        Ok(output) => Json(output).into_response(),
        Err(failure) => error(failure.status, failure.code),
    }
}
async fn generate_route(
    State(state): State<App>,
    Path(route): Path<String>,
    input: Result<Json<Request>, JsonRejection>,
) -> Response {
    if let Ok(Json(ref value)) = input
        && value.route != route
    {
        return error(400, "route_path_mismatch");
    }
    generate(State(state), input).await
}
async fn status(State(state): State<App>) -> Response {
    match state.adapter.status().await {
        Ok(s) => Json(s).into_response(),
        Err(e) => error(e.status, e.code),
    }
}
async fn ready(State(state): State<App>) -> Response {
    match state.adapter.status().await {
        Ok(s) => (
            if s["ready"] == true {
                StatusCode::OK
            } else {
                StatusCode::SERVICE_UNAVAILABLE
            },
            Json(s),
        )
            .into_response(),
        Err(e) => error(e.status, e.code),
    }
}
pub async fn serve(config: Config, key: Option<String>) -> Result<(), &'static str> {
    config.validate()?;
    let adapter = Adapter::new(config.clone(), key)?;
    let state = App {
        adapter,
        ingress: Arc::new(Semaphore::new(config.admission_limit)),
        deadline: Duration::from_millis(config.deadline_ms),
    };
    let routes = Router::new()
        .route("/generate", post(generate))
        .route("/generate/{route}", post(generate_route))
        .layer(DefaultBodyLimit::max(config.max_request_bytes))
        .route_layer(middleware::from_fn_with_state(state.clone(), bounds));
    let app = Router::new()
        .merge(routes)
        .route("/health", get(|| async { Json(json!({"status":"ok"})) }))
        .route("/status", get(status))
        .route("/ready", get(ready))
        .with_state(state);
    let socket = TcpListener::bind(config.bind)
        .await
        .map_err(|_| "bind_failed")?;
    let listener = BoundedListener::new(
        socket,
        config.admission_limit * 2 + 8,
        Duration::from_millis(config.deadline_ms)
            .saturating_mul(2)
            .max(Duration::from_secs(1)),
    );
    #[cfg(unix)]
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        .map_err(|_| "signal_registration_failed")?;
    axum::serve(listener, app)
        .with_graceful_shutdown(async move {
            #[cfg(unix)]
            tokio::select! { _=tokio::signal::ctrl_c()=>{},_=terminate.recv()=>{} }
            #[cfg(not(unix))]
            let _ = tokio::signal::ctrl_c().await;
        })
        .await
        .map_err(|_| "serve_failed")
}
