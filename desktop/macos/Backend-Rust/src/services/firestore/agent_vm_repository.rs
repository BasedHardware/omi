use super::*;

impl FirestoreService {
    pub(crate) async fn get_agent_vm(
        &self,
        uid: &str,
    ) -> Result<Option<crate::models::agent::AgentVm>, Box<dyn std::error::Error + Send + Sync>>
    {
        let doc = self.get_user_document(uid).await?;
        let empty = json!({});
        let fields = doc.get("fields").unwrap_or(&empty);

        let agent_vm = fields.get("agentVm");
        if agent_vm.is_none() {
            return Ok(None);
        }

        let map_value = agent_vm
            .and_then(|v| v.get("mapValue"))
            .and_then(|v| v.get("fields"));

        if map_value.is_none() {
            return Ok(None);
        }

        let Some(f) = map_value else {
            return Ok(None);
        };

        let vm_name = f
            .get("vmName")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        if vm_name.is_empty() {
            return Ok(None);
        }

        let zone = f
            .get("zone")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .unwrap_or("us-central1-a")
            .to_string();

        let ip = f
            .get("ip")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());

        let status_str = f
            .get("status")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .unwrap_or("provisioning");

        let status = match status_str {
            "ready" => crate::models::agent::AgentVmStatus::Ready,
            "stopped" => crate::models::agent::AgentVmStatus::Stopped,
            "error" => crate::models::agent::AgentVmStatus::Error,
            _ => crate::models::agent::AgentVmStatus::Provisioning,
        };

        let auth_token = f
            .get("authToken")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let created_at = f
            .get("createdAt")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let last_query_at = f
            .get("lastQueryAt")
            .and_then(|v| v.get("stringValue"))
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());

        Ok(Some(crate::models::agent::AgentVm {
            vm_name,
            zone,
            ip,
            status,
            auth_token,
            created_at,
            last_query_at,
        }))
    }

    /// Set agent VM info on a user's document
    pub(crate) async fn set_agent_vm(
        &self,
        uid: &str,
        vm_name: &str,
        zone: &str,
        ip: Option<&str>,
        status: crate::models::agent::AgentVmStatus,
        auth_token: &str,
        created_at: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let mut vm_fields = json!({
            "vmName": {"stringValue": vm_name},
            "zone": {"stringValue": zone},
            "status": {"stringValue": status.to_string()},
            "authToken": {"stringValue": auth_token},
            "createdAt": {"stringValue": created_at}
        });

        if let Some(ip_val) = ip {
            vm_fields["ip"] = json!({"stringValue": ip_val});
        }

        let fields = json!({
            "agentVm": {
                "mapValue": {
                    "fields": vm_fields
                }
            }
        });

        self.update_user_fields(uid, fields, &["agentVm"]).await
    }

    /// Delete the agentVm field from a user's document.
    /// Used when the GCE VM no longer exists in GCP.
    pub(crate) async fn delete_agent_vm(
        &self,
        uid: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // Omitting agentVm from the body while including it in the update mask
        // causes Firestore to delete the field.
        self.update_user_fields(uid, json!({}), &["agentVm"]).await
    }
}
