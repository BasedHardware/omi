use serde::Serialize;
use std::sync::Mutex;
use sysinfo::{Pid, ProcessRefreshKind, RefreshKind, System};
use tauri::command;

static SYSTEM: Mutex<Option<System>> = Mutex::new(None);

#[derive(Serialize)]
pub struct MemoryUsage {
    /// Resident set size of this process in bytes.
    pub process_bytes: u64,
    /// Total system RAM in bytes.
    pub total_bytes: u64,
    /// Used system RAM in bytes (active + wired).
    pub used_bytes: u64,
}

#[command]
pub async fn get_memory_usage() -> Result<MemoryUsage, String> {
    let pid = Pid::from_u32(std::process::id());
    let mut guard = SYSTEM.lock().map_err(|e| e.to_string())?;
    let sys = guard.get_or_insert_with(|| {
        System::new_with_specifics(
            RefreshKind::new()
                .with_memory(sysinfo::MemoryRefreshKind::everything())
                .with_processes(ProcessRefreshKind::new().with_memory()),
        )
    });

    sys.refresh_memory();
    sys.refresh_processes_specifics(
        sysinfo::ProcessesToUpdate::Some(&[pid]),
        true,
        ProcessRefreshKind::new().with_memory(),
    );

    let process_bytes = sys.process(pid).map(|p| p.memory()).unwrap_or(0);
    let total_bytes = sys.total_memory();
    let used_bytes = sys.used_memory();

    Ok(MemoryUsage {
        process_bytes,
        total_bytes,
        used_bytes,
    })
}
