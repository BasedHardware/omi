use omi_product_emulator::core::{
    discover_bluetooth_targets, read_button_event, set_bluetooth_connection, ButtonEvent,
    FirmwareImage, FlashSession,
};
use serde::Serialize;
use serde_json::{json, Value};
use std::{
    env,
    process::ExitCode,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread,
    time::Duration,
};

fn output(value: impl Serialize) {
    println!(
        "{}",
        serde_json::to_string(&value).expect("serializing CLI output must succeed")
    );
}

fn required<'a>(args: &'a [String], index: usize, name: &str) -> Result<&'a str, String> {
    args.get(index)
        .map(String::as_str)
        .ok_or_else(|| format!("missing {name}"))
}

fn button_event(value: &str) -> Result<ButtonEvent, String> {
    match value {
        "single" => Ok(ButtonEvent::Single),
        "double" => Ok(ButtonEvent::Double),
        "long" => Ok(ButtonEvent::Long),
        "press" => Ok(ButtonEvent::Press),
        "release" => Ok(ButtonEvent::Release),
        _ => Err("button event must be single, double, long, press, or release".into()),
    }
}

fn run(args: &[String]) -> Result<Value, String> {
    match required(args, 1, "command")? {
        "scan" => Ok(json!({"devices": discover_bluetooth_targets()?})),
        "connect" => {
            let id = required(args, 2, "device id")?;
            set_bluetooth_connection(id, true)?;
            Ok(json!({"device_id": id, "connected": true}))
        }
        "status" => {
            let id = required(args, 2, "device id")?;
            let target = discover_bluetooth_targets()?
                .into_iter()
                .find(|target| target.address == id)
                .ok_or("device is not currently available")?;
            serde_json::to_value(target).map_err(|error| error.to_string())
        }
        "button" => match required(args, 2, "button command")? {
            "read" => {
                let id = required(args, 3, "device id")?;
                Ok(json!({"device_id": id, "event": read_button_event(id)?}))
            }
            "event" => {
                let event = button_event(required(args, 3, "button event")?)?;
                Ok(json!({"event": event, "packet": event.packet()}))
            }
            _ => Err("button command must be read or event".into()),
        },
        "firmware" => match required(args, 2, "firmware command")? {
            "inspect" => {
                let image = FirmwareImage::validate(required(args, 3, "firmware path")?)?;
                serde_json::to_value(image).map_err(|error| error.to_string())
            }
            _ => Err("firmware command must be inspect".into()),
        },
        "flash" => {
            let image = FirmwareImage::validate(required(args, 2, "firmware path")?)?;
            let serial = required(args, 3, "serial port")?;
            let cancelled = Arc::new(AtomicBool::new(false));
            let signal = Arc::clone(&cancelled);
            ctrlc::set_handler(move || signal.store(true, Ordering::SeqCst))
                .map_err(|error| error.to_string())?;
            let mut session = FlashSession::start_devkit(&image, serial)?;
            output(json!({"state": "running", "firmware": image, "serial": serial}));
            loop {
                if cancelled.load(Ordering::SeqCst) {
                    session.cancel()?;
                    return Err("flash cancelled".into());
                }
                match session.poll()? {
                    Some(true) => return Ok(json!({"state": "completed"})),
                    Some(false) => return Err("flash tool reported failure".into()),
                    None => thread::sleep(Duration::from_millis(100)),
                }
            }
        }
        _ => Err("command must be scan, connect, status, button, firmware, or flash".into()),
    }
}

fn main() -> ExitCode {
    let args = env::args().collect::<Vec<_>>();
    match run(&args) {
        Ok(value) => {
            output(json!({"ok": true, "result": value}));
            ExitCode::SUCCESS
        }
        Err(error) => {
            output(json!({"ok": false, "error": error}));
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_missing_and_invalid_commands() {
        assert!(run(&["omi-product-cli".into()]).is_err());
        assert!(run(&["omi-product-cli".into(), "nope".into()]).is_err());
        assert!(run(&[
            "omi-product-cli".into(),
            "button".into(),
            "event".into(),
            "nope".into()
        ])
        .is_err());
    }

    #[test]
    fn emits_button_packets_without_hardware() {
        let result = run(&[
            "omi-product-cli".into(),
            "button".into(),
            "event".into(),
            "press".into(),
        ])
        .unwrap();
        assert_eq!(result["packet"], json!([4, 0, 0, 0, 0, 0, 0, 0]));
    }
}
