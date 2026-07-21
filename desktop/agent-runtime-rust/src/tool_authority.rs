use rx4::ToolCall;
use tokio::sync::watch;

#[derive(Clone)]
pub(crate) struct RunningQuery {
    pub(crate) cancel: watch::Sender<bool>,
    pub(crate) owner_id: String,
    pub(crate) session_id: String,
    pub(crate) run_id: String,
    pub(crate) attempt_id: String,
    pub(crate) profile_generation: u64,
    pub(crate) surface_kind: String,
}

pub(crate) struct ToolRequest {
    pub(crate) request_id: String,
    pub(crate) client_id: String,
    pub(crate) call: ToolCall,
}
