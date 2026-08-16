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
