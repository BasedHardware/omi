//! Request-level deadline budget for the Anthropic chat path (FC-per-hop-timeout).
//!
//! One admission budget is created in route middleware before extractors run and
//! governs everything up to the first client-visible semantic SSE event: auth and
//! paywall waits, body extraction, provider retries, and server-tool
//! continuations. Provider headers, pings, and keepalives are not progress.
//! After the first visible event the budget is done — streaming deliberately has
//! no total response timeout (#9135: a long answer is not an error) and stalls
//! are governed by the semantic-progress idle timer in the stream translator.
//!
//! Policy clocks are explicitly out of scope: the unknown-kid refresh cooldown,
//! cache TTLs, the idle-timer policy value, and startup retries stay
//! independent. Detached work spawned during a request (the Firestore usage
//! write on `message_stop`) must never inherit the request deadline.

use std::time::Duration;

/// Cloud Run's configured request timeout for `desktop-backend`. This is the
/// code-side constant; the deployed platform value must be verified as release
/// evidence, not assumed from here.
pub const PLATFORM_REQUEST_TIMEOUT: Duration = Duration::from_secs(300);

/// Headroom reserved under the platform bound so the gateway, not Cloud Run,
/// owns timeout mapping and can return a typed, retryable timeout response.
pub const PLATFORM_HEADROOM: Duration = Duration::from_secs(60);

/// The single admission budget per provider route class. The Anthropic chat
/// path and the Gemini proxy both derive it from the same platform contract.
pub const REQUEST_BUDGET: Duration =
    Duration::from_secs(PLATFORM_REQUEST_TIMEOUT.as_secs() - PLATFORM_HEADROOM.as_secs());

/// Absolute deadline for one request, measured on the tokio clock so tests can
/// drive it with `tokio::time::pause`.
#[derive(Debug, Clone, Copy)]
pub struct RequestDeadline {
    deadline: tokio::time::Instant,
}

impl RequestDeadline {
    pub fn new(budget: Duration) -> Self {
        Self {
            deadline: tokio::time::Instant::now() + budget,
        }
    }

    /// Time left in the budget; zero once expired.
    pub fn remaining(&self) -> Duration {
        self.deadline
            .saturating_duration_since(tokio::time::Instant::now())
    }

    /// Bound a stage constant by the budget: `min(cap, remaining)`.
    pub fn derive(&self, cap: Duration) -> Duration {
        cap.min(self.remaining())
    }

    pub fn expired(&self) -> bool {
        self.remaining() == Duration::ZERO
    }
}

/// Failure surface of a budgeted provider send.
#[derive(Debug)]
pub enum DeadlineSendError {
    /// The budget ran out before the provider produced response headers.
    Expired,
    /// The transport failed within the budget (connect/read errors).
    Transport(reqwest::Error),
}

/// The narrow seam every outbound provider send on the chat path goes through.
/// A diff-scoped checker (`check_chat_send_deadline.py`) flags direct
/// `.send()` calls in `routes/chat/` that bypass it.
pub async fn send_with_deadline(
    builder: reqwest::RequestBuilder,
    deadline: &RequestDeadline,
) -> Result<reqwest::Response, DeadlineSendError> {
    let remaining = deadline.remaining();
    if remaining == Duration::ZERO {
        return Err(DeadlineSendError::Expired);
    }
    match tokio::time::timeout(remaining, builder.send()).await {
        Ok(Ok(response)) => Ok(response),
        Ok(Err(error)) => Err(DeadlineSendError::Transport(error)),
        Err(_) => Err(DeadlineSendError::Expired),
    }
}

/// The budget's absolute edge won the race against still-pending work.
#[derive(Debug, PartialEq, Eq)]
pub struct DeadlineElapsed;

/// Race a deadline future against work. Dropping the returned future drops the
/// in-flight work, so a downstream disconnect still cancels the upstream call.
pub async fn race_deadline<D, F, T>(deadline: D, future: F) -> Result<T, DeadlineElapsed>
where
    D: std::future::Future<Output = ()>,
    F: std::future::Future<Output = T>,
{
    tokio::pin!(deadline);
    tokio::pin!(future);
    tokio::select! {
        value = &mut future => Ok(value),
        () = &mut deadline => Err(DeadlineElapsed),
    }
}

/// Bound a whole unit of request-owned work by the remaining budget.
pub async fn within_deadline<F, T>(
    deadline: &RequestDeadline,
    future: F,
) -> Result<T, DeadlineElapsed>
where
    F: std::future::Future<Output = T>,
{
    race_deadline(tokio::time::sleep(deadline.remaining()), future).await
}

/// Middleware that admits the request budget before extractors and body
/// extraction run, so auth/paywall waits are inside the budget.
pub async fn attach_request_deadline(
    mut request: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    request
        .extensions_mut()
        .insert(RequestDeadline::new(REQUEST_BUDGET));
    next.run(request).await
}

#[axum::async_trait]
impl<S> axum::extract::FromRequestParts<S> for RequestDeadline
where
    S: Send + Sync,
{
    type Rejection = std::convert::Infallible;

    async fn from_request_parts(
        parts: &mut axum::http::request::Parts,
        _state: &S,
    ) -> Result<Self, Self::Rejection> {
        // The middleware guarantees presence on the chat route; a fresh budget
        // is the safe fallback if the layer is ever missing.
        Ok(parts
            .extensions
            .get::<RequestDeadline>()
            .copied()
            .unwrap_or_else(|| RequestDeadline::new(REQUEST_BUDGET)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test(start_paused = true)]
    async fn remaining_derive_and_expiry_follow_the_tokio_clock() {
        let deadline = RequestDeadline::new(Duration::from_secs(100));
        assert!(!deadline.expired());
        assert_eq!(
            deadline.derive(Duration::from_secs(5)),
            Duration::from_secs(5)
        );

        tokio::time::advance(Duration::from_secs(97)).await;
        assert_eq!(deadline.remaining(), Duration::from_secs(3));
        // A stage cap larger than the budget is truncated to what's left.
        assert_eq!(
            deadline.derive(Duration::from_secs(120)),
            Duration::from_secs(3)
        );

        tokio::time::advance(Duration::from_secs(4)).await;
        assert!(deadline.expired());
        assert_eq!(deadline.remaining(), Duration::ZERO);
        assert_eq!(deadline.derive(Duration::from_secs(5)), Duration::ZERO);
    }

    #[tokio::test(start_paused = true)]
    async fn middleware_admits_the_shared_budget_before_the_handler() {
        use axum::{body::Body, http::Request, routing::get, Router};
        use tower::ServiceExt;

        let app = Router::new()
            .route(
                "/",
                get(|deadline: RequestDeadline| async move {
                    // Time spent before/inside the handler consumes the one
                    // budget the middleware admitted.
                    tokio::time::advance(Duration::from_secs(100)).await;
                    deadline.remaining().as_secs().to_string()
                }),
            )
            .layer(axum::middleware::from_fn(attach_request_deadline));

        let response = app
            .oneshot(Request::builder().uri("/").body(Body::empty()).unwrap())
            .await
            .unwrap();
        let body = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let expected = REQUEST_BUDGET.as_secs() - 100;
        assert_eq!(body, expected.to_string().as_bytes());
    }
}
