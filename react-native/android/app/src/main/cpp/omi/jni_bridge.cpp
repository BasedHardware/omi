#include <jni.h>
#include <vector>

#include "omi_backend_http.h"
#include "omi_backend_policy.h"
#include "omi_backend_recording.h"
#include "omi_native_boundary.h"

extern "C" JNIEXPORT jstring JNICALL
Java_com_rnruntime_OmiNativeModule_nativeCapabilities(JNIEnv* env, jobject) {
  char buffer[256] = {};
  if (omi_get_native_capabilities(buffer, sizeof(buffer)) != OMI_STATUS_OK) {
    return env->NewStringUTF("{}");
  }
  return env->NewStringUTF(buffer);
}

extern "C" JNIEXPORT jbyteArray JNICALL
Java_com_rnruntime_OmiNativeModule_nativeNormalizePacket(JNIEnv* env, jobject, jbyteArray raw) {
  if (raw == nullptr) return nullptr;
  const jsize rawLength = env->GetArrayLength(raw);
  std::vector<uint8_t> input(static_cast<size_t>(rawLength));
  env->GetByteArrayRegion(raw, 0, rawLength, reinterpret_cast<jbyte*>(input.data()));
  std::vector<uint8_t> output(input.size());
  size_t outputLength = 0;
  const auto status = omi_normalize_packet(input.data(), input.size(), output.data(), output.size(), &outputLength);
  if (status != OMI_STATUS_OK) return nullptr;
  auto result = env->NewByteArray(static_cast<jsize>(outputLength));
  env->SetByteArrayRegion(result, 0, static_cast<jsize>(outputLength), reinterpret_cast<const jbyte*>(output.data()));
  return result;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativePolicyAvailable(JNIEnv*, jclass) {
  return JNI_TRUE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeIsCapturePath(JNIEnv* env, jclass, jstring path) {
  if (path == nullptr) return JNI_FALSE;
  const char* utf = env->GetStringUTFChars(path, nullptr);
  if (utf == nullptr) return JNI_FALSE;
  const int32_t result = omi_backend_is_capture_path(utf);
  env->ReleaseStringUTFChars(path, utf);
  return result == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jint JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRequestTimeoutSeconds(JNIEnv* env, jclass, jstring method, jstring path) {
  const char* methodUtf = nullptr;
  const char* pathUtf = nullptr;
  if (method != nullptr) methodUtf = env->GetStringUTFChars(method, nullptr);
  if (path != nullptr) pathUtf = env->GetStringUTFChars(path, nullptr);
  const int32_t seconds = omi_backend_request_timeout_seconds(
      methodUtf == nullptr ? "" : methodUtf,
      pathUtf == nullptr ? "" : pathUtf);
  if (method != nullptr && methodUtf != nullptr) env->ReleaseStringUTFChars(method, methodUtf);
  if (path != nullptr && pathUtf != nullptr) env->ReleaseStringUTFChars(path, pathUtf);
  return seconds;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeExamplePlatformSupported(JNIEnv* env, jclass, jstring method, jstring path) {
  if (method == nullptr || path == nullptr) return JNI_FALSE;
  const char* methodUtf = env->GetStringUTFChars(method, nullptr);
  const char* pathUtf = env->GetStringUTFChars(path, nullptr);
  if (methodUtf == nullptr || pathUtf == nullptr) {
    if (methodUtf != nullptr) env->ReleaseStringUTFChars(method, methodUtf);
    if (pathUtf != nullptr) env->ReleaseStringUTFChars(path, pathUtf);
    return JNI_FALSE;
  }
  const int32_t result = omi_backend_example_platform_supported(methodUtf, pathUtf);
  env->ReleaseStringUTFChars(method, methodUtf);
  env->ReleaseStringUTFChars(path, pathUtf);
  return result == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeHttpRequestValid(JNIEnv* env, jclass, jstring method, jstring path) {
  if (method == nullptr || path == nullptr) return JNI_FALSE;
  const char* methodUtf = env->GetStringUTFChars(method, nullptr);
  const char* pathUtf = env->GetStringUTFChars(path, nullptr);
  if (methodUtf == nullptr || pathUtf == nullptr) {
    if (methodUtf != nullptr) env->ReleaseStringUTFChars(method, methodUtf);
    if (pathUtf != nullptr) env->ReleaseStringUTFChars(path, pathUtf);
    return JNI_FALSE;
  }
  const int32_t result = omi_backend_http_request_valid(methodUtf, pathUtf);
  env->ReleaseStringUTFChars(method, methodUtf);
  env->ReleaseStringUTFChars(path, pathUtf);
  return result == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingPathOwned(JNIEnv* env, jclass, jstring method, jstring path, jstring sessionId) {
  if (method == nullptr || path == nullptr) return JNI_FALSE;
  const char* methodUtf = env->GetStringUTFChars(method, nullptr);
  const char* pathUtf = env->GetStringUTFChars(path, nullptr);
  const char* sessionUtf = sessionId == nullptr ? nullptr : env->GetStringUTFChars(sessionId, nullptr);
  if (methodUtf == nullptr || pathUtf == nullptr) {
    if (methodUtf != nullptr) env->ReleaseStringUTFChars(method, methodUtf);
    if (pathUtf != nullptr) env->ReleaseStringUTFChars(path, pathUtf);
    if (sessionId != nullptr && sessionUtf != nullptr) env->ReleaseStringUTFChars(sessionId, sessionUtf);
    return JNI_FALSE;
  }
  const int32_t result = omi_backend_recording_path_owned(methodUtf, pathUtf, sessionUtf);
  env->ReleaseStringUTFChars(method, methodUtf);
  env->ReleaseStringUTFChars(path, pathUtf);
  if (sessionId != nullptr && sessionUtf != nullptr) env->ReleaseStringUTFChars(sessionId, sessionUtf);
  return result == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingJournalRelpath(JNIEnv* env, jclass, jstring partitionHex, jstring captureId) {
  if (partitionHex == nullptr || captureId == nullptr) return nullptr;
  const char* partitionUtf = env->GetStringUTFChars(partitionHex, nullptr);
  const char* captureUtf = env->GetStringUTFChars(captureId, nullptr);
  if (partitionUtf == nullptr || captureUtf == nullptr) {
    if (partitionUtf != nullptr) env->ReleaseStringUTFChars(partitionHex, partitionUtf);
    if (captureUtf != nullptr) env->ReleaseStringUTFChars(captureId, captureUtf);
    return nullptr;
  }
  char buffer[160];
  const int32_t written = omi_backend_recording_journal_relpath(
      partitionUtf, captureUtf, buffer, sizeof(buffer));
  env->ReleaseStringUTFChars(partitionHex, partitionUtf);
  env->ReleaseStringUTFChars(captureId, captureUtf);
  if (written < 0) return nullptr;
  return env->NewStringUTF(buffer);
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingCapturedAtValid(JNIEnv*, jclass, jdouble value) {
  return omi_backend_recording_captured_at_valid(value) == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingCapturedAtEqual(JNIEnv*, jclass, jboolean expectedPresent, jdouble expected, jboolean actualPresent, jdouble actual) {
  return omi_backend_recording_captured_at_equal(expectedPresent == JNI_TRUE ? 1 : 0, expected,
                                                  actualPresent == JNI_TRUE ? 1 : 0, actual) == 1
             ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingRetryableStatus(JNIEnv*, jclass, jint status) {
  return omi_backend_recording_retryable_status(status) == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingSameContext(JNIEnv* env, jclass, jstring expectedLogin, jstring currentLogin, jstring expectedOrigin, jstring currentOrigin) {
  const char* expectedLoginUtf = expectedLogin == nullptr ? nullptr : env->GetStringUTFChars(expectedLogin, nullptr);
  const char* currentLoginUtf = currentLogin == nullptr ? nullptr : env->GetStringUTFChars(currentLogin, nullptr);
  const char* expectedOriginUtf = expectedOrigin == nullptr ? nullptr : env->GetStringUTFChars(expectedOrigin, nullptr);
  const char* currentOriginUtf = currentOrigin == nullptr ? nullptr : env->GetStringUTFChars(currentOrigin, nullptr);
  const int32_t result = omi_backend_recording_same_context(expectedLoginUtf, currentLoginUtf, expectedOriginUtf, currentOriginUtf);
  if (expectedLogin != nullptr && expectedLoginUtf != nullptr) env->ReleaseStringUTFChars(expectedLogin, expectedLoginUtf);
  if (currentLogin != nullptr && currentLoginUtf != nullptr) env->ReleaseStringUTFChars(currentLogin, currentLoginUtf);
  if (expectedOrigin != nullptr && expectedOriginUtf != nullptr) env->ReleaseStringUTFChars(expectedOrigin, expectedOriginUtf);
  if (currentOrigin != nullptr && currentOriginUtf != nullptr) env->ReleaseStringUTFChars(currentOrigin, currentOriginUtf);
  return result == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingRememberedIdentity(JNIEnv* env, jclass, jstring identifier, jstring name) {
  const char* identifierUtf = identifier == nullptr ? nullptr : env->GetStringUTFChars(identifier, nullptr);
  const char* nameUtf = name == nullptr ? nullptr : env->GetStringUTFChars(name, nullptr);
  const int32_t result = omi_backend_recording_remembered_identity(identifierUtf, nameUtf);
  if (identifier != nullptr && identifierUtf != nullptr) env->ReleaseStringUTFChars(identifier, identifierUtf);
  if (name != nullptr && nameUtf != nullptr) env->ReleaseStringUTFChars(name, nameUtf);
  return result == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingRememberedCurrent(JNIEnv* env, jclass, jlong ticket, jlong generation, jstring expectedLogin, jstring currentLogin, jboolean ready) {
  const char* expectedLoginUtf = expectedLogin == nullptr ? nullptr : env->GetStringUTFChars(expectedLogin, nullptr);
  const char* currentLoginUtf = currentLogin == nullptr ? nullptr : env->GetStringUTFChars(currentLogin, nullptr);
  const int32_t result = omi_backend_recording_remembered_current(
      static_cast<uint64_t>(ticket), static_cast<uint64_t>(generation), expectedLoginUtf,
      currentLoginUtf, ready == JNI_TRUE ? 1 : 0);
  if (expectedLogin != nullptr && expectedLoginUtf != nullptr) env->ReleaseStringUTFChars(expectedLogin, expectedLoginUtf);
  if (currentLogin != nullptr && currentLoginUtf != nullptr) env->ReleaseStringUTFChars(currentLogin, currentLoginUtf);
  return result == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingDeviceValid(JNIEnv* env, jclass, jstring deviceId, jstring deviceName, jdouble codec) {
  const char* deviceIdUtf = deviceId == nullptr ? nullptr : env->GetStringUTFChars(deviceId, nullptr);
  const char* deviceNameUtf = deviceName == nullptr ? nullptr : env->GetStringUTFChars(deviceName, nullptr);
  const int32_t result = omi_backend_recording_device_valid(
      deviceIdUtf, deviceName == nullptr ? 0 : 1, deviceNameUtf, codec);
  if (deviceId != nullptr && deviceIdUtf != nullptr) env->ReleaseStringUTFChars(deviceId, deviceIdUtf);
  if (deviceName != nullptr && deviceNameUtf != nullptr) env->ReleaseStringUTFChars(deviceName, deviceNameUtf);
  return result == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingBudgetOk(JNIEnv*, jclass, jlong totalBytes, jlong extraBytes, jboolean creating, jint fileCount) {
  return omi_backend_recording_budget_ok(static_cast<uint64_t>(totalBytes), static_cast<uint64_t>(extraBytes),
                                         creating == JNI_TRUE ? 1 : 0, static_cast<uint32_t>(fileCount)) == 1
             ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingOwnerKeyValid(JNIEnv* env, jclass, jstring ownerKey) {
  if (ownerKey == nullptr) return JNI_FALSE;
  const char* utf = env->GetStringUTFChars(ownerKey, nullptr);
  if (utf == nullptr) return JNI_FALSE;
  const int32_t result = omi_backend_recording_owner_key_valid(utf);
  env->ReleaseStringUTFChars(ownerKey, utf);
  return result == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingReceiptValid(JNIEnv* env, jclass, jstring receipt) {
  if (receipt == nullptr) return JNI_FALSE;
  const char* utf = env->GetStringUTFChars(receipt, nullptr);
  if (utf == nullptr) return JNI_FALSE;
  const int32_t result = omi_backend_recording_receipt_valid(utf);
  env->ReleaseStringUTFChars(receipt, utf);
  return result == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeRecordingUuidValid(JNIEnv* env, jclass, jstring value) {
  if (value == nullptr) return JNI_FALSE;
  const char* utf = env->GetStringUTFChars(value, nullptr);
  if (utf == nullptr) return JNI_FALSE;
  const int32_t result = omi_backend_recording_uuid_valid(utf);
  env->ReleaseStringUTFChars(value, utf);
  return result == 1 ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_rnruntime_OmiBackendTransport_nativeSoftwarePlaneIsNew(JNIEnv* env, jclass, jstring stored, jboolean stampedValid) {
  const char* storedUtf = stored == nullptr ? nullptr : env->GetStringUTFChars(stored, nullptr);
  const int32_t result = omi_backend_software_plane_is_new(storedUtf, stampedValid == JNI_TRUE ? 1 : 0);
  if (stored != nullptr && storedUtf != nullptr) env->ReleaseStringUTFChars(stored, storedUtf);
  return result == 1 ? JNI_TRUE : JNI_FALSE;
}
