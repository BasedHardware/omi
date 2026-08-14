#include <jni.h>
#include <vector>
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
