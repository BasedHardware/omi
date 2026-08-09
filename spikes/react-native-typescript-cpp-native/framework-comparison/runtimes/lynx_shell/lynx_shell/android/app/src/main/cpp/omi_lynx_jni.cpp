#include <jni.h>
#include <string>
#include <vector>
#include "omi_native_boundary.h"

extern "C" JNIEXPORT jstring JNICALL
Java_com_lynxshell_modules_OmiNativeModule_nativeCapabilities(JNIEnv* env, jobject) {
    char buffer[256]{};
    const int32_t status = omi_get_native_capabilities(buffer, sizeof(buffer));
    if (status != OMI_STATUS_OK) {
        return env->NewStringUTF("{\"cppBoundary\":\"NATIVE_ADAPTER_UNAVAILABLE\"}");
    }
    return env->NewStringUTF(buffer);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_lynxshell_modules_OmiNativeModule_nativeNormalizePacket(
    JNIEnv* env, jobject, jstring raw) {
    if (raw == nullptr) {
        return env->NewStringUTF("{\"status\":\"NATIVE_ADAPTER_UNAVAILABLE\",\"reason\":\"null input\"}");
    }

    const char* chars = env->GetStringUTFChars(raw, nullptr);
    const jsize length = env->GetStringUTFLength(raw);
    std::vector<uint8_t> input(reinterpret_cast<const uint8_t*>(chars),
                               reinterpret_cast<const uint8_t*>(chars) + length);
    env->ReleaseStringUTFChars(raw, chars);

    std::vector<uint8_t> output(input.size());
    size_t output_length = 0;
    const int32_t status = omi_normalize_packet(
        input.data(), input.size(), output.data(), output.size(), &output_length);

    std::string result = "{\"status\":" + std::to_string(status) +
                         ",\"payloadLength\":" + std::to_string(output_length) + "}";
    return env->NewStringUTF(result.c_str());
}
