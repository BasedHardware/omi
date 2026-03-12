// Agent VM models

use serde::{Deserialize, Serialize};

/// Agent VM status
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum AgentVmStatus {
    Provisioning,
    Ready,
    Stopped,
    Error,
}

impl std::fmt::Display for AgentVmStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AgentVmStatus::Provisioning => write!(f, "provisioning"),
            AgentVmStatus::Ready => write!(f, "ready"),
            AgentVmStatus::Stopped => write!(f, "stopped"),
            AgentVmStatus::Error => write!(f, "error"),
        }
    }
}

/// Agent VM info stored in Firestore on the user document
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentVm {
    pub vm_name: String,
    pub zone: String,
    pub ip: Option<String>,
    pub status: AgentVmStatus,
    pub auth_token: String,
    pub created_at: String,
    pub last_query_at: Option<String>,
}

/// Response for POST /v2/agent/provision
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProvisionAgentResponse {
    pub status: String,
    pub vm_name: String,
    pub ip: Option<String>,
    pub auth_token: String,
    pub agent_status: AgentVmStatus,
}

/// Response for GET /v2/agent/status
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentStatusResponse {
    pub vm_name: String,
    pub zone: String,
    pub ip: Option<String>,
    pub status: AgentVmStatus,
    pub auth_token: String,
    pub created_at: String,
    pub last_query_at: Option<String>,
}
