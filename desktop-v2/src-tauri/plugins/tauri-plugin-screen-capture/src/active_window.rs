use crate::models::ActiveWindow;

/// Detect the currently focused window and return information about it.
pub fn get_active_window() -> Result<ActiveWindow, String> {
    platform::get_active_window_impl()
}

// ---------------------------------------------------------------------------
// Linux implementation (X11 via x11rb)
// ---------------------------------------------------------------------------
#[cfg(target_os = "linux")]
mod platform {
    use super::*;
    use x11rb::connection::Connection;
    use x11rb::protocol::xproto::{Atom, AtomEnum, ConnectionExt as _, Window};
    use x11rb::rust_connection::RustConnection;

    /// Helper: intern an atom name and return its ID.
    fn intern_atom(conn: &RustConnection, name: &str) -> Result<Atom, String> {
        conn.intern_atom(false, name.as_bytes())
            .map_err(|e| format!("intern_atom request failed: {}", e))?
            .reply()
            .map(|r| r.atom)
            .map_err(|e| format!("intern_atom reply failed: {}", e))
    }

    /// Read a property that holds a single u32 (window ID, PID, etc.).
    fn get_property_u32(
        conn: &RustConnection,
        window: Window,
        property: Atom,
    ) -> Result<u32, String> {
        let reply = conn
            .get_property(false, window, property, AtomEnum::ANY, 0, 1)
            .map_err(|e| format!("get_property request failed: {}", e))?
            .reply()
            .map_err(|e| format!("get_property reply failed: {}", e))?;

        if reply.value_len == 0 || reply.value.len() < 4 {
            return Err("Property not found or empty".to_string());
        }

        Ok(u32::from_ne_bytes([
            reply.value[0],
            reply.value[1],
            reply.value[2],
            reply.value[3],
        ]))
    }

    /// Read a string property (UTF-8 or Latin-1).
    fn get_property_string(
        conn: &RustConnection,
        window: Window,
        property: Atom,
    ) -> Result<String, String> {
        let reply = conn
            .get_property(false, window, property, AtomEnum::ANY, 0, 1024)
            .map_err(|e| format!("get_property request failed: {}", e))?
            .reply()
            .map_err(|e| format!("get_property reply failed: {}", e))?;

        if reply.value_len == 0 {
            return Err("Property not found or empty".to_string());
        }

        Ok(String::from_utf8_lossy(&reply.value)
            .trim_end_matches('\0')
            .to_string())
    }

    pub fn get_active_window_impl() -> Result<ActiveWindow, String> {
        let (conn, screen_num) =
            RustConnection::connect(None).map_err(|e| format!("X11 connect failed: {}", e))?;

        let screen = &conn.setup().roots[screen_num];
        let root = screen.root;

        // Get _NET_ACTIVE_WINDOW from root.
        let net_active_window = intern_atom(&conn, "_NET_ACTIVE_WINDOW")?;
        let active_win = get_property_u32(&conn, root, net_active_window)
            .map_err(|_| "No active window found".to_string())?;

        if active_win == 0 {
            return Err("No window is currently focused".to_string());
        }

        // Get _NET_WM_PID.
        let net_wm_pid = intern_atom(&conn, "_NET_WM_PID")?;
        let pid = get_property_u32(&conn, active_win, net_wm_pid).unwrap_or(0);

        // Get _NET_WM_NAME (UTF-8) or fall back to WM_NAME.
        let net_wm_name = intern_atom(&conn, "_NET_WM_NAME")?;
        let window_title = get_property_string(&conn, active_win, net_wm_name)
            .or_else(|_| {
                get_property_string(
                    &conn,
                    active_win,
                    u32::from(AtomEnum::WM_NAME),
                )
            })
            .unwrap_or_default();

        // Get WM_CLASS — format: "instance\0class\0".
        let wm_class_atom = u32::from(AtomEnum::WM_CLASS);
        let wm_class_raw = get_property_string(&conn, active_win, wm_class_atom)
            .unwrap_or_default();

        // The class name is the second null-separated string.
        let app_name = wm_class_raw
            .split('\0')
            .nth(1)
            .unwrap_or_else(|| wm_class_raw.split('\0').next().unwrap_or("unknown"))
            .to_string();

        Ok(ActiveWindow {
            app_name,
            window_title,
            pid,
        })
    }
}

// ---------------------------------------------------------------------------
// macOS stub
// ---------------------------------------------------------------------------
#[cfg(target_os = "macos")]
mod platform {
    use super::*;

    pub fn get_active_window_impl() -> Result<ActiveWindow, String> {
        Err("Active window detection is not yet implemented on macOS".to_string())
    }
}

// ---------------------------------------------------------------------------
// Windows stub
// ---------------------------------------------------------------------------
#[cfg(target_os = "windows")]
mod platform {
    use super::*;

    pub fn get_active_window_impl() -> Result<ActiveWindow, String> {
        Err("Active window detection is not yet implemented on Windows".to_string())
    }
}

// ---------------------------------------------------------------------------
// Fallback
// ---------------------------------------------------------------------------
#[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
mod platform {
    use super::*;

    pub fn get_active_window_impl() -> Result<ActiveWindow, String> {
        Err("Active window detection is not supported on this platform".to_string())
    }
}
