#![deny(dead_code, unreachable_pub)]
//! Shared bounded HTTP client construction.
//!
//! Every outbound HTTP call must carry a connect timeout and a total-request
//! deadline: a bare `reqwest::Client::new()` has neither, so one hung upstream
//! (Pinecone, Sentry, Crisp, ...) pins its handler or background task until the
//! platform kills it. Related failure class: FC-per-hop-timeout — bounded
//! per-request budgets instead of per-call-site retail timeouts.

use std::time::Duration;

const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);

/// Build a client whose every request fails after `total_timeout` end to end
/// (connect included, capped separately at 10s). Callers pick the budget that
/// fits their upstream; none may opt out of having one.
pub(crate) fn bounded_client(total_timeout: Duration) -> reqwest::Client {
    reqwest::Client::builder()
        .connect_timeout(CONNECT_TIMEOUT)
        .timeout(total_timeout)
        .build()
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;
    use tokio::io::AsyncReadExt;
    use tokio::net::TcpListener;

    #[tokio::test]
    async fn bounded_client_fails_a_stalled_upstream_within_its_budget() {
        // A listener that accepts the connection and then never responds —
        // the exact upstream shape a bare Client::new() hangs on forever.
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut buf = [0u8; 1024];
            // Read the request, then stall without ever writing a response.
            let _ = socket.read(&mut buf).await;
            tokio::time::sleep(Duration::from_secs(30)).await;
        });

        let client = bounded_client(Duration::from_millis(300));
        let started = Instant::now();
        let result = client.get(format!("http://{}", addr)).send().await;
        let elapsed = started.elapsed();

        assert!(
            result.is_err(),
            "stalled upstream must not yield a response"
        );
        assert!(
            result.unwrap_err().is_timeout(),
            "failure must be the client-side deadline, not a transport error"
        );
        assert!(
            elapsed < Duration::from_secs(5),
            "deadline must fire near its budget, elapsed={elapsed:?}"
        );
        server.abort();
    }
}
