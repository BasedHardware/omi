use core::ffi::c_void;

use crate::hal::{self, AdcDevice, BatteryHardware, Error as HalError};
use crate::util;
use spin::Mutex;

const ADC_TOTAL_SAMPLES: usize = 50;
const HISTORY_SIZE: usize = 5;
const R1: u16 = 1091;
const R2: u16 = 499;
const ADC_RESOLUTION: u8 = 12;

static SAMPLE_BUFFER: Mutex<[i16; ADC_TOTAL_SAMPLES + 1]> = Mutex::new([0; ADC_TOTAL_SAMPLES + 1]);

struct History {
    values: [u16; HISTORY_SIZE],
    index: usize,
    initialized: bool,
}

static HISTORY: Mutex<History> = Mutex::new(History {
    values: [0; HISTORY_SIZE],
    index: 0,
    initialized: false,
});

#[derive(Clone, Copy)]
struct BatteryState {
    millivolts: u16,
    percentage: u8,
}

const BATTERY_STATES: [BatteryState; 12] = [
    BatteryState {
        millivolts: 4200,
        percentage: 100,
    },
    BatteryState {
        millivolts: 4160,
        percentage: 99,
    },
    BatteryState {
        millivolts: 4090,
        percentage: 91,
    },
    BatteryState {
        millivolts: 4030,
        percentage: 78,
    },
    BatteryState {
        millivolts: 3890,
        percentage: 63,
    },
    BatteryState {
        millivolts: 3830,
        percentage: 53,
    },
    BatteryState {
        millivolts: 3680,
        percentage: 36,
    },
    BatteryState {
        millivolts: 3660,
        percentage: 35,
    },
    BatteryState {
        millivolts: 3480,
        percentage: 14,
    },
    BatteryState {
        millivolts: 3420,
        percentage: 11,
    },
    BatteryState {
        millivolts: 3400,
        percentage: 1,
    },
    BatteryState {
        millivolts: 0,
        percentage: 0,
    },
];

extern "C" {
    static mut is_charging: bool;
}

fn error_code(err: HalError) -> i32 {
    err.as_errno()
}

struct MeasureGuard<'a> {
    hw: &'a BatteryHardware,
    active: bool,
}

impl<'a> MeasureGuard<'a> {
    fn new(hw: &'a BatteryHardware) -> Self {
        Self { hw, active: false }
    }

    fn arm(&mut self) {
        self.active = true;
    }
}

impl<'a> Drop for MeasureGuard<'a> {
    fn drop(&mut self) {
        if self.active {
            let _ = self.hw.restore_measurement();
        }
    }
}

fn update_history(value: u16) -> u16 {
    let mut history = HISTORY.lock();

    if !history.initialized {
        history.values.fill(value);
        history.initialized = true;
    } else {
        let idx = history.index;
        history.values[idx] = value;
    }

    history.index = (history.index + 1) % HISTORY_SIZE;

    let sum: u32 = history.values.iter().map(|&v| v as u32).sum();
    (sum / HISTORY_SIZE as u32) as u16
}

fn median_from_buffer(buffer: &[i16]) -> i32 {
    let mut sorted = [0i16; ADC_TOTAL_SAMPLES];
    sorted.copy_from_slice(&buffer[1..=ADC_TOTAL_SAMPLES]);
    sorted.sort_unstable();

    if ADC_TOTAL_SAMPLES % 2 == 0 {
        let a = sorted[ADC_TOTAL_SAMPLES / 2 - 1] as i32;
        let b = sorted[ADC_TOTAL_SAMPLES / 2] as i32;
        (a + b) / 2
    } else {
        sorted[ADC_TOTAL_SAMPLES / 2] as i32
    }
}

fn convert_to_millivolts(adc: &AdcDevice, raw: i32) -> Result<i32, i32> {
    let mut value = raw;
    if let Err(err) = adc.raw_to_millivolts(hal::ADC_GAIN_1_3, ADC_RESOLUTION, &mut value) {
        Err(err.as_errno())
    } else {
        Ok(value)
    }
}

fn scale_to_battery_voltage(adc_mv: i32, charging: bool) -> u16 {
    let corrected = if charging { adc_mv - 16 } else { adc_mv };
    if corrected <= 0 {
        return 0;
    }

    let numerator = (corrected as i64) * (R1 as i64 + R2 as i64);
    let voltage = numerator / R2 as i64;
    voltage.max(0).min(u16::MAX as i64) as u16
}

fn hardware() -> BatteryHardware {
    BatteryHardware::new()
}

#[no_mangle]
pub extern "C" fn battery_get_millivolt(out: *mut u16) -> i32 {
    if out.is_null() {
        return HalError::NullPointer.as_errno();
    }

    let adc = match AdcDevice::new() {
        Ok(adc) => adc,
        Err(err) => return err.as_errno(),
    };

    let hw = hardware();
    let mut buffer = SAMPLE_BUFFER.lock();
    let mut guard = MeasureGuard::new(&hw);

    if let Err(err) = hw.prepare_measurement() {
        return error_code(err);
    }
    guard.arm();

    if !adc.is_ready() {
        return HalError::DeviceNotReady.as_errno();
    }

    if let Err(err) = hw.channel_setup() {
        return error_code(err);
    }

    hw.calibrate_offset();
    hal::busy_wait_us(100);

    if let Err(err) = hw.read_samples(&mut buffer[..], ADC_TOTAL_SAMPLES as u32) {
        return error_code(err);
    }

    let median = median_from_buffer(&buffer[..]);
    let adc_mv = match convert_to_millivolts(&adc, median) {
        Ok(value) => value,
        Err(err) => return err,
    };

    let charging = unsafe { is_charging };
    let raw_mv = scale_to_battery_voltage(adc_mv, charging);
    let filtered = update_history(raw_mv);

    unsafe {
        *out = filtered;
    }

    0
}

#[no_mangle]
pub extern "C" fn battery_get_percentage(out: *mut u8, battery_millivolt: u16) -> i32 {
    if out.is_null() {
        return HalError::NullPointer.as_errno();
    }

    let percentage = if battery_millivolt >= BATTERY_STATES[0].millivolts {
        BATTERY_STATES[0].percentage
    } else if battery_millivolt <= BATTERY_STATES[BATTERY_STATES.len() - 1].millivolts {
        BATTERY_STATES[BATTERY_STATES.len() - 1].percentage
    } else {
        let mut value = BATTERY_STATES[BATTERY_STATES.len() - 1].percentage;
        for window in BATTERY_STATES.windows(2) {
            let upper = window[0];
            let lower = window[1];
            if battery_millivolt <= upper.millivolts && battery_millivolt > lower.millivolts {
                let voltage_range = (upper.millivolts - lower.millivolts) as u32;
                let percentage_range = (upper.percentage - lower.percentage) as u32;
                let voltage_diff = (upper.millivolts - battery_millivolt) as u32;
                value =
                    upper.percentage - ((voltage_diff * percentage_range) / voltage_range) as u8;
                break;
            }
        }
        value
    };

    unsafe {
        *out = percentage;
    }

    0
}

#[no_mangle]
pub extern "C" fn battery_charge_start() -> i32 {
    match start_charging_impl() {
        Ok(()) => 0,
        Err(err) => err,
    }
}

#[no_mangle]
pub extern "C" fn battery_charge_stop() -> i32 {
    0
}

#[no_mangle]
pub extern "C" fn battery_set_fast_charge() -> i32 {
    0
}

#[no_mangle]
pub extern "C" fn battery_set_slow_charge() -> i32 {
    0
}

#[no_mangle]
pub extern "C" fn battery_charging_state_read() -> i32 {
    let hw = hardware();
    let state = match hw.read_charge_pin() {
        Ok(val) => val,
        Err(err) => return error_code(err),
    };

    unsafe {
        is_charging = state == 0;
    }
    0
}

#[no_mangle]
pub extern "C" fn battery_enable_read() -> i32 {
    let adc = match AdcDevice::new() {
        Ok(adc) => adc,
        Err(err) => return err.as_errno(),
    };

    let hw = hardware();
    let mut buffer = SAMPLE_BUFFER.lock();
    let mut guard = MeasureGuard::new(&hw);

    if let Err(err) = hw.prepare_measurement() {
        return error_code(err);
    }
    guard.arm();

    hal::sleep_ms(10);

    if !adc.is_ready() {
        return HalError::DeviceNotReady.as_errno();
    }

    if let Err(err) = hw.channel_setup() {
        return error_code(err);
    }

    hw.calibrate_offset();
    hal::sleep_ms(5);

    match hw.read_samples(&mut buffer[..], ADC_TOTAL_SAMPLES as u32) {
        Ok(()) => 0,
        Err(err) => error_code(err),
    }
}

unsafe extern "C" fn battery_chg_trampoline(_user_data: *mut c_void) {
    let res = battery_charging_state_read();
    if res < 0 {
        util::log_error_fmt(format_args!("Failed to read charging state ({res})\n"));
    }
}

#[no_mangle]
pub extern "C" fn battery_init() -> i32 {
    match init_impl() {
        Ok(()) => 0,
        Err(err) => err,
    }
}

fn start_charging_impl() -> Result<(), i32> {
    Ok(())
}

fn init_impl() -> Result<(), i32> {
    let hw = hardware();

    if let Err(err) = hw.configure_pins() {
        return Err(error_code(err));
    }

    if let Err(err) = hw.set_charging_handler(Some(battery_chg_trampoline), core::ptr::null_mut()) {
        return Err(error_code(err));
    }

    if let Err(err) = hw.enable_charging_interrupt() {
        return Err(error_code(err));
    }

    let _ = battery_enable_read();
    let _ = battery_charging_state_read();

    Ok(())
}

pub fn init() -> Result<(), i32> {
    init_impl()
}

pub fn start_charging() -> Result<(), i32> {
    start_charging_impl()
}
