#![no_std]

use serde::Serialize;

pub const OMI_SERVICE_UUID: &str = "19b10000-e8f2-537e-4f6c-d104768a1214";
pub const AUDIO_DATA_UUID: &str = "19b10001-e8f2-537e-4f6c-d104768a1214";
pub const AUDIO_CODEC_UUID: &str = "19b10002-e8f2-537e-4f6c-d104768a1214";
pub const BUTTON_SERVICE_UUID: &str = "23ba7924-0000-1000-7450-346eac492e92";
pub const BUTTON_TRIGGER_UUID: &str = "23ba7925-0000-1000-7450-346eac492e92";
pub const BATTERY_SERVICE_UUID: &str = "0000180f-0000-1000-8000-00805f9b34fb";
pub const BATTERY_LEVEL_UUID: &str = "00002a19-0000-1000-8000-00805f9b34fb";
pub const DEVICE_INFO_SERVICE_UUID: &str = "0000180a-0000-1000-8000-00805f9b34fb";
pub const MODEL_NUMBER_UUID: &str = "00002a24-0000-1000-8000-00805f9b34fb";
pub const FIRMWARE_REVISION_UUID: &str = "00002a26-0000-1000-8000-00805f9b34fb";
pub const HARDWARE_REVISION_UUID: &str = "00002a27-0000-1000-8000-00805f9b34fb";
pub const MANUFACTURER_NAME_UUID: &str = "00002a29-0000-1000-8000-00805f9b34fb";

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
#[repr(i32)]
pub enum ButtonEvent {
    Single = 1,
    Double = 2,
    Long = 3,
    Press = 4,
    Release = 5,
}

impl ButtonEvent {
    pub fn packet(self) -> [u8; 8] {
        let mut packet = [0; 8];
        packet[..4].copy_from_slice(&(self as i32).to_le_bytes());
        packet
    }

    pub fn decode(packet: &[u8]) -> Result<Self, &'static str> {
        let bytes: [u8; 4] = packet
            .get(..4)
            .ok_or("button value is shorter than four bytes")?
            .try_into()
            .map_err(|_| "invalid button value")?;
        match i32::from_le_bytes(bytes) {
            1 => Ok(Self::Single),
            2 => Ok(Self::Double),
            3 => Ok(Self::Long),
            4 => Ok(Self::Press),
            5 => Ok(Self::Release),
            _ => Err("unknown button event"),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ButtonState {
    pub pressed: bool,
    pub powered: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PeripheralState {
    pub button: ButtonState,
    pub battery: u8,
}

impl Default for PeripheralState {
    fn default() -> Self {
        Self {
            button: ButtonState::default(),
            battery: 100,
        }
    }
}

impl PeripheralState {
    pub fn apply_button(&mut self, event: ButtonEvent) -> [u8; 8] {
        self.button.apply(event);
        event.packet()
    }

    pub fn set_battery(&mut self, level: u8) -> Result<[u8; 1], &'static str> {
        if level > 100 {
            return Err("battery level must be between 0 and 100");
        }
        self.battery = level;
        Ok([level])
    }
}

impl Default for ButtonState {
    fn default() -> Self {
        Self {
            pressed: false,
            powered: true,
        }
    }
}

impl ButtonState {
    pub fn apply(&mut self, event: ButtonEvent) {
        match event {
            ButtonEvent::Press => self.pressed = true,
            ButtonEvent::Release => self.pressed = false,
            ButtonEvent::Long => {
                self.pressed = false;
                self.powered = false;
            }
            ButtonEvent::Single | ButtonEvent::Double => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wire_values_and_state_transitions_match_firmware() {
        assert_eq!(ButtonEvent::Single.packet(), [1, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(ButtonEvent::Double.packet(), [2, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(ButtonEvent::Long.packet(), [3, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(ButtonEvent::Press.packet(), [4, 0, 0, 0, 0, 0, 0, 0]);
        assert_eq!(ButtonEvent::Release.packet(), [5, 0, 0, 0, 0, 0, 0, 0]);

        let mut state = ButtonState::default();
        state.apply(ButtonEvent::Press);
        assert!(state.pressed);
        state.apply(ButtonEvent::Release);
        assert!(!state.pressed);
        state.apply(ButtonEvent::Long);
        assert_eq!(
            state,
            ButtonState {
                pressed: false,
                powered: false
            }
        );

        let mut peripheral = PeripheralState::default();
        assert_eq!(
            peripheral.apply_button(ButtonEvent::Double),
            [2, 0, 0, 0, 0, 0, 0, 0]
        );
        assert_eq!(peripheral.set_battery(42), Ok([42]));
        assert_eq!(
            peripheral.set_battery(101),
            Err("battery level must be between 0 and 100")
        );
    }
}
