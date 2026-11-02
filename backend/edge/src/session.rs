//! One relayed session: two independent pumps (client -> upstream and
//! upstream -> client) so a slow reader on one side never blocks the other
//! direction, plus the close-handshake and drain bookkeeping.
//!
//! Semantics (what "passthrough" means here):
//! - Text and binary messages are relayed message for message with identical
//!   payload bytes, in order, per direction. Fragmented messages are
//!   reassembled and re-sent as one frame, as any websocket proxy that
//!   terminates the protocol does.
//! - Ping/pong are hop-by-hop: each side's pings are answered by the edge
//!   (tungstenite does this automatically) and are not relayed.
//! - A close frame (code and reason) is relayed to the other side. Each side
//!   gets its close echo from the edge, as it would from listen today.
//! - A connection that ends without a close frame is mirrored: the other side
//!   is dropped without a close frame too, so listen sees exactly what it
//!   sees today when a client vanishes.
//! - Drain: the edge sends the client 1012 (service restart). Frames the
//!   client sent before it saw that close are still relayed upstream. Listen
//!   then gets **1001** (going away), whether the client echoes the 1012 or
//!   vanishes: listen treats 1000 and 1001 as ordinary closes, but only 1000
//!   finalizes a desktop conversation. 1001 keeps the conversation in
//!   progress for the client's reconnect, exactly as a dropped client does
//!   today. Any other close code the client sends is relayed unchanged.
use std::future::Future;
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use futures_util::{Sink, SinkExt, Stream, StreamExt};
use tokio::io::{AsyncRead, AsyncWrite};
use tokio_tungstenite::tungstenite::protocol::frame::coding::CloseCode;
use tokio_tungstenite::tungstenite::protocol::CloseFrame;
use tokio_tungstenite::tungstenite::{Error as WsError, Message};
use tokio_tungstenite::WebSocketStream;
use tokio_util::sync::CancellationToken;

use crate::metrics::{Direction, DirectionCounters, FrameKind, Metrics, SessionOutcome};

/// Close reason sent to clients with code 1012 (service restart) during drain.
pub const DRAIN_CLOSE_REASON: &str = "edge draining";

/// How long a pump may take to send its own close after the session aborts.
const ABORT_GRACE: Duration = Duration::from_secs(1);

pub struct SessionCtx {
    /// Process-local counter; never a uid. Used only in logs.
    pub id: u64,
    pub close_timeout: Duration,
    /// Cancelled when the edge starts closing sessions during drain.
    pub drain: CancellationToken,
    /// Extra per-session delay after `drain` fires (spreads reconnects).
    pub drain_jitter: Duration,
    pub metrics: Arc<Metrics>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum PumpEnd {
    /// The source sent a close frame (relayed) and then ended.
    Closed,
    /// The source ended or failed without a close frame.
    Dropped,
    /// The session gave up waiting (close timeout).
    Aborted,
}

#[derive(Default, Clone, Copy, Debug)]
struct PumpStats {
    relayed: u64,
    discarded: u64,
}

const NOBODY: u8 = 0;
const CLIENT: u8 = 1;
const UPSTREAM: u8 = 2;

/// State shared by the two pumps of one session.
#[derive(Default)]
struct SessionFlags {
    /// Which side's close frame the edge received first (`CLIENT`/`UPSTREAM`).
    close_initiator: AtomicU8,
    /// The edge sent the client its drain close.
    drain_sent: AtomicBool,
    /// Bound on any close write (a client that stops reading cannot stall drain).
    close_timeout: Duration,
}

/// Deterministic spread of drain closes across `spread`, by session id.
pub fn drain_jitter(id: u64, spread: Duration) -> Duration {
    if spread.is_zero() {
        return Duration::ZERO;
    }
    // Fibonacci hashing gives an even spread for sequential ids.
    let frac = (id.wrapping_mul(0x9E37_79B9_7F4A_7C15) >> 11) as f64 / (1u64 << 53) as f64;
    spread.mul_f64(frac)
}

struct ActiveGuard<'a>(&'a Metrics);

impl Drop for ActiveGuard<'_> {
    fn drop(&mut self) {
        self.0.sessions_active.dec();
    }
}

/// What a pump hands back when its source is done.
struct PumpResult<Dst> {
    end: PumpEnd,
    stats: PumpStats,
    /// Returned so the session can flush a pending close echo before teardown.
    dst: Dst,
}

/// Relay one session until both sides are closed, one side drops, or a
/// close handshake times out.
pub async fn relay<C, U>(client: WebSocketStream<C>, upstream: WebSocketStream<U>, ctx: SessionCtx) -> SessionOutcome
where
    C: AsyncRead + AsyncWrite + Unpin + Send,
    U: AsyncRead + AsyncWrite + Unpin + Send,
{
    let metrics = ctx.metrics.clone();
    metrics.sessions_active.inc();
    let _active = ActiveGuard(&metrics);
    let started = Instant::now();

    let (c_tx, c_rx) = client.split();
    let (u_tx, u_rx) = upstream.split();
    let abort = CancellationToken::new();
    let flags = Arc::new(SessionFlags {
        close_timeout: ctx.close_timeout,
        ..Default::default()
    });

    let drain_fire = || {
        let drain = ctx.drain.clone();
        let jitter = ctx.drain_jitter;
        async move {
            drain.cancelled().await;
            tokio::time::sleep(jitter).await;
        }
    };
    // The session's own copy of the drain timer starts the close deadline
    // even if the upstream -> client pump is stuck writing to a client that
    // stopped reading.
    let session_drain = drain_fire();
    tokio::pin!(session_drain);
    let mut session_drain_fired = false;

    let c2u = pump(
        c_rx,
        u_tx,
        metrics.direction(Direction::ClientToUpstream),
        CLIENT,
        None::<std::future::Pending<()>>,
        abort.clone(),
        flags.clone(),
    );
    let u2c = pump(
        u_rx,
        c_tx,
        metrics.direction(Direction::UpstreamToClient),
        UPSTREAM,
        Some(drain_fire()),
        abort.clone(),
        flags.clone(),
    );
    tokio::pin!(c2u, u2c);

    let mut c2u_res = None;
    let mut u2c_res = None;
    let mut first_dropped: Option<Direction> = None;
    let mut deadline: Option<tokio::time::Instant> = None;
    let mut timed_out = false;
    let far = || tokio::time::Instant::now() + Duration::from_secs(365 * 24 * 3600);
    let no_close_yet = || flags.close_initiator.load(Ordering::SeqCst) == NOBODY;

    loop {
        tokio::select! {
            res = &mut c2u, if c2u_res.is_none() => {
                let dropped = res.end == PumpEnd::Dropped;
                c2u_res = Some(res);
                if dropped && no_close_yet() {
                    // Mirror an abnormal end: drop the other side too.
                    first_dropped = Some(Direction::ClientToUpstream);
                    break;
                }
                deadline.get_or_insert_with(|| tokio::time::Instant::now() + ctx.close_timeout);
            }
            res = &mut u2c, if u2c_res.is_none() => {
                let dropped = res.end == PumpEnd::Dropped;
                u2c_res = Some(res);
                if dropped && no_close_yet() {
                    first_dropped = Some(Direction::UpstreamToClient);
                    break;
                }
                deadline.get_or_insert_with(|| tokio::time::Instant::now() + ctx.close_timeout);
            }
            _ = &mut session_drain, if !session_drain_fired => {
                session_drain_fired = true;
                deadline.get_or_insert_with(|| tokio::time::Instant::now() + ctx.close_timeout);
            }
            _ = tokio::time::sleep_until(deadline.unwrap_or_else(far)), if deadline.is_some() => {
                timed_out = true;
                break;
            }
        }
        if c2u_res.is_some() && u2c_res.is_some() {
            break;
        }
    }

    if timed_out {
        // Let each unfinished pump send its own close (1001) before teardown.
        abort.cancel();
        let finish = async {
            if c2u_res.is_none() {
                c2u_res = Some((&mut c2u).await);
            }
            if u2c_res.is_none() {
                u2c_res = Some((&mut u2c).await);
            }
        };
        let _ = tokio::time::timeout(ABORT_GRACE, finish).await;
    }

    if first_dropped.is_none() {
        // A close echo may still be queued on a side whose close arrived
        // last; flush it so neither peer waits for an echo that never comes.
        let flush = async {
            if let Some(r) = c2u_res.as_mut() {
                let _ = r.dst.flush().await;
            }
            if let Some(r) = u2c_res.as_mut() {
                let _ = r.dst.flush().await;
            }
        };
        let _ = tokio::time::timeout(ABORT_GRACE, flush).await;
    }

    let outcome = if timed_out {
        SessionOutcome::CloseTimeout
    } else if let Some(dir) = first_dropped {
        match dir {
            Direction::ClientToUpstream => SessionOutcome::ClientDropped,
            Direction::UpstreamToClient => SessionOutcome::UpstreamDropped,
        }
    } else if flags.drain_sent.load(Ordering::SeqCst) {
        SessionOutcome::Drained
    } else if flags.close_initiator.load(Ordering::SeqCst) == CLIENT {
        SessionOutcome::ClientClosed
    } else {
        SessionOutcome::UpstreamClosed
    };

    let elapsed = started.elapsed();
    metrics.session_ended(outcome);
    metrics.session_seconds.observe(elapsed.as_secs_f64());
    let c = c2u_res.as_ref().map(|r| r.stats).unwrap_or_default();
    let u = u2c_res.as_ref().map(|r| r.stats).unwrap_or_default();
    tracing::info!(
        session_id = ctx.id,
        outcome = outcome.as_str(),
        duration_ms = elapsed.as_millis() as u64,
        c2u_relayed = c.relayed,
        c2u_discarded = c.discarded,
        u2c_relayed = u.relayed,
        u2c_discarded = u.discarded,
        "session ended"
    );
    outcome
}

/// Relay messages from `src` (side `me`) to `dst` until `src` closes or ends.
///
/// `drain`: when it resolves, send the destination a 1012 close (only the
/// upstream -> client pump gets one).
async fn pump<Src, Dst, D>(
    mut src: Src,
    mut dst: Dst,
    counters: DirectionCounters,
    me: u8,
    drain: Option<D>,
    abort: CancellationToken,
    flags: Arc<SessionFlags>,
) -> PumpResult<Dst>
where
    Src: Stream<Item = Result<Message, WsError>> + Unpin,
    Dst: Sink<Message, Error = WsError> + Unpin,
    D: Future<Output = ()>,
{
    let mut stats = PumpStats::default();
    // False once a close was sent to `dst` or `dst` failed: data can no
    // longer be relayed and is counted as discarded instead.
    let mut dst_open = true;
    let mut drain_done = drain.is_none();
    let drain = async move {
        match drain {
            Some(d) => d.await,
            None => std::future::pending().await,
        }
    };
    tokio::pin!(drain);

    loop {
        let next = tokio::select! {
            biased;
            _ = abort.cancelled() => {
                if dst_open {
                    let frame = CloseFrame { code: CloseCode::Away, reason: "edge closing".into() };
                    let _ = tokio::time::timeout(ABORT_GRACE, dst.send(Message::Close(Some(frame)))).await;
                }
                return PumpResult { end: PumpEnd::Aborted, stats, dst };
            }
            // Relay what upstream already sent before the drain close.
            m = src.next() => m,
            _ = &mut drain, if !drain_done => {
                drain_done = true;
                if dst_open {
                    dst_open = false;
                    let close = dst.send(Message::Close(Some(client_drain_frame())));
                    if let Ok(Ok(())) = tokio::time::timeout(flags.close_timeout, close).await {
                        flags.drain_sent.store(true, Ordering::SeqCst);
                    }
                }
                continue;
            }
        };

        let msg = match next {
            Some(Ok(msg)) => msg,
            Some(Err(_)) | None => {
                if me == CLIENT && flags.drain_sent.load(Ordering::SeqCst) {
                    // The client went away after the edge's drain close
                    // without echoing it. The edge caused this end, so give
                    // listen a clean close instead of mirroring a drop.
                    if dst_open {
                        let close = dst.send(Message::Close(Some(upstream_drain_frame())));
                        let _ = tokio::time::timeout(flags.close_timeout, close).await;
                    }
                    return PumpResult {
                        end: PumpEnd::Closed,
                        stats,
                        dst,
                    };
                }
                return PumpResult {
                    end: PumpEnd::Dropped,
                    stats,
                    dst,
                };
            }
        };

        let kind = match msg {
            Message::Binary(ref b) => (FrameKind::Binary, b.len()),
            Message::Text(ref t) => (FrameKind::Text, t.len()),
            Message::Close(frame) => {
                let _ = flags
                    .close_initiator
                    .compare_exchange(NOBODY, me, Ordering::SeqCst, Ordering::SeqCst);
                if dst_open {
                    // The client's echo of the edge's drain close becomes 1001
                    // for listen (see the module docs); every other close is
                    // relayed as received.
                    let echoes_drain = me == CLIENT
                        && flags.drain_sent.load(Ordering::SeqCst)
                        && frame.as_ref().is_none_or(|f| f.code == CloseCode::Restart);
                    let frame = if echoes_drain {
                        Some(upstream_drain_frame())
                    } else {
                        frame
                    };
                    let _ = tokio::time::timeout(flags.close_timeout, dst.send(Message::Close(frame))).await;
                }
                // tungstenite queued the close echo to `src`; it is written
                // on the next poll of that socket. Poll once without waiting
                // so the echo goes out now (the session flushes again at the
                // end if the socket was busy). Do not wait for TCP EOF:
                // listen keeps its socket open while it finalizes.
                let _ = tokio::time::timeout(Duration::ZERO, src.next()).await;
                return PumpResult {
                    end: PumpEnd::Closed,
                    stats,
                    dst,
                };
            }
            // Hop-by-hop; tungstenite already answered pings.
            Message::Ping(_) | Message::Pong(_) | Message::Frame(_) => continue,
        };

        if dst_open && dst.send(msg).await.is_ok() {
            counters.record(kind.0, kind.1);
            stats.relayed += 1;
        } else {
            dst_open = false;
            counters.discarded.inc();
            stats.discarded += 1;
        }
    }
}

/// What the client gets on drain: 1012, reconnect.
fn client_drain_frame() -> CloseFrame {
    CloseFrame {
        code: CloseCode::Restart,
        reason: DRAIN_CLOSE_REASON.into(),
    }
}

/// What listen gets for a drained session: 1001, an ordinary close that
/// keeps the conversation in progress for the reconnect.
fn upstream_drain_frame() -> CloseFrame {
    CloseFrame {
        code: CloseCode::Away,
        reason: DRAIN_CLOSE_REASON.into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn jitter_is_within_spread_and_spreads() {
        let spread = Duration::from_secs(10);
        let mut buckets = [0u32; 10];
        for id in 0..1000u64 {
            let j = drain_jitter(id, spread);
            assert!(j < spread);
            buckets[(j.as_secs_f64()) as usize] += 1;
        }
        assert!(buckets.iter().all(|&b| b > 50), "uneven spread: {buckets:?}");
        assert_eq!(drain_jitter(7, Duration::ZERO), Duration::ZERO);
    }
}
