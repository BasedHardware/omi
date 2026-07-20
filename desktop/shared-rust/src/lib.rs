//! Platform-neutral policy and wire types shared by Omi desktop hosts.

pub mod fallback;
pub mod model_qos;

#[cfg(any(target_os = "macos", target_os = "linux"))]
eqswift::setup!();

/// Returns the resolved model tier for Swift clients on supported targets.
#[cfg(any(target_os = "macos", target_os = "linux"))]
#[eqswift::export]
pub fn active_model_tier() -> String {
    model_qos::active_tier().as_str().to_owned()
}

/// Returns the stable model identifier for a tier and workload.
#[cfg(any(target_os = "macos", target_os = "linux"))]
#[eqswift::export]
pub fn model_id_for(tier: String, workload: model_qos::ModelWorkload) -> String {
    model_qos::model_id_for(model_qos::ModelTier::from_persisted(&tier), workload).to_owned()
}

/// Returns the user-facing description for a tier.
#[cfg(any(target_os = "macos", target_os = "linux"))]
#[eqswift::export]
pub fn tier_description_for(tier: String) -> String {
    model_qos::tier_description_for(model_qos::ModelTier::from_persisted(&tier)).to_owned()
}
