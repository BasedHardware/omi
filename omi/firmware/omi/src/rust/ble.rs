use core::ffi::c_char;

use crate::macros::omi_macro_support::{
    BleAccess, BleCharacteristicSpec, BleServiceSpec, CodecSpec,
};
use crate::omi_ble_service;

omi_ble_service!(
    name: audio_service,
    uuid: "19B10000-E8F2-537E-4F6C-D104768A1214",
    advertise: true,
    characteristics: [
        {
            name: data,
            uuid: "19B10001-E8F2-537E-4F6C-D104768A1214",
            access: [Read, Notify],
            codec: Binary
        },
        {
            name: codec,
            uuid: "19B10002-E8F2-537E-4F6C-D104768A1214",
            access: [Read],
            codec: Json(u8)
        },
        {
            name: speaker,
            uuid: "19B10003-E8F2-537E-4F6C-D104768A1214",
            access: [Write, Notify],
            codec: Binary
        }
    ]
);

omi_ble_service!(
    name: settings_service,
    uuid: "19B10010-E8F2-537E-4F6C-D104768A1214",
    advertise: false,
    characteristics: [
        {
            name: dim_ratio,
            uuid: "19B10011-E8F2-537E-4F6C-D104768A1214",
            access: [Read, Write],
            codec: Json(u8)
        }
    ]
);

omi_ble_service!(
    name: features_service,
    uuid: "19B10020-E8F2-537E-4F6C-D104768A1214",
    advertise: false,
    characteristics: [
        {
            name: flags,
            uuid: "19B10021-E8F2-537E-4F6C-D104768A1214",
            access: [Read],
            codec: Json(u32)
        }
    ]
);

omi_ble_service!(
    name: storage_service,
    uuid: "30295780-4301-EABD-2904-2849ADFEAE43",
    advertise: false,
    characteristics: [
        {
            name: command,
            uuid: "30295781-4301-EABD-2904-2849ADFEAE43",
            access: [Write, Notify],
            codec: Binary
        },
        {
            name: status,
            uuid: "30295782-4301-EABD-2904-2849ADFEAE43",
            access: [Read, Notify],
            codec: Binary
        }
    ]
);

omi_ble_service!(
    name: button_service,
    uuid: "23BA7924-0000-1000-7450-346EAC492E92",
    advertise: false,
    characteristics: [
        {
            name: event,
            uuid: "23BA7925-0000-1000-7450-346EAC492E92",
            access: [Read, Notify],
            codec: Binary
        }
    ]
);

omi_ble_service!(
    name: accel_service,
    uuid: "32403790-0000-1000-7450-BF445E5829A2",
    advertise: false,
    characteristics: [
        {
            name: sample,
            uuid: "32403791-0000-1000-7450-BF445E5829A2",
            access: [Read, Notify],
            codec: Binary
        }
    ]
);

omi_ble_service!(
    name: haptic_service,
    uuid: "CAB1AB95-2EA5-4F4D-BB56-874B72CFC984",
    advertise: false,
    characteristics: [
        {
            name: command,
            uuid: "CAB1AB96-2EA5-4F4D-BB56-874B72CFC984",
            access: [Write],
            codec: Binary
        }
    ]
);

pub use accel_service::Characteristic as AccelCharacteristic;
pub use audio_service::Characteristic as AudioCharacteristic;
pub use button_service::Characteristic as ButtonCharacteristic;
pub use features_service::Characteristic as FeaturesCharacteristic;
pub use haptic_service::Characteristic as HapticCharacteristic;
pub use settings_service::Characteristic as SettingsCharacteristic;
pub use storage_service::Characteristic as StorageCharacteristic;

pub const AUDIO_SERVICE: &BleServiceSpec = &audio_service::SPEC;
pub const SETTINGS_SERVICE: &BleServiceSpec = &settings_service::SPEC;
pub const FEATURES_SERVICE: &BleServiceSpec = &features_service::SPEC;
pub const STORAGE_SERVICE: &BleServiceSpec = &storage_service::SPEC;
pub const BUTTON_SERVICE: &BleServiceSpec = &button_service::SPEC;
pub const ACCEL_SERVICE: &BleServiceSpec = &accel_service::SPEC;
pub const HAPTIC_SERVICE: &BleServiceSpec = &haptic_service::SPEC;

pub fn audio_service_spec() -> &'static BleServiceSpec {
    AUDIO_SERVICE
}

pub fn settings_service_spec() -> &'static BleServiceSpec {
    SETTINGS_SERVICE
}

pub fn features_service_spec() -> &'static BleServiceSpec {
    FEATURES_SERVICE
}

pub fn storage_service_spec() -> &'static BleServiceSpec {
    STORAGE_SERVICE
}

pub fn button_service_spec() -> &'static BleServiceSpec {
    BUTTON_SERVICE
}

pub fn accel_service_spec() -> &'static BleServiceSpec {
    ACCEL_SERVICE
}

pub fn haptic_service_spec() -> &'static BleServiceSpec {
    HAPTIC_SERVICE
}

pub fn haptic_command() -> &'static BleCharacteristicSpec {
    &haptic_service::command
}

pub fn haptic_command_access() -> &'static [BleAccess] {
    haptic_command().access()
}

pub fn haptic_command_codec() -> CodecSpec {
    haptic_command().codec()
}

pub fn services() -> &'static [&'static BleServiceSpec] {
    &[
        AUDIO_SERVICE,
        SETTINGS_SERVICE,
        FEATURES_SERVICE,
        STORAGE_SERVICE,
        BUTTON_SERVICE,
        ACCEL_SERVICE,
        HAPTIC_SERVICE,
    ]
}

pub fn advertised_services() -> &'static [&'static BleServiceSpec] {
    &[AUDIO_SERVICE]
}

fn c_str_ptr(s: &'static str) -> *const c_char {
    s.as_ptr() as *const c_char
}

#[no_mangle]
pub extern "C" fn omi_ble_audio_service_uuid() -> *const c_char {
    c_str_ptr(audio_service::uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_audio_data_uuid() -> *const c_char {
    c_str_ptr(AudioCharacteristic::data.uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_audio_codec_uuid() -> *const c_char {
    c_str_ptr(AudioCharacteristic::codec.uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_audio_speaker_uuid() -> *const c_char {
    c_str_ptr(AudioCharacteristic::speaker.uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_settings_service_uuid() -> *const c_char {
    c_str_ptr(settings_service::uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_settings_dim_ratio_uuid() -> *const c_char {
    c_str_ptr(SettingsCharacteristic::dim_ratio.uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_features_service_uuid() -> *const c_char {
    c_str_ptr(features_service::uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_features_flags_uuid() -> *const c_char {
    c_str_ptr(FeaturesCharacteristic::flags.uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_storage_service_uuid() -> *const c_char {
    c_str_ptr(storage_service::uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_storage_command_uuid() -> *const c_char {
    c_str_ptr(StorageCharacteristic::command.uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_storage_status_uuid() -> *const c_char {
    c_str_ptr(StorageCharacteristic::status.uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_button_service_uuid() -> *const c_char {
    c_str_ptr(button_service::uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_button_event_uuid() -> *const c_char {
    c_str_ptr(ButtonCharacteristic::event.uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_accel_service_uuid() -> *const c_char {
    c_str_ptr(accel_service::uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_accel_sample_uuid() -> *const c_char {
    c_str_ptr(AccelCharacteristic::sample.uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_haptic_service_uuid() -> *const c_char {
    c_str_ptr(haptic_service::uuid_cstr())
}

#[no_mangle]
pub extern "C" fn omi_ble_haptic_command_uuid() -> *const c_char {
    c_str_ptr(HapticCharacteristic::command.uuid_cstr())
}
