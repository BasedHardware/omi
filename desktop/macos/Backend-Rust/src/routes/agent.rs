// Agent VM routes
// Endpoints: /v2/agent/*

use axum::{
    extract::State,
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};

use crate::auth::{AuthUser, PaywalledAuthUser};
use crate::models::agent::{AgentStatusResponse, AgentVmStatus, ProvisionAgentResponse};
use crate::AppState;

fn local_harness_agent_disabled() -> bool {
    std::env::var("ENVIRONMENT").as_deref() == Ok("local-dev-harness")
}

/// Read the public NAT IP from a GCE instance response.
///
/// Phase 1 keeps ONE_TO_ONE_NAT: agent-proxy (omi-prod-vpc-1) and desktop clients
/// still reach VMs on the `default` VPC via the public IP. Private-only VMs are
/// deferred until desktop upload/sync is proxied and cross-VPC reachability exists.
fn extract_agent_vm_ip(instance: &serde_json::Value) -> Result<String, String> {
    instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
        .as_str()
        .filter(|ip| !ip.trim().is_empty())
        .map(str::to_string)
        .ok_or_else(|| "GCE instance response missing public natIP".to_string())
}

/// POST /v2/agent/provision
/// Idempotent — if user already has a VM, returns existing info.
/// Creates a GCE VM from the omi-agent image family for this user.
async fn provision_agent_vm(
    State(state): State<AppState>,
    user: PaywalledAuthUser,
) -> Result<Json<ProvisionAgentResponse>, StatusCode> {
    if local_harness_agent_disabled() {
        tracing::debug!("Agent VM provision disabled in local dev harness");
        return Err(StatusCode::SERVICE_UNAVAILABLE);
    }
    let user: AuthUser = user.into();
    tracing::info!("Agent VM provision request for user {}", user.uid);

    // 1. Check if user already has a VM
    match state.firestore.get_agent_vm(&user.uid).await {
        Ok(Some(vm)) => {
            tracing::info!(
                "User {} already has agent VM: {} (status: {})",
                user.uid,
                vm.vm_name,
                vm.status
            );
            return Ok(Json(ProvisionAgentResponse {
                status: "exists".to_string(),
                vm_name: vm.vm_name,
                ip: vm.ip,
                auth_token: vm.auth_token,
                agent_status: vm.status,
            }));
        }
        Ok(None) => {
            tracing::info!(
                "No existing agent VM for user {}, provisioning...",
                user.uid
            );
        }
        Err(e) => {
            tracing::error!("Failed to check existing agent VM: {}", e);
            return Err(StatusCode::INTERNAL_SERVER_ERROR);
        }
    }

    // 2. Generate VM name and auth token
    // Use first 12 chars of uid to keep VM name reasonable length
    let uid_prefix = if user.uid.len() > 12 {
        &user.uid[..12]
    } else {
        &user.uid
    };
    let vm_name = format!("omi-agent-{}", uid_prefix.to_lowercase());
    let auth_token = format!("omi-{}", uuid::Uuid::new_v4());

    // 3. Write provisioning status to Firestore first (claim the slot)
    let now = chrono::Utc::now().to_rfc3339();
    if let Err(e) = state
        .firestore
        .set_agent_vm(
            &user.uid,
            &vm_name,
            "us-central1-a",
            None, // no IP yet
            AgentVmStatus::Provisioning,
            &auth_token,
            &now,
        )
        .await
    {
        tracing::error!("Failed to write agent VM to Firestore: {}", e);
        return Err(StatusCode::INTERNAL_SERVER_ERROR);
    }

    // 4. Create the GCE VM asynchronously
    // We return immediately with "provisioning" status.
    // The VM creation runs in background and updates Firestore when done.
    let gce_project = state.config.gce_project_id.clone().ok_or_else(|| {
        tracing::error!("GCE_PROJECT_ID / FIREBASE_PROJECT_ID not set — cannot provision agent VM");
        StatusCode::INTERNAL_SERVER_ERROR
    })?;
    let gce_source_image = state.config.gce_source_image.clone().ok_or_else(|| {
        tracing::error!(
            "GCE_SOURCE_IMAGE not set and no project ID to derive it — cannot provision agent VM"
        );
        StatusCode::INTERNAL_SERVER_ERROR
    })?;
    let agent_gcs_bucket = state.config.agent_gcs_bucket.clone().ok_or_else(|| {
        tracing::error!("AGENT_GCS_BUCKET not set — cannot provision agent VM");
        StatusCode::INTERNAL_SERVER_ERROR
    })?;
    let firestore = state.firestore.clone();
    let uid = user.uid.clone();
    let vm_name_clone = vm_name.clone();
    let auth_token_clone = auth_token.clone();
    tokio::spawn(async move {
        tracing::info!("Starting GCE VM creation: {}", vm_name_clone);

        match create_gce_vm(
            &firestore,
            &vm_name_clone,
            &auth_token_clone,
            &gce_project,
            &gce_source_image,
            &agent_gcs_bucket,
        )
        .await
        {
            Ok(ip) => {
                tracing::info!("VM {} created with IP {}", vm_name_clone, ip);
                let now = chrono::Utc::now().to_rfc3339();
                if let Err(e) = firestore
                    .set_agent_vm(
                        &uid,
                        &vm_name_clone,
                        "us-central1-a",
                        Some(&ip),
                        AgentVmStatus::Ready,
                        &auth_token_clone,
                        &now,
                    )
                    .await
                {
                    tracing::error!("Failed to update VM status to ready: {}", e);
                }
            }
            Err(e) => {
                tracing::error!("Failed to create VM {}: {}", vm_name_clone, e);
                let now = chrono::Utc::now().to_rfc3339();
                if let Err(e2) = firestore
                    .set_agent_vm(
                        &uid,
                        &vm_name_clone,
                        "us-central1-a",
                        None,
                        AgentVmStatus::Error,
                        &auth_token_clone,
                        &now,
                    )
                    .await
                {
                    tracing::error!("Failed to update VM status to error: {}", e2);
                }
            }
        }
    });

    Ok(Json(ProvisionAgentResponse {
        status: "provisioning".to_string(),
        vm_name,
        ip: None,
        auth_token,
        agent_status: AgentVmStatus::Provisioning,
    }))
}

/// GET /v2/agent/status
/// Returns the current agent VM status for the authenticated user.
/// If the VM self-stopped (idle timeout), detects it via GCE API and restarts it.
async fn get_agent_status(
    State(state): State<AppState>,
    user: PaywalledAuthUser,
) -> Result<Json<Option<AgentStatusResponse>>, StatusCode> {
    if local_harness_agent_disabled() {
        return Ok(Json(None));
    }
    let user: AuthUser = user.into();
    tracing::info!("Agent VM status request for user {}", user.uid);

    match state.firestore.get_agent_vm(&user.uid).await {
        Ok(Some(vm)) => {
            // If Firestore says "ready", "error", or "stopped", verify the VM is actually running.
            // The VM may have self-stopped due to idle timeout and be restartable.
            if vm.status == AgentVmStatus::Ready
                || vm.status == AgentVmStatus::Error
                || vm.status == AgentVmStatus::Stopped
            {
                let gce_project_id = match &state.config.gce_project_id {
                    Some(p) => p.clone(),
                    None => {
                        tracing::warn!("GCE_PROJECT_ID not set — returning Firestore status without GCE verification");
                        return Ok(Json(Some(vm)));
                    }
                };
                match check_gce_instance_status(
                    &state.firestore,
                    &vm.vm_name,
                    &vm.zone,
                    &gce_project_id,
                )
                .await
                {
                    Ok(gce_status) if gce_status == "TERMINATED" || gce_status == "STOPPED" => {
                        tracing::info!(
                            "VM {} is {} (idle auto-stop), restarting...",
                            vm.vm_name,
                            gce_status
                        );
                        // Update Firestore to reflect stopped state
                        let now = chrono::Utc::now().to_rfc3339();
                        let _ = state
                            .firestore
                            .set_agent_vm(
                                &user.uid,
                                &vm.vm_name,
                                &vm.zone,
                                None,
                                AgentVmStatus::Provisioning,
                                &vm.auth_token,
                                &now,
                            )
                            .await;

                        // Start the VM in the background
                        let firestore = state.firestore.clone();
                        let uid = user.uid.clone();
                        let vm_name = vm.vm_name.clone();
                        let zone = vm.zone.clone();
                        let auth_token = vm.auth_token.clone();
                        let gce_project = gce_project_id.clone();

                        tokio::spawn(async move {
                            match start_stopped_vm(&firestore, &vm_name, &zone, &gce_project).await
                            {
                                Ok(ip) => {
                                    tracing::info!("VM {} restarted with IP {}", vm_name, ip);
                                    let now = chrono::Utc::now().to_rfc3339();
                                    let _ = firestore
                                        .set_agent_vm(
                                            &uid,
                                            &vm_name,
                                            &zone,
                                            Some(&ip),
                                            AgentVmStatus::Ready,
                                            &auth_token,
                                            &now,
                                        )
                                        .await;
                                }
                                Err(e) => {
                                    tracing::error!("Failed to restart VM {}: {}", vm_name, e);
                                    let now = chrono::Utc::now().to_rfc3339();
                                    let _ = firestore
                                        .set_agent_vm(
                                            &uid,
                                            &vm_name,
                                            &zone,
                                            None,
                                            AgentVmStatus::Error,
                                            &auth_token,
                                            &now,
                                        )
                                        .await;
                                }
                            }
                        });

                        // Return "provisioning" so the client polls
                        return Ok(Json(Some(AgentStatusResponse {
                            ip: None,
                            status: AgentVmStatus::Provisioning,
                            ..vm
                        })));
                    }
                    Ok(gce_status) if gce_status == "NOT_FOUND" => {
                        tracing::warn!(
                            "VM {} no longer exists in GCP — clearing Firestore record",
                            vm.vm_name
                        );
                        let _ = state.firestore.delete_agent_vm(&user.uid).await;
                        return Ok(Json(None));
                    }
                    Ok(gce_status)
                        if gce_status == "RUNNING"
                            && (vm.status == AgentVmStatus::Error
                                || vm.status == AgentVmStatus::Stopped) =>
                    {
                        // VM is actually running but Firestore is stale — recover
                        tracing::info!(
                            "VM {} is RUNNING but Firestore says {:?}, recovering...",
                            vm.vm_name,
                            vm.status
                        );
                        // Get fresh IP and update Firestore
                        let firestore = state.firestore.clone();
                        let uid = user.uid.clone();
                        let vm_name = vm.vm_name.clone();
                        let zone = vm.zone.clone();
                        let auth_token = vm.auth_token.clone();
                        let gce_project = gce_project_id.clone();

                        tokio::spawn(async move {
                            let project = &gce_project;
                            let instance_url = format!(
                                "https://compute.googleapis.com/compute/v1/projects/{}/zones/{}/instances/{}",
                                project, zone, vm_name
                            );
                            if let Ok(resp) = firestore
                                .build_compute_request(reqwest::Method::GET, &instance_url)
                                .await
                            {
                                if let Ok(resp) = resp.send().await {
                                    if let Ok(instance) = resp.json::<serde_json::Value>().await {
                                        let ip = match extract_agent_vm_ip(&instance) {
                                            Ok(ip) => ip,
                                            Err(e) => {
                                                tracing::warn!(
                                                    "Could not recover public IP for VM {}: {}",
                                                    vm_name,
                                                    e
                                                );
                                                return;
                                            }
                                        };
                                        let now = chrono::Utc::now().to_rfc3339();
                                        let _ = firestore
                                            .set_agent_vm(
                                                &uid,
                                                &vm_name,
                                                &zone,
                                                Some(&ip),
                                                AgentVmStatus::Ready,
                                                &auth_token,
                                                &now,
                                            )
                                            .await;
                                        tracing::info!("VM {} recovered — ip={}", vm_name, ip);
                                    }
                                }
                            }
                        });

                        // Return provisioning so client polls
                        return Ok(Json(Some(AgentStatusResponse {
                            ip: None,
                            status: AgentVmStatus::Provisioning,
                            ..vm
                        })));
                    }
                    Ok(gce_status) => {
                        tracing::debug!("VM {} GCE status: {}", vm.vm_name, gce_status);
                    }
                    Err(e) => {
                        // If we can't reach GCE, return Firestore data as-is
                        tracing::warn!("Could not check GCE status for {}: {}", vm.vm_name, e);
                    }
                }
            }

            Ok(Json(Some(vm)))
        }
        Ok(None) => Ok(Json(None)),
        Err(e) => {
            tracing::error!("Failed to get agent VM status: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

/// Check the actual GCE instance status (RUNNING, TERMINATED, STOPPED, etc.)
async fn check_gce_instance_status(
    firestore: &crate::services::FirestoreService,
    vm_name: &str,
    zone: &str,
    project: &str,
) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    let url = format!(
        "https://compute.googleapis.com/compute/v1/projects/{}/zones/{}/instances/{}",
        project, zone, vm_name
    );

    let resp = firestore
        .build_compute_request(reqwest::Method::GET, &url)
        .await?
        .send()
        .await?;

    if resp.status() == reqwest::StatusCode::NOT_FOUND {
        return Ok("NOT_FOUND".to_string());
    }

    let instance: serde_json::Value = resp.json().await?;
    let status = instance["status"].as_str().unwrap_or("UNKNOWN").to_string();
    Ok(status)
}

/// Start a stopped/terminated GCE VM and wait for it to get an IP.
async fn start_stopped_vm(
    firestore: &crate::services::FirestoreService,
    vm_name: &str,
    zone: &str,
    project: &str,
) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    // Call GCE start API
    let start_url = format!(
        "https://compute.googleapis.com/compute/v1/projects/{}/zones/{}/instances/{}/start",
        project, zone, vm_name
    );

    let response = firestore
        .build_compute_request(reqwest::Method::POST, &start_url)
        .await?
        .header("Content-Length", "0")
        .send()
        .await?;

    if !response.status().is_success() {
        let error_text = response.text().await?;
        return Err(format!("GCE start failed: {}", error_text).into());
    }

    let op: serde_json::Value = response.json().await?;
    let op_name = op["name"]
        .as_str()
        .ok_or("Missing operation name in GCE start response")?;

    // Poll operation until done (max ~2 minutes)
    let op_url = format!(
        "https://compute.googleapis.com/compute/v1/projects/{}/zones/{}/operations/{}",
        project, zone, op_name
    );

    for _ in 0..24 {
        tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;

        let status_resp = firestore
            .build_compute_request(reqwest::Method::GET, &op_url)
            .await?
            .send()
            .await?;

        let status: serde_json::Value = status_resp.json().await?;
        if status["status"].as_str() == Some("DONE") {
            if let Some(error) = status.get("error") {
                return Err(format!("GCE start operation failed: {}", error).into());
            }
            break;
        }
    }

    // Get the VM's (possibly new) public NAT IP. Phase 1 keeps public NAT so
    // agent-proxy and desktop can reach VMs across VPCs.
    let instance_url = format!(
        "https://compute.googleapis.com/compute/v1/projects/{}/zones/{}/instances/{}",
        project, zone, vm_name
    );

    let instance_resp = firestore
        .build_compute_request(reqwest::Method::GET, &instance_url)
        .await?
        .send()
        .await?;

    let instance: serde_json::Value = instance_resp.json().await?;
    let ip = extract_agent_vm_ip(&instance)?;

    Ok(ip)
}

/// Build the GCE instances.insert request body for a new agent VM.
///
/// Phase 1 keeps ONE_TO_ONE_NAT (public IP) and tags VMs `omi-agent-vm` so a
/// later source-restricted / private-network cutover can target them. Do not
/// remove accessConfigs until desktop upload/sync is proxied and proxy↔VM
/// private reachability exists (VPC peering or shared VPC).
fn build_gce_vm_insert_body(
    vm_name: &str,
    auth_token: &str,
    source_image: &str,
    gcs_bucket: &str,
    zone: &str,
) -> serde_json::Value {
    // Startup script: pull the real startup.sh from GCS and run it.
    // All logic lives in GCS so it can be updated without reprovisioning VMs.
    let startup_script = format!(
        "#!/bin/bash\ncurl -sf https://storage.googleapis.com/{}/startup.sh -o /tmp/omi-startup.sh \\\n  && bash /tmp/omi-startup.sh\n",
        gcs_bucket
    );

    serde_json::json!({
        "name": vm_name,
        "machineType": format!("zones/{}/machineTypes/e2-small", zone),
        "disks": [{
            "boot": true,
            "autoDelete": true,
            "initializeParams": {
                "sourceImage": source_image,
                "diskSizeGb": "50",
                "diskType": format!("zones/{}/diskTypes/pd-balanced", zone)
            }
        }],
        "networkInterfaces": [{
            "network": "global/networks/default",
            "accessConfigs": [{
                "type": "ONE_TO_ONE_NAT",
                "name": "External NAT"
            }]
        }],
        "tags": {
            "items": ["omi-agent-vm"]
        },
        "metadata": {
            "items": [{
                "key": "startup-script",
                "value": startup_script
            }, {
                "key": "auth-token",
                "value": auth_token
            }]
        }
    })
}

/// Create a GCE VM from the omi-agent image family.
/// Returns the public NAT IP of the created VM.
async fn create_gce_vm(
    firestore: &crate::services::FirestoreService,
    vm_name: &str,
    auth_token: &str,
    project: &str,
    source_image: &str,
    gcs_bucket: &str,
) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    let zone = "us-central1-a";

    // GCE instances.insert REST API
    let url = format!(
        "https://compute.googleapis.com/compute/v1/projects/{}/zones/{}/instances",
        project, zone
    );

    let body = build_gce_vm_insert_body(vm_name, auth_token, source_image, gcs_bucket, zone);

    // Use Firestore's authenticated request builder (same service account)
    let response = firestore
        .build_compute_request(reqwest::Method::POST, &url)
        .await?
        .json(&body)
        .send()
        .await?;

    if !response.status().is_success() {
        let error_text = response.text().await?;
        return Err(format!("GCE insert failed: {}", error_text).into());
    }

    // The insert returns an operation. Wait for it to complete.
    let op: serde_json::Value = response.json().await?;
    let op_name = op["name"]
        .as_str()
        .ok_or("Missing operation name in GCE response")?;

    // Poll the operation until done (max ~2 minutes)
    let op_url = format!(
        "https://compute.googleapis.com/compute/v1/projects/{}/zones/{}/operations/{}",
        project, zone, op_name
    );

    for _ in 0..24 {
        tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;

        let status_resp = firestore
            .build_compute_request(reqwest::Method::GET, &op_url)
            .await?
            .send()
            .await?;

        let status: serde_json::Value = status_resp.json().await?;
        if status["status"].as_str() == Some("DONE") {
            if let Some(error) = status.get("error") {
                return Err(format!("GCE operation failed: {}", error).into());
            }
            break;
        }
    }

    // Get the VM's public NAT IP (phase 1 connectivity model).
    let instance_url = format!(
        "https://compute.googleapis.com/compute/v1/projects/{}/zones/{}/instances/{}",
        project, zone, vm_name
    );

    let instance_resp = firestore
        .build_compute_request(reqwest::Method::GET, &instance_url)
        .await?
        .send()
        .await?;

    let instance: serde_json::Value = instance_resp.json().await?;
    let ip = extract_agent_vm_ip(&instance)?;

    Ok(ip)
}

// ============================================================================
// Router
// ============================================================================

pub fn agent_routes() -> Router<AppState> {
    Router::new()
        .route("/v2/agent/provision", post(provision_agent_vm))
        .route("/v2/agent/status", get(get_agent_status))
}

#[cfg(test)]
mod contract_tests {
    use super::{build_gce_vm_insert_body, extract_agent_vm_ip};

    #[test]
    fn contract_create_gce_vm_provision_json_keeps_public_nat_and_firewall_tag() {
        let body = build_gce_vm_insert_body(
            "omi-agent-contract",
            "omi-test-token",
            "projects/test/global/images/family/omi-agent",
            "omi-agent-artifacts",
            "us-central1-a",
        );

        let network = &body["networkInterfaces"][0];
        assert_eq!(network["network"], "global/networks/default");
        assert_eq!(
            network["accessConfigs"][0]["type"], "ONE_TO_ONE_NAT",
            "phase 1 must keep public NAT until private cutover prerequisites land"
        );
        assert_eq!(network["accessConfigs"][0]["name"], "External NAT");

        let tags = body["tags"]["items"]
            .as_array()
            .expect("provision body must include network tags");
        assert!(
            tags.iter().any(|tag| tag == "omi-agent-vm"),
            "provision body must tag VMs for omi-agent-vm firewall policy"
        );
    }

    #[test]
    fn contract_agent_vm_ip_uses_public_nat_ip() {
        let instance = serde_json::json!({
            "networkInterfaces": [{
                "networkIP": "10.128.0.42",
                "accessConfigs": [{"natIP": "203.0.113.10"}]
            }]
        });

        assert_eq!(extract_agent_vm_ip(&instance).unwrap(), "203.0.113.10");

        let private_only = serde_json::json!({
            "networkInterfaces": [{
                "networkIP": "10.128.0.42"
            }]
        });
        assert!(
            extract_agent_vm_ip(&private_only).is_err(),
            "phase 1 readiness must require public natIP (not private-only)"
        );
    }
}
