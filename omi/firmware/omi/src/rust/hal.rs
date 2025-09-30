use core::ffi::{c_char, c_void, CStr};
use core::ptr;

use crate::ffi;

const ENODEV: i32 = -19;
const EINVAL: i32 = -22;
const EALREADY: i32 = -114;

pub const ADC_GAIN_1_3: i32 = ffi::ADC_GAIN_1_3;
pub const DMIC_TRIGGER_START: i32 = ffi::DMIC_TRIGGER_START;
pub const DMIC_TRIGGER_STOP: i32 = ffi::DMIC_TRIGGER_STOP;
pub const DISK_IOCTL_CTRL_INIT: u8 = ffi::DISK_IOCTL_CTRL_INIT;
pub const DISK_IOCTL_CTRL_DEINIT: u8 = ffi::DISK_IOCTL_CTRL_DEINIT;
pub const DISK_IOCTL_GET_SECTOR_COUNT: u8 = ffi::DISK_IOCTL_GET_SECTOR_COUNT;
pub const DISK_IOCTL_GET_SECTOR_SIZE: u8 = ffi::DISK_IOCTL_GET_SECTOR_SIZE;

#[derive(Debug, Clone, Copy)]
pub enum Error {
    NullPointer,
    DeviceNotReady,
    C(i32),
}

impl Error {
    pub fn as_errno(self) -> i32 {
        match self {
            Error::NullPointer => EINVAL,
            Error::DeviceNotReady => ENODEV,
            Error::C(code) => code,
        }
    }
}

pub type Result<T> = core::result::Result<T, Error>;

impl From<i32> for Error {
    fn from(code: i32) -> Self {
        if code < 0 {
            Error::C(code)
        } else {
            Error::C(code)
        }
    }
}

#[derive(Clone, Copy)]
pub struct GpioPin {
    raw: *const c_void,
}

impl GpioPin {
    pub fn new(raw: *const c_void) -> Result<Self> {
        if raw.is_null() {
            Err(Error::NullPointer)
        } else {
            Ok(Self { raw })
        }
    }

    pub fn raw(&self) -> *const c_void {
        self.raw
    }

    pub fn is_ready(&self) -> bool {
        unsafe { ffi::omi_gpio_is_ready(self.raw) }
    }

    pub fn configure_output(&self) -> Result<()> {
        let err = unsafe { ffi::omi_gpio_configure(self.raw, ffi::omi_gpio_flag_output()) };
        if err < 0 {
            Err(Error::from(err))
        } else {
            Ok(())
        }
    }

    pub fn configure_input(&self) -> Result<()> {
        let err = unsafe { ffi::omi_gpio_configure(self.raw, ffi::omi_gpio_flag_input()) };
        if err < 0 {
            Err(Error::from(err))
        } else {
            Ok(())
        }
    }

    pub fn set(&self, value: bool) -> Result<()> {
        let err = unsafe { ffi::omi_gpio_set(self.raw, value as i32) };
        if err < 0 {
            Err(Error::from(err))
        } else {
            Ok(())
        }
    }
}

#[derive(Clone, Copy)]
pub enum LedColor {
    Red,
    Green,
    Blue,
}

#[derive(Clone, Copy)]
pub struct LedPwm {
    color: LedColor,
}

impl LedPwm {
    pub fn new(color: LedColor) -> Self {
        Self { color }
    }

    pub fn red() -> Self {
        Self::new(LedColor::Red)
    }

    pub fn green() -> Self {
        Self::new(LedColor::Green)
    }

    pub fn blue() -> Self {
        Self::new(LedColor::Blue)
    }

    fn is_ready_fn(&self) -> unsafe extern "C" fn() -> bool {
        match self.color {
            LedColor::Red => ffi::omi_led_ready_red,
            LedColor::Green => ffi::omi_led_ready_green,
            LedColor::Blue => ffi::omi_led_ready_blue,
        }
    }

    fn period_fn(&self) -> unsafe extern "C" fn() -> u32 {
        match self.color {
            LedColor::Red => ffi::omi_led_period_red,
            LedColor::Green => ffi::omi_led_period_green,
            LedColor::Blue => ffi::omi_led_period_blue,
        }
    }

    fn set_fn(&self) -> unsafe extern "C" fn(u32) -> i32 {
        match self.color {
            LedColor::Red => ffi::omi_led_set_red,
            LedColor::Green => ffi::omi_led_set_green,
            LedColor::Blue => ffi::omi_led_set_blue,
        }
    }

    pub fn is_ready(&self) -> bool {
        unsafe { (self.is_ready_fn())() }
    }

    pub fn period(&self) -> u32 {
        unsafe { (self.period_fn())() }
    }

    pub fn set_pulse(&self, pulse: u32) -> Result<()> {
        let err = unsafe { (self.set_fn())(pulse) };
        if err < 0 {
            Err(Error::from(err))
        } else {
            Ok(())
        }
    }

    pub fn set_duty(&self, percent: u32) -> Result<()> {
        let ratio = percent.min(100);
        let pulse = (self.period() * ratio) / 100;
        self.set_pulse(pulse)
    }

    pub fn off(&self) -> Result<()> {
        self.set_pulse(0)
    }
}

pub fn led_start() -> Result<()> {
    let leds = [LedPwm::red(), LedPwm::green(), LedPwm::blue()];
    for led in leds.iter() {
        if !led.is_ready() {
            return Err(Error::DeviceNotReady);
        }
    }
    Ok(())
}

pub struct SdCard {
    device: *const c_void,
    enable_pin: GpioPin,
    mount: *mut c_void,
    drive: *const c_char,
    mount_point: *const c_char,
}

impl SdCard {
    pub fn new() -> Result<Self> {
        let device = unsafe { ffi::omi_sd_device() };
        if device.is_null() {
            return Err(Error::NullPointer);
        }

        let enable_pin = GpioPin::new(unsafe { ffi::omi_sd_enable_pin() })?;
        let mount = unsafe { ffi::omi_sd_mount_struct() };
        if mount.is_null() {
            return Err(Error::NullPointer);
        }
        let drive = unsafe { ffi::omi_sd_drive_name() };
        if drive.is_null() {
            return Err(Error::NullPointer);
        }
        let mount_point = unsafe { ffi::omi_sd_mount_point() };
        if mount_point.is_null() {
            return Err(Error::NullPointer);
        }

        Ok(Self {
            device,
            enable_pin,
            mount,
            drive,
            mount_point,
        })
    }

    pub fn device_name(&self) -> Option<&'static str> {
        let ptr = unsafe { ffi::omi_device_name(self.device) };
        if ptr.is_null() {
            None
        } else {
            unsafe { CStr::from_ptr(ptr) }.to_str().ok()
        }
    }

    pub fn drive_name(&self) -> &'static str {
        unsafe { CStr::from_ptr(self.drive) }.to_str().unwrap_or("SDMMC")
    }

    pub fn mount_point(&self) -> &'static str {
        unsafe { CStr::from_ptr(self.mount_point) }.to_str().unwrap_or("/ext")
    }

    pub fn power_on(&self) -> Result<()> {
        self.enable_pin.configure_output()?;
        self.enable_pin.set(true)?;
        let ret = unsafe { ffi::omi_pm_device_action(self.device, ffi::PM_DEVICE_ACTION_RESUME) };
        if ret < 0 && ret != EALREADY {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn power_off(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_pm_device_action(self.device, ffi::PM_DEVICE_ACTION_SUSPEND) };
        if ret < 0 && ret != EALREADY {
            return Err(Error::from(ret));
        }
        let _ = self.enable_pin.set(false);
        Ok(())
    }

    pub fn disk_ioctl_raw(&self, cmd: u8, buffer: *mut c_void) -> Result<()> {
        let ret = unsafe { ffi::omi_disk_access_ioctl(self.drive, cmd, buffer) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn disk_init(&self) -> Result<()> {
        self.disk_ioctl_raw(DISK_IOCTL_CTRL_INIT, ptr::null_mut())
    }

    pub fn disk_deinit(&self) -> Result<()> {
        self.disk_ioctl_raw(DISK_IOCTL_CTRL_DEINIT, ptr::null_mut())
    }

    pub fn disk_ioctl<T>(&self, cmd: u8, buffer: Option<&mut T>) -> Result<()> {
        let ptr = buffer
            .map(|b| b as *mut T as *mut c_void)
            .unwrap_or(ptr::null_mut());
        self.disk_ioctl_raw(cmd, ptr)
    }

    pub fn stats(&self) -> Result<(u32, u32)> {
        let mut block_count: u32 = 0;
        self.disk_ioctl(ffi::DISK_IOCTL_GET_SECTOR_COUNT, Some(&mut block_count))?;
        let mut block_size: u32 = 0;
        self.disk_ioctl(ffi::DISK_IOCTL_GET_SECTOR_SIZE, Some(&mut block_size))?;
        Ok((block_count, block_size))
    }

    pub fn mount(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_fs_mount(self.mount) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn unmount(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_fs_unmount(self.mount) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn format_ext2(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_fs_mkfs(ffi::FS_EXT2, self.mount as usize, ptr::null_mut(), 0) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }
}

pub struct DelayableWork {
    raw: *mut c_void,
}

impl DelayableWork {
    pub fn new(callback: ffi::omi_work_callback_t, user_data: *mut c_void) -> Result<Self> {
        let raw = unsafe { ffi::omi_delayable_work_create(callback, user_data) };
        if raw.is_null() {
            Err(Error::NullPointer)
        } else {
            Ok(Self { raw })
        }
    }

    pub fn cancel(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_delayable_work_cancel(self.raw) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn schedule(&self, delay_ms: u32) -> Result<()> {
        let ret = unsafe { ffi::omi_delayable_work_schedule(self.raw, delay_ms) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn raw(&self) -> *mut c_void {
        self.raw
    }
}

impl Drop for DelayableWork {
    fn drop(&mut self) {
        unsafe { ffi::omi_delayable_work_destroy(self.raw) }
    }
}

unsafe impl Send for DelayableWork {}

pub struct BatteryHardware;

impl BatteryHardware {
    pub fn new() -> Self {
        Self
    }

    pub fn prepare_measurement(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_battery_prepare_measurement_pin() };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn restore_measurement(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_battery_restore_measurement_pin() };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn channel_setup(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_battery_channel_setup() };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn read_samples(&self, buffer: &mut [i16], extra: u32) -> Result<()> {
        let ret = unsafe { ffi::omi_battery_perform_read(buffer.as_mut_ptr(), buffer.len(), extra) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn calibrate_offset(&self) {
        unsafe { ffi::omi_saadc_trigger_offset_calibration() };
    }

    pub fn configure_pins(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_battery_configure_pins() };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn set_charging_handler(&self, cb: ffi::omi_gpio_edge_cb_t, user_data: *mut c_void) -> Result<()> {
        let ret = unsafe { ffi::omi_battery_set_chg_handler(cb, user_data) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn enable_charging_interrupt(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_battery_enable_chg_interrupt() };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn disable_charging_interrupt(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_battery_disable_chg_interrupt() };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn read_charge_pin(&self) -> Result<i32> {
        let ret = unsafe { ffi::omi_battery_read_chg_pin() };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(ret)
        }
    }
}

pub struct Dmic {
    raw: *const c_void,
}

impl Dmic {
    pub fn new() -> Result<Self> {
        let raw = unsafe { ffi::omi_device_get(ffi::OMI_DEVICE_DMIC0) };
        if raw.is_null() {
            Err(Error::NullPointer)
        } else if !unsafe { ffi::omi_device_is_ready(raw) } {
            Err(Error::DeviceNotReady)
        } else {
            Ok(Self { raw })
        }
    }

    pub fn configure(&self, sample_rate: u32, channels: u8) -> Result<()> {
        let ret = unsafe { ffi::omi_mic_configure(sample_rate, channels) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn trigger(&self, trigger: i32) -> Result<()> {
        let ret = unsafe { ffi::omi_dmic_trigger(self.raw, trigger) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn read(&self, buffer: &mut *mut c_void, size: &mut u32, timeout_ms: i32) -> Result<()> {
        let ret = unsafe { ffi::omi_dmic_read(self.raw, 0, buffer, size, timeout_ms) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }
}

pub struct MemSlab {
    raw: *mut c_void,
}

impl MemSlab {
    pub fn global() -> Result<Self> {
        let raw = unsafe { ffi::omi_mic_mem_slab() };
        if raw.is_null() {
            Err(Error::NullPointer)
        } else {
            Ok(Self { raw })
        }
    }

    pub fn alloc(&self, timeout_ms: u32) -> Result<*mut c_void> {
        let mut block: *mut c_void = ptr::null_mut();
        let ret = unsafe { ffi::omi_mem_slab_alloc(self.raw, &mut block, timeout_ms) };
        if ret < 0 {
            Err(Error::from(ret))
        } else if block.is_null() {
            Err(Error::NullPointer)
        } else {
            Ok(block)
        }
    }

    pub fn free(&self, block: *mut c_void) -> Result<()> {
        let ret = unsafe { ffi::omi_mem_slab_free(self.raw, block) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }
}

pub struct ThreadHandle {
    raw: *mut c_void,
}

impl ThreadHandle {
    pub fn create(
        entry: unsafe extern "C" fn(*mut c_void, *mut c_void, *mut c_void),
        priority: i32,
    ) -> Result<Self> {
        let raw = unsafe { ffi::omi_thread_create(entry, ptr::null_mut(), ptr::null_mut(), ptr::null_mut(), priority) };
        if raw.is_null() {
            Err(Error::NullPointer)
        } else {
            Ok(Self { raw })
        }
    }

    pub fn start(&self) {
        unsafe { ffi::omi_thread_start(self.raw) };
    }

    pub fn abort(&self) {
        unsafe { ffi::omi_thread_abort(self.raw) };
    }
}

impl Drop for ThreadHandle {
    fn drop(&mut self) {
        self.abort();
    }
}

unsafe impl Send for ThreadHandle {}

pub fn motor_pin() -> Result<GpioPin> {
    GpioPin::new(unsafe { ffi::omi_gpio_pin(ffi::OMI_PIN_MOTOR) })
}

pub fn sleep_ms(ms: u32) {
    unsafe { ffi::omi_sleep_ms(ms) }
}

pub fn busy_wait_us(us: u32) {
    unsafe { ffi::omi_busy_wait_us(us) }
}

pub struct Settings;

impl Settings {
    pub fn new() -> Self {
        Settings
    }

    pub fn init(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_settings_subsys_init() };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn load(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_settings_load() };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn save_one(&self, name: &CStr, value: &[u8]) -> Result<()> {
        let ret = unsafe { ffi::omi_settings_save_one(name.as_ptr(), value.as_ptr() as *const c_void, value.len()) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn register_handler(
        &self,
        subtree: &CStr,
        set_cb: ffi::omi_settings_set_cb,
        user_data: *mut c_void,
    ) -> Result<()> {
        let ret = unsafe { ffi::omi_settings_register_handler(subtree.as_ptr(), set_cb, user_data) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }

    pub fn name_steq(name: *const c_char, key: &CStr, next: &mut *const c_char) -> bool {
        unsafe { ffi::omi_settings_name_steq(name, key.as_ptr(), next) }
    }
}

pub fn register_haptic_service(cb: ffi::omi_haptic_write_cb_t) -> Result<()> {
    let ret = unsafe { ffi::omi_haptic_register_service(cb) };
    if ret < 0 {
        Err(Error::from(ret))
    } else {
        Ok(())
    }
}

pub struct SpiFlash {
    dev: *const c_void,
}

impl SpiFlash {
    pub fn new() -> Result<Self> {
        let dev = unsafe { ffi::omi_device_get(ffi::OMI_DEVICE_SPI_FLASH) };
        if dev.is_null() {
            Err(Error::NullPointer)
        } else {
            Ok(Self { dev })
        }
    }

    pub fn is_ready(&self) -> bool {
        unsafe { ffi::omi_device_is_ready(self.dev) }
    }

    pub fn suspend(&self) -> Result<()> {
        let ret = unsafe { ffi::omi_pm_device_action(self.dev, ffi::PM_DEVICE_ACTION_SUSPEND) };
        if ret < 0 && ret != EALREADY {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }
}

pub struct AdcDevice {
    raw: *const c_void,
}

impl AdcDevice {
    pub fn new() -> Result<Self> {
        let raw = unsafe { ffi::omi_device_get(ffi::OMI_DEVICE_ADC) };
        if raw.is_null() {
            Err(Error::NullPointer)
        } else {
            Ok(Self { raw })
        }
    }

    pub fn raw(&self) -> *const c_void {
        self.raw
    }

    pub fn is_ready(&self) -> bool {
        unsafe { ffi::omi_device_is_ready(self.raw) }
    }

    pub fn ref_internal_mv(&self) -> u16 {
        unsafe { ffi::omi_adc_ref_internal_mv(self.raw) }
    }

    pub fn raw_to_millivolts(&self, gain: i32, resolution: u8, value: &mut i32) -> Result<()> {
        let ret = unsafe { ffi::omi_adc_raw_to_millivolts(self.ref_internal_mv(), gain as _, resolution, value) };
        if ret < 0 {
            Err(Error::from(ret))
        } else {
            Ok(())
        }
    }
}
