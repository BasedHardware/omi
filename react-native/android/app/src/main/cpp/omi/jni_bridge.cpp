#include <jni.h>
#include <vector>

#include "omi_backend_http.h"
#include "omi_backend_policy.h"
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
