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
                                                          jbyteArray payload_out) {
    (void)self;
    jsize raw_len = (*env)->GetArrayLength(env, raw);
    jbyte *raw_bytes = (*env)->GetByteArrayElements(env, raw, NULL);
    uint8_t *payload = (uint8_t *)(*env)->GetByteArrayElements(env, payload_out, NULL);
    jint status = omi_normalize_packet((const uint8_t *)raw_bytes, (size_t)raw_len,
                                       payload, (size_t)(*env)->GetArrayLength(env, payload_out));
    (*env)->ReleaseByteArrayElements(env, raw, raw_bytes, JNI_ABORT);
    (*env)->ReleaseByteArrayElements(env, payload_out, (jbyte *)payload, 0);
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
