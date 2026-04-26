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
// macOS implementation
// ---------------------------------------------------------------------------
//
// App name + PID come from NSWorkspace.frontmostApplication (no special
// permission). Window title comes from CGWindowListCopyWindowInfo, scanning
// for the topmost on-screen window owned by that PID. The window-list call
// only returns titles when Screen Recording is granted (same TCC scope as
// capture), so without that grant `window_title` is the empty string.
#[cfg(target_os = "macos")]
mod platform {
    use super::*;
    use core_foundation::array::CFArray;
    use core_foundation::base::{CFType, TCFType, ToVoid};
    use core_foundation::dictionary::CFDictionary;
    use core_foundation::number::CFNumber;
    use core_foundation::string::CFString;
    use core_graphics::window::{
        kCGNullWindowID, kCGWindowListExcludeDesktopElements,
        kCGWindowListOptionOnScreenOnly, CGWindowListCopyWindowInfo,
    };
    use objc2::msg_send;
    use objc2::rc::Retained;
    use objc2::runtime::AnyObject;
    use objc2_app_kit::{NSRunningApplication, NSWorkspace};

    fn frontmost_app() -> Option<Retained<NSRunningApplication>> {
        // sharedWorkspace + frontmostApplication are typed-safe in
        // objc2-app-kit 0.3; no unsafe block needed.
        NSWorkspace::sharedWorkspace().frontmostApplication()
    }

    /// Look up the title of the topmost on-screen window owned by `pid`.
    /// Returns "" if none is found or the OS withholds the title.
    fn window_title_for_pid(pid: i32) -> String {
        let info: CFArray<CFDictionary> = unsafe {
            let raw = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                kCGNullWindowID,
            );
            if raw.is_null() {
                return String::new();
            }
            CFArray::wrap_under_create_rule(raw)
        };

        // CGWindowListCopyWindowInfo returns front-to-back, so the first dict
        // owned by our PID is the visually frontmost one.
        let owner_pid_key = CFString::from_static_string("kCGWindowOwnerPID");
        let name_key = CFString::from_static_string("kCGWindowName");

        for i in 0..info.len() {
            let dict = match info.get(i) {
                Some(d) => d,
                None => continue,
            };

            let owner_pid: Option<i32> = unsafe {
                dict.find(owner_pid_key.to_void()).and_then(|item| {
                    let ty = CFType::wrap_under_get_rule(*item);
                    ty.downcast::<CFNumber>().and_then(|n| n.to_i32())
                })
            };

            if owner_pid != Some(pid) {
                continue;
            }

            let title: Option<String> = unsafe {
                dict.find(name_key.to_void()).and_then(|item| {
                    let ty = CFType::wrap_under_get_rule(*item);
                    ty.downcast::<CFString>().map(|s| s.to_string())
                })
            };

            return title.unwrap_or_default();
        }

        String::new()
    }

    pub fn get_active_window_impl() -> Result<ActiveWindow, String> {
        let app = frontmost_app().ok_or_else(|| "No frontmost application".to_string())?;

        let app_name = app
            .localizedName()
            .map(|s| s.to_string())
            .unwrap_or_default();

        // `processIdentifier` is a `pid_t` (i32) selector on NSRunningApplication.
        // It isn't surfaced as a typed method by objc2-app-kit 0.2, so we send
        // the message directly. The selector is part of the public AppKit ABI
        // and has been stable since macOS 10.6.
        let pid: i32 = unsafe {
            let obj: &AnyObject = &*(Retained::as_ptr(&app) as *const AnyObject);
            msg_send![obj, processIdentifier]
        };

        let window_title = window_title_for_pid(pid);

        Ok(ActiveWindow {
            app_name,
            window_title,
            pid: pid as u32,
        })
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
