#pragma once

#ifdef __cplusplus
extern "C" {
#endif

const char *omi_ble_audio_service_uuid(void);
const char *omi_ble_audio_data_uuid(void);
const char *omi_ble_audio_codec_uuid(void);
const char *omi_ble_audio_speaker_uuid(void);

const char *omi_ble_settings_service_uuid(void);
const char *omi_ble_settings_dim_ratio_uuid(void);

const char *omi_ble_features_service_uuid(void);
const char *omi_ble_features_flags_uuid(void);

const char *omi_ble_storage_service_uuid(void);
const char *omi_ble_storage_command_uuid(void);
const char *omi_ble_storage_status_uuid(void);

const char *omi_ble_button_service_uuid(void);
const char *omi_ble_button_event_uuid(void);

const char *omi_ble_accel_service_uuid(void);
const char *omi_ble_accel_sample_uuid(void);

const char *omi_ble_haptic_service_uuid(void);
const char *omi_ble_haptic_command_uuid(void);

#ifdef __cplusplus
}
#endif
