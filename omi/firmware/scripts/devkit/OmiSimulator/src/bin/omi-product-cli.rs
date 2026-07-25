use omi_product_emulator::core::{
    discover_bluetooth_targets, mcumgr_image, monitor_button_events, nrfutil_devices,
    nrfutil_program, probe_device, read_button_event, set_bluetooth_connection, ButtonEvent,
    FirmwareImage, FlashSession, PeripheralSimulator,
};
use serde::Serialize;
use serde_json::{json, Value};
use std::{
    env,
    io::{self, BufRead},
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

fn hex_packet(value: &str) -> Result<Vec<u8>, String> {
    if value.is_empty() || !value.len().is_multiple_of(2) {
        return Err("audio packet must contain an even number of hexadecimal digits".into());
    }
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let pair = std::str::from_utf8(pair).map_err(|error| error.to_string())?;
            u8::from_str_radix(pair, 16)
                .map_err(|_| "audio packet contains invalid hexadecimal digits".into())
        })
        .collect()
}

fn simulate() -> Result<Value, String> {
    let mut simulator = PeripheralSimulator::start()?;
    output(json!({
        "state": "running",
        "input": ["button single|double|long|press|release", "battery 0..100", "audio HEX", "status", "stop"]
    }));
    for line in io::stdin().lock().lines() {
        let line = line.map_err(|error| error.to_string())?;
        let parts = line.split_whitespace().collect::<Vec<_>>();
        match parts.as_slice() {
            ["button", event] => simulator.button(button_event(event)?)?,
            ["battery", level] => simulator.battery(
                level
                    .parse::<u8>()
                    .map_err(|_| "battery level must be between 0 and 100")?,
            )?,
            ["audio", packet] => simulator.audio(&hex_packet(packet)?)?,
            ["status"] => {
                let (powered, pressed, battery) = simulator.status();
                output(
                    json!({"state": "running", "powered": powered, "pressed": pressed, "battery": battery}),
                );
            }
            ["stop"] => break,
            [] => continue,
            _ => {
                return Err("simulate input must be button, battery, audio, status, or stop".into())
            }
        }
    }
    if simulator.wait()? {
        Ok(json!({"state": "stopped"}))
    } else {
        Err("CoreBluetooth peripheral exited unsuccessfully".into())
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
        "disconnect" => {
            let id = required(args, 2, "device id")?;
            set_bluetooth_connection(id, false)?;
            Ok(json!({"device_id": id, "connected": false}))
        }
        "probe" => {
            let id = required(args, 2, "device id")?;
            serde_json::to_value(probe_device(id)?).map_err(|error| error.to_string())
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
            "monitor" => {
                let id = required(args, 3, "device id")?;
                let seconds = args
                    .get(4)
                    .map(|value| value.parse::<u64>())
                    .transpose()
                    .map_err(|error| error.to_string())?
                    .unwrap_or(30);
                Ok(json!({"device_id": id, "events": monitor_button_events(id, seconds)?}))
            }
            "event" => {
                let event = button_event(required(args, 3, "button event")?)?;
                Ok(json!({"event": event, "packet": event.packet()}))
            }
            _ => Err("button command must be read or event".into()),
        },
        "nrfutil" => match required(args, 2, "nrfutil command")? {
            "list" => nrfutil_devices(args.get(3).map(String::as_str)),
            "program" => {
                let firmware = required(args, 3, "firmware path")?;
                let controller = required(args, 4, "controller serial number")?;
                nrfutil_program(firmware, controller)
            }
            _ => Err("nrfutil command must be list or program".into()),
        },
        "mcumgr" => {
            let image = required(args, 2, "signed MCUboot image")?;
            let connection = required(args, 3, "connection string")?;
            mcumgr_image(image, connection, true)?;
            Ok(json!({"state": "completed", "reset": true}))
        }
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
        "simulate" => simulate(),
        _ => Err(
            "command must be scan, connect, disconnect, status, probe, button, firmware, flash, nrfutil, mcumgr, or simulate"
                .into(),
        ),
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

    #[test]
    fn parses_audio_fixture_packets() {
        assert_eq!(hex_packet("00ff10").unwrap(), [0, 255, 16]);
        assert!(hex_packet("").is_err());
        assert!(hex_packet("0").is_err());
        assert!(hex_packet("zz").is_err());
    }
}
