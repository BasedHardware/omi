//! listen-edge: the Rust websocket edge in front of backend-listen.
//!
//! Plan D (`projects/backend-target-architecture/plan-d-realtime-gateway.md`):
//! - D1, passthrough: the edge accepts `/v4/listen` websockets, opens the same
//!   path and query on the upstream listen service, and relays messages byte
//!   for byte in both directions.
//! - D2, shadow: listen mirrors a cohort's raw frames to `/v1/shadow`; the
//!   edge decodes them and runs listen's VAD gate, and compares decisions with
//!   listen's. No provider legs, nothing reaches the client.
//!
//! It is not deployed.
pub mod codec;
pub mod config;
pub mod gate;
pub mod metrics;
pub mod server;
pub mod session;
pub mod shadow;
pub mod silero;
