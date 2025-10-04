#![allow(dead_code)]
#![allow(unused_imports)]

//! Sketch of what the LED driver might look like if we relied on
//! Zephyr's native Rust bindings (no C shim).
//!
//! This assumes the existence of high-level safe wrappers around
//! PWM dt-specs and the settings subsystem, which the upstream
//! `embassy-zephyr` and `zephyr-rust` experiments are converging on.
//! The code below is illustrative only.

use zephyr::drivers::pwm::{Pwm, PwmChannel, PulseWidth, Period};
use zephyr::dt::{self, DevicePath};
use zephyr::kernel::error::Result;
use zephyr::logging::Log;
use zephyr::settings::{Settings, SettingsHandle};

/// Strongly typed wrapper around the three LED channels the board exposes.
struct StatusLeds {
    red: PwmChannel,
    green: PwmChannel,
    blue: PwmChannel,
    settings: SettingsHandle,
}

impl StatusLeds {
    /// Instantiate channels straight from device tree handles.
    pub fn new(settings: SettingsHandle) -> Result<Self> {
        // DevicePath::label resolves to &lt;DT_NODELABEL&gt; entries at build time.
        let red = Pwm::from_dt(DevicePath::label("led_red"))?.channel(0)?;
        let green = Pwm::from_dt(DevicePath::label("led_green"))?.channel(0)?;
        let blue = Pwm::from_dt(DevicePath::label("led_blue"))?.channel(0)?;

        Ok(Self { red, green, blue, settings })
    }

    /// Equivalent to `led_start` in C: ensure each PWM device is ready.
    pub fn init(&self) -> Result<()> {
        self.red.device().ensure_ready()?;
        self.green.device().ensure_ready()?;
        self.blue.device().ensure_ready()?;
        Log::info!("LED PWM devices ready");
        Ok(())
    }

    fn dim_ratio(&self) -> u32 {
        self.settings
            .get::<u8>("omi/dim_ratio")
            .ok()
            .map(u32::from)
            .unwrap_or(50)
            .min(100)
    }

    fn apply(&self, channel: &PwmChannel, on: bool) -> Result<()> {
        let period = channel.period()?;
        let pulse = if on {
            Period::ticks(period.ticks() * self.dim_ratio() / 100)
        } else {
            Period::ticks(0)
        };
        channel.set_pulse(PulseWidth::from_period(pulse))
    }

    pub fn set_red(&self, on: bool) {
        if let Err(err) = self.apply(&self.red, on) {
            Log::error!("Failed to set red LED: {:?}", err);
        }
    }

    pub fn set_green(&self, on: bool) {
        if let Err(err) = self.apply(&self.green, on) {
            Log::error!("Failed to set green LED: {:?}", err);
        }
    }

    pub fn set_blue(&self, on: bool) {
        if let Err(err) = self.apply(&self.blue, on) {
            Log::error!("Failed to set blue LED: {:?}", err);
        }
    }
}

/// Example of how an async task might drive the boot animation using Embassy.
#[embassy::task]
pub async fn boot_chaser(mut leds: StatusLeds) {
    use embassy_time::Timer;

    if leds.init().is_err() {
        return;
    }

    let delay = embassy_time::Duration::from_millis(600);
    let pause = embassy_time::Duration::from_millis(200);

    leds.set_red(true);
    Timer::after(delay).await;
    leds.set_red(false);
    Timer::after(pause).await;

    leds.set_green(true);
    Timer::after(delay).await;
    leds.set_green(false);
    Timer::after(pause).await;

    leds.set_blue(true);
    Timer::after(delay).await;
    leds.set_blue(false);
    Timer::after(pause).await;

    leds.set_red(true);
    leds.set_green(true);
    leds.set_blue(true);
    Timer::after(delay).await;

    leds.set_red(false);
    leds.set_green(false);
    leds.set_blue(false);
}

/// Entry point (called from your Zephyr Rust `main`).
pub fn start(settings: SettingsHandle) {
    if let Ok(leds) = StatusLeds::new(settings) {
        embassy::spawn!(boot_chaser(leds)).unwrap();
    }
}

