//! listen-edge: the Rust websocket edge in front of backend-listen.
//!
//! D1 scope (plan D, `projects/backend-target-architecture/plan-d-realtime-gateway.md`):
//! passthrough only. The edge accepts `/v4/listen` websockets, opens the same
//! path and query on the upstream listen service, and relays messages
//! byte for byte in both directions. It does no decode, no VAD and opens no
//! provider legs. It is not deployed.
pub mod config;
pub mod metrics;
pub mod server;
pub mod session;
