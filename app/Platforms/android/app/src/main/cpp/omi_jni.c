/*
 * omi_jni.c — JNI shim binding the SAME native-core C++ middleware the Apple
 * hosts compile (through CNativeCore in Package.swift). The middleware stays
 * C++; this file only marshals Kotlin strings/arrays onto the C ABI.
 *
 * Requires Kotlin/NDK symbol names for omi.v5.host.OmiPolicyJniBridge.
 */
#include <jni.h>
#include <stdint.h>
#include <string.h>

#include "omi_backend_policy.h"
#include "omi_backend_recording.h"
#include "omi_device.h"
#include "omi_native_boundary.h"

#define JNI_CLASS omi_v5_host_OmiPolicyJniBridge

static char *dup_jstring(JNIEnv *env, jstring s) {
    if (s == NULL) return NULL;
    const char *utf = (*env)->GetStringUTFChars(env, s, NULL);
    if (utf == NULL) return NULL;
    /* callers free(); small policy strings only */
    size_t n = strlen(utf) + 1;
    char *copy = (char *)malloc(n);
    if (copy != NULL) memcpy(copy, utf, n);
    (*env)->ReleaseStringUTFChars(env, s, utf);
    return copy;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeRouteStrip(JNIEnv *env, jobject self,
                                                     jstring path, jbyteArray out) {
    (void)self;
    char *p = dup_jstring(env, path);
    if (p == NULL) return 0;
    jsize cap = (*env)->GetArrayLength(env, out);
    char *buf = (char *)malloc((size_t)cap);
    jint written = 0;
    if (omi_backend_route_strip(p, buf, (size_t)cap) == 0) {
        written = (jint)strlen(buf);
        (*env)->SetByteArrayRegion(env, out, 0, written, (jbyte *)buf);
    }
    free(buf);
    free(p);
    return written;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeIsCapturePath(JNIEnv *env, jobject self, jstring path) {
    (void)self;
    char *p = dup_jstring(env, path);
    jint r = p != NULL ? omi_backend_is_capture_path(p) : 0;
    free(p);
    return r;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeRequestTimeoutSeconds(JNIEnv *env, jobject self,
                                                                jstring method, jstring path) {
    (void)self;
    char *m = dup_jstring(env, method);
    char *p = dup_jstring(env, path);
    jint r = omi_backend_request_timeout_seconds(m, p);
    free(m);
    free(p);
    return r;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeExamplePlatformSupported(JNIEnv *env, jobject self,
                                                                   jstring method, jstring path) {
    (void)self;
    char *m = dup_jstring(env, method);
    char *p = dup_jstring(env, path);
    jint r = omi_backend_example_platform_supported(m, p);
    free(m);
    free(p);
    return r;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeIsLoopbackHostname(JNIEnv *env, jobject self,
                                                             jstring hostname) {
    (void)self;
    char *h = dup_jstring(env, hostname);
    jint r = omi_backend_is_loopback_hostname(h);
    free(h);
    return r;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeIsCloudHostname(JNIEnv *env, jobject self,
                                                          jstring hostname) {
    (void)self;
    char *h = dup_jstring(env, hostname);
    jint r = omi_backend_is_cloud_hostname(h);
    free(h);
    return r;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeIsAllowedV5Hostname(JNIEnv *env, jobject self,
                                                              jstring hostname) {
    (void)self;
    char *h = dup_jstring(env, hostname);
    jint r = omi_backend_is_allowed_v5_hostname(h);
    free(h);
    return r;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeSoftwarePlaneIsNew(JNIEnv *env, jobject self,
                                                             jstring stored,
                                                             jboolean stamped_valid) {
    (void)self;
    char *s = dup_jstring(env, stored);
    jint r = omi_backend_software_plane_is_new(s, stamped_valid == JNI_TRUE ? 1 : 0);
    free(s);
    return r;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeRecordingCapturedAtValid(JNIEnv *env, jobject self,
                                                                   jdouble seconds) {
    (void)env;
    (void)self;
    return omi_backend_recording_captured_at_valid(seconds);
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeRecordingRetryableStatus(JNIEnv *env, jobject self,
                                                                   jint status) {
    (void)env;
    (void)self;
    return omi_backend_recording_retryable_status(status);
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeRecordingOwnerKeyValid(JNIEnv *env, jobject self,
                                                                 jstring owner_key) {
    (void)self;
    char *k = dup_jstring(env, owner_key);
    jint r = omi_backend_recording_owner_key_valid(k);
    free(k);
    return r;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeRecordingReceiptValid(JNIEnv *env, jobject self,
                                                                jstring receipt) {
    (void)self;
    char *r0 = dup_jstring(env, receipt);
    jint r = omi_backend_recording_receipt_valid(r0);
    free(r0);
    return r;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeRecordingUUIDValid(JNIEnv *env, jobject self,
                                                             jstring value) {
    (void)self;
    char *v = dup_jstring(env, value);
    jint r = omi_backend_recording_uuid_valid(v);
    free(v);
    return r;
}

JNIEXPORT jlong JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativePacketChecksum(JNIEnv *env, jobject self,
                                                         jbyteArray data) {
    (void)self;
    jsize n = (*env)->GetArrayLength(env, data);
    jbyte *bytes = (*env)->GetByteArrayElements(env, data, NULL);
    uint32_t crc = omi_calculate_packet_checksum((const uint8_t *)bytes, (size_t)n);
    (*env)->ReleaseByteArrayElements(env, data, bytes, JNI_ABORT);
    return (jlong)crc;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeNormalizePacket(JNIEnv *env, jobject self,
                                                          jbyteArray raw,
                                                          jbyteArray payload_out,
                                                          jintArray meta_out) {
    (void)self;
    jsize raw_len = (*env)->GetArrayLength(env, raw);
    jbyte *raw_bytes = (*env)->GetByteArrayElements(env, raw, NULL);
    uint8_t *payload = (uint8_t *)(*env)->GetByteArrayElements(env, payload_out, NULL);
    size_t payload_len = 0;
    jint status = omi_normalize_packet((const uint8_t *)raw_bytes, (size_t)raw_len,
                                       payload,
                                       (size_t)(*env)->GetArrayLength(env, payload_out),
                                       &payload_len);
    (*env)->ReleaseByteArrayElements(env, raw, raw_bytes, JNI_ABORT);
    (*env)->ReleaseByteArrayElements(env, payload_out, (jbyte *)payload, 0);
    if (meta_out != NULL && (*env)->GetArrayLength(env, meta_out) >= 1) {
        jint meta[1] = {(jint)payload_len};
        (*env)->SetIntArrayRegion(env, meta_out, 0, 1, meta);
    }
    return status;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeGetNativeCapabilities(JNIEnv *env, jobject self,
                                                                jbyteArray out) {
    (void)self;
    jsize cap = (*env)->GetArrayLength(env, out);
    char *buf = (char *)malloc((size_t)cap);
    jint written = 0;
    if (omi_get_native_capabilities(buf, (size_t)cap) == 0) {
        written = (jint)strlen(buf);
        (*env)->SetByteArrayRegion(env, out, 0, written, (jbyte *)buf);
    }
    free(buf);
    return written;
}

/* ------------------------------------------------------------------ */
/* omi_device — portable BLE device logic through the same C ABI.      */
/* Handles are native pointers carried as jlong.                       */
/* ------------------------------------------------------------------ */

static void *dev_handle(jlong handle) { return (void *)(uintptr_t)handle; }

JNIEXPORT jstring JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceDiscoveredName(
    JNIEnv *env, jobject self, jstring advertised, jstring cached, jbyteArray manufacturer) {
    (void)self;
    char *a = dup_jstring(env, advertised);
    char *c = dup_jstring(env, cached);
    uint8_t stack[512];
    const uint8_t *data = NULL;
    size_t data_len = 0;
    if (manufacturer != NULL) {
        jsize len = (*env)->GetArrayLength(env, manufacturer);
        if (len > 0) {
            if ((size_t)len > sizeof(stack)) len = (jsize)sizeof(stack);
            (*env)->GetByteArrayRegion(env, manufacturer, 0, len, (jbyte *)stack);
            data = stack;
            data_len = (size_t)len;
        }
    }
    char out[256];
    jint written = (jint)omi_device_discovered_name(a, c, data, data_len, out, sizeof(out));
    free(a);
    free(c);
    if (written < 0) written = 0;
    return (*env)->NewStringUTF(env, out);
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceIsNotePinAdvertisement(
    JNIEnv *env, jobject self, jbyteArray manufacturer) {
    (void)self;
    if (manufacturer == NULL) return 0;
    jsize len = (*env)->GetArrayLength(env, manufacturer);
    if (len <= 0) return 0;
    uint8_t stack[512];
    if ((size_t)len > sizeof(stack)) len = (jsize)sizeof(stack);
    (*env)->GetByteArrayRegion(env, manufacturer, 0, len, (jbyte *)stack);
    return omi_device_is_note_pin_advertisement(stack, (size_t)len);
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceIsOmiLike(JNIEnv *env, jobject self,
                                                          jstring name) {
    (void)self;
    char *n = dup_jstring(env, name);
    jint r = n != NULL ? omi_device_is_omi_like(n) : 0;
    free(n);
    return r;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceShouldPersistBatteryReading(
    JNIEnv *env, jobject self, jint previous_level, jboolean has_previous_level,
    jlong previous_timestamp_ms, jboolean has_previous_timestamp_ms, jint level,
    jlong now_ms) {
    (void)env;
    (void)self;
    return omi_device_should_persist_battery_reading(
        previous_level, has_previous_level == JNI_TRUE ? 1 : 0, previous_timestamp_ms,
        has_previous_timestamp_ms == JNI_TRUE ? 1 : 0, level, now_ms);
}

JNIEXPORT jstring JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCharacteristicText(JNIEnv *env, jobject self,
                                                                   jbyteArray bytes) {
    (void)self;
    if (bytes == NULL) return NULL;
    jsize len = (*env)->GetArrayLength(env, bytes);
    if (len <= 0) return NULL;
    uint8_t stack[2048];
    if ((size_t)len > sizeof(stack)) len = (jsize)sizeof(stack);
    (*env)->GetByteArrayRegion(env, bytes, 0, len, (jbyte *)stack);
    char out[2048];
    jint written = (jint)omi_device_characteristic_text(stack, (size_t)len, out, sizeof(out));
    if (written < 0) return NULL;
    return (*env)->NewStringUTF(env, out);
}

JNIEXPORT jlong JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceAssemblerCreate(JNIEnv *env, jobject self) {
    (void)env;
    (void)self;
    return (jlong)(uintptr_t)omi_device_assembler_create();
}

JNIEXPORT void JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceAssemblerDestroy(JNIEnv *env, jobject self,
                                                                 jlong handle) {
    (void)env;
    (void)self;
    omi_device_assembler_destroy(dev_handle(handle));
}

JNIEXPORT void JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceAssemblerReset(JNIEnv *env, jobject self,
                                                               jlong handle) {
    (void)env;
    (void)self;
    omi_device_assembler_reset(dev_handle(handle));
}

/* Classify: returns [kind, index, payload_len, codec_status]; the normalized
 * payload is copied into payload_out. */
JNIEXPORT jintArray JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceAssemblerClassify(JNIEnv *env, jobject self,
                                                                  jlong handle,
                                                                  jbyteArray raw,
                                                                  jbyteArray payload_out) {
    (void)self;
    void *assembler = dev_handle(handle);
    if (assembler == NULL) return NULL;
    jsize raw_len = (*env)->GetArrayLength(env, raw);
    jbyte *raw_bytes = (*env)->GetByteArrayElements(env, raw, NULL);
    uint8_t *payload = (uint8_t *)(*env)->GetByteArrayElements(env, payload_out, NULL);
    uint16_t index = 0;
    size_t payload_len = 0;
    int32_t codec_status = 0;
    int32_t kind = omi_device_assembler_classify(
        assembler, (const uint8_t *)raw_bytes, (size_t)raw_len, &index, payload,
        (size_t)(*env)->GetArrayLength(env, payload_out), &payload_len, &codec_status);
    (*env)->ReleaseByteArrayElements(env, raw, raw_bytes, JNI_ABORT);
    (*env)->ReleaseByteArrayElements(env, payload_out, (jbyte *)payload, 0);
    jint meta[4] = {kind, index, (jint)payload_len, codec_status};
    jintArray result = (*env)->NewIntArray(env, 4);
    (*env)->SetIntArrayRegion(env, result, 0, 4, meta);
    return result;
}

JNIEXPORT jlong JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureCreate(JNIEnv *env, jobject self) {
    (void)env;
    (void)self;
    return (jlong)(uintptr_t)omi_device_capture_create();
}

JNIEXPORT void JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureDestroy(JNIEnv *env, jobject self,
                                                               jlong handle) {
    (void)env;
    (void)self;
    omi_device_capture_destroy(dev_handle(handle));
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureStage(JNIEnv *env, jobject self,
                                                             jlong handle) {
    (void)env;
    (void)self;
    return omi_device_capture_stage(dev_handle(handle));
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureIsCapturing(JNIEnv *env, jobject self,
                                                                   jlong handle) {
    (void)env;
    (void)self;
    return omi_device_capture_is_capturing(dev_handle(handle));
}

JNIEXPORT jboolean JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureOpen(JNIEnv *env, jobject self,
                                                            jlong handle, jstring device_id,
                                                            jstring device_name, jint codec,
                                                            jlong now_ms) {
    (void)self;
    void *machine = dev_handle(handle);
    if (machine == NULL) return JNI_FALSE;
    char *id = dup_jstring(env, device_id);
    char *name = dup_jstring(env, device_name);
    jint status = omi_device_capture_open(machine, id, name, codec, now_ms);
    free(id);
    free(name);
    return status == OMI_STATUS_OK ? JNI_TRUE : JNI_FALSE;
}

/* Ingest: returns the accepted packet index (>= 0) or -1. */
JNIEXPORT jlong JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureIngest(JNIEnv *env, jobject self,
                                                              jlong handle, jbyteArray raw,
                                                              jlong received_at_ms) {
    (void)self;
    void *machine = dev_handle(handle);
    if (machine == NULL) return -1;
    jsize raw_len = (*env)->GetArrayLength(env, raw);
    jbyte *raw_bytes = (*env)->GetByteArrayElements(env, raw, NULL);
    uint16_t index = 0;
    jint accepted = omi_device_capture_ingest(machine, (const uint8_t *)raw_bytes,
                                              (size_t)raw_len, received_at_ms, &index);
    (*env)->ReleaseByteArrayElements(env, raw, raw_bytes, JNI_ABORT);
    return accepted == 1 ? (jlong)index : -1;
}

JNIEXPORT void JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureFail(JNIEnv *env, jobject self,
                                                            jlong handle) {
    (void)env;
    (void)self;
    omi_device_capture_fail(dev_handle(handle));
}

/* Handoff: returns JNI_TRUE when a nonempty batch was handed off; outs = a
 * jlongArray of 3 filled with [started_at_ms, ended_at_ms, byte_count]. */
JNIEXPORT jboolean JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureHandoff(JNIEnv *env, jobject self,
                                                               jlong handle, jlong now_ms,
                                                               jlongArray outs) {
    (void)self;
    void *machine = dev_handle(handle);
    if (machine == NULL) return JNI_FALSE;
    int64_t started = 0;
    int64_t ended = 0;
    size_t byte_count = 0;
    jint outcome =
        omi_device_capture_handoff(machine, now_ms, &started, &ended, &byte_count);
    if (outs != NULL && (*env)->GetArrayLength(env, outs) >= 3) {
        jlong values[3] = {started, ended, (jlong)byte_count};
        (*env)->SetLongArrayRegion(env, outs, 0, 3, values);
    }
    return outcome == 1 ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureBatchCount(JNIEnv *env, jobject self,
                                                                  jlong handle) {
    (void)env;
    (void)self;
    return (jint)omi_device_capture_batch_count(dev_handle(handle));
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureBatchByteCount(JNIEnv *env,
                                                                      jobject self,
                                                                      jlong handle) {
    (void)env;
    (void)self;
    return (jint)omi_device_capture_batch_byte_count(dev_handle(handle));
}

JNIEXPORT jlong JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureStartedAtMs(JNIEnv *env, jobject self,
                                                                   jlong handle) {
    (void)env;
    (void)self;
    return omi_device_capture_started_at_ms(dev_handle(handle));
}

/* Packet at: returns [status, index, payload_len]; received_at_ms in outs[0]. */
JNIEXPORT jintArray JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCapturePacketAt(JNIEnv *env, jobject self,
                                                                jlong handle, jint position,
                                                                jbyteArray payload_out,
                                                                jlongArray outs) {
    (void)self;
    void *machine = dev_handle(handle);
    if (machine == NULL) return NULL;
    uint8_t *payload = (uint8_t *)(*env)->GetByteArrayElements(env, payload_out, NULL);
    uint16_t index = 0;
    size_t payload_len = 0;
    int64_t received_at_ms = 0;
    jint status = omi_device_capture_packet_at(
        machine, (size_t)position, &index, payload,
        (size_t)(*env)->GetArrayLength(env, payload_out), &payload_len, &received_at_ms);
    (*env)->ReleaseByteArrayElements(env, payload_out, (jbyte *)payload, 0);
    jint meta[3] = {status, index, (jint)payload_len};
    jintArray result = (*env)->NewIntArray(env, 3);
    (*env)->SetIntArrayRegion(env, result, 0, 3, meta);
    if (outs != NULL && (*env)->GetArrayLength(env, outs) >= 1) {
        jlong values[1] = {received_at_ms};
        (*env)->SetLongArrayRegion(env, outs, 0, 1, values);
    }
    return result;
}

JNIEXPORT jstring JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureDeviceId(JNIEnv *env, jobject self,
                                                                jlong handle) {
    (void)self;
    void *machine = dev_handle(handle);
    if (machine == NULL) return NULL;
    char out[256];
    if (omi_device_capture_device_id(machine, out, sizeof(out)) < 0) return NULL;
    return (*env)->NewStringUTF(env, out);
}

JNIEXPORT jstring JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureDeviceName(JNIEnv *env, jobject self,
                                                                  jlong handle) {
    (void)self;
    void *machine = dev_handle(handle);
    if (machine == NULL) return NULL;
    char out[256];
    if (omi_device_capture_device_name(machine, out, sizeof(out)) < 0) return NULL;
    return (*env)->NewStringUTF(env, out);
}

JNIEXPORT jint JNICALL
Java_omi_v5_host_OmiPolicyJniBridge_nativeDeviceCaptureCodec(JNIEnv *env, jobject self,
                                                             jlong handle) {
    (void)env;
    (void)self;
    return omi_device_capture_codec(dev_handle(handle));
}
