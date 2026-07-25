#![no_std]

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
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
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ButtonState {
    pub pressed: bool,
    pub powered: bool,
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
    }
}
