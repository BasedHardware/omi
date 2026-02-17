// Agent VM routes
// Endpoints: /v2/agent/*

use axum::{
    extract::State,
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};

use crate::auth::AuthUser;
use crate::models::agent::{AgentStatusResponse, AgentVmStatus, ProvisionAgentResponse};
use crate::AppState;

/// POST /v2/agent/provision
/// Idempotent — if user already has a VM, returns existing info.
/// Creates a GCE VM from the omi-agent image family for this user.
async fn provision_agent_vm(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<ProvisionAgentResponse>, StatusCode> {
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
            tracing::info!("No existing agent VM for user {}, provisioning...", user.uid);
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
    let firestore = state.firestore.clone();
    let uid = user.uid.clone();
    let vm_name_clone = vm_name.clone();
    let auth_token_clone = auth_token.clone();
    let anthropic_key = state.config.agent_anthropic_api_key.clone();
    let gemini_key = state.config.gemini_api_key.clone();

    tokio::spawn(async move {
        tracing::info!("Starting GCE VM creation: {}", vm_name_clone);

        match create_gce_vm(
            &firestore,
            &vm_name_clone,
            &auth_token_clone,
            anthropic_key.as_deref(),
            gemini_key.as_deref(),
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
    user: AuthUser,
) -> Result<Json<Option<AgentStatusResponse>>, StatusCode> {
    tracing::info!("Agent VM status request for user {}", user.uid);

    match state.firestore.get_agent_vm(&user.uid).await {
        Ok(Some(vm)) => {
            // If Firestore says "ready", verify the VM is actually running.
            // The VM may have self-stopped due to idle timeout.
            if vm.status == AgentVmStatus::Ready {
                match check_gce_instance_status(&state.firestore, &vm.vm_name, &vm.zone).await {
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

                        tokio::spawn(async move {
                            match start_stopped_vm(&firestore, &vm_name, &zone).await {
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
                            vm_name: vm.vm_name,
                            zone: vm.zone,
                            ip: None,
                            status: AgentVmStatus::Provisioning,
                            auth_token: vm.auth_token,
                            created_at: vm.created_at,
                            last_query_at: vm.last_query_at,
                        })));
                    }
                    Ok(gce_status) => {
                        tracing::debug!("VM {} GCE status: {}", vm.vm_name, gce_status);
                    }
                    Err(e) => {
                        // If we can't reach GCE, return Firestore data as-is
                        tracing::warn!(
                            "Could not check GCE status for {}: {}",
                            vm.vm_name,
                            e
                        );
                    }
                }
            }

            Ok(Json(Some(AgentStatusResponse {
                vm_name: vm.vm_name,
                zone: vm.zone,
                ip: vm.ip,
                status: vm.status,
                auth_token: vm.auth_token,
                created_at: vm.created_at,
                last_query_at: vm.last_query_at,
            })))
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
) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    let project = "based-hardware";
    let url = format!(
        "https://compute.googleapis.com/compute/v1/projects/{}/zones/{}/instances/{}",
        project, zone, vm_name
    );

    let resp = firestore
        .build_compute_request(reqwest::Method::GET, &url)
        .await?
        .send()
        .await?;

    let instance: serde_json::Value = resp.json().await?;
    let status = instance["status"]
        .as_str()
        .unwrap_or("UNKNOWN")
        .to_string();
    Ok(status)
}

/// Start a stopped/terminated GCE VM and wait for it to get an IP.
async fn start_stopped_vm(
    firestore: &crate::services::FirestoreService,
    vm_name: &str,
    zone: &str,
) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    let project = "based-hardware";

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

    // Get the VM's (possibly new) external IP
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
    let ip = instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
        .as_str()
        .unwrap_or("unknown")
        .to_string();

    Ok(ip)
}

/// Create a GCE VM from the omi-agent image family.
/// Returns the external IP of the created VM.
async fn create_gce_vm(
    firestore: &crate::services::FirestoreService,
    vm_name: &str,
    auth_token: &str,
    anthropic_key: Option<&str>,
    gemini_key: Option<&str>,
) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    let project = "based-hardware";
    let zone = "us-central1-a";

    // Build startup script that starts the agent server
    let mut startup_script = format!(
        r#"#!/bin/bash
cd /home/matthewdi/omi-agent
export AUTH_TOKEN='{}'
export DB_PATH='data/omi.db'
"#,
        auth_token
    );
    if let Some(key) = anthropic_key {
        startup_script.push_str(&format!("export ANTHROPIC_API_KEY='{}'\n", key));
    }
    if let Some(key) = gemini_key {
        startup_script.push_str(&format!("export GEMINI_API_KEY='{}'\n", key));
    }
    startup_script.push_str("nohup node agent.mjs --serve > /tmp/agent-server.log 2>&1 &\n");

    // GCE instances.insert REST API
    let url = format!(
        "https://compute.googleapis.com/compute/v1/projects/{}/zones/{}/instances",
        project, zone
    );

    let body = serde_json::json!({
        "name": vm_name,
        "machineType": format!("zones/{}/machineTypes/e2-small", zone),
        "disks": [{
            "boot": true,
            "autoDelete": true,
            "initializeParams": {
                "sourceImage": format!("projects/{}/global/images/family/omi-agent", project),
                "diskSizeGb": "50",
                "diskType": format!("zones/{}/diskTypes/pd-ssd", zone)
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
            "items": ["http-server"]
        },
        "metadata": {
            "items": [{
                "key": "startup-script",
                "value": startup_script
            }]
        }
    });

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

    // Get the VM's external IP
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
    let ip = instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
        .as_str()
        .unwrap_or("unknown")
        .to_string();

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
