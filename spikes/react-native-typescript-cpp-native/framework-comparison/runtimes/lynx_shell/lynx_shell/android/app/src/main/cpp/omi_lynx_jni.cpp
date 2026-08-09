#include <jni.h>
#include <string>
#include <vector>
#include "omi_native_boundary.h"

namespace {
std::string base64Encode(const uint8_t* data, size_t length) {
    static constexpr char alphabet[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string result;
    result.reserve(((length + 2) / 3) * 4);
    for (size_t i = 0; i < length; i += 3) {
        const uint32_t chunk = (static_cast<uint32_t>(data[i]) << 16) |
                               (i + 1 < length ? static_cast<uint32_t>(data[i + 1]) << 8 : 0) |
                               (i + 2 < length ? static_cast<uint32_t>(data[i + 2]) : 0);
        result.push_back(alphabet[(chunk >> 18) & 0x3f]);
        result.push_back(alphabet[(chunk >> 12) & 0x3f]);
        result.push_back(i + 1 < length ? alphabet[(chunk >> 6) & 0x3f] : '=');
        result.push_back(i + 2 < length ? alphabet[chunk & 0x3f] : '=');
    }
    return result;
}
}  // namespace

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
    JNIEnv* env, jobject, jbyteArray raw) {
    if (raw == nullptr) {
        return env->NewStringUTF("{\"status\":-1,\"payloadLength\":0,\"payloadBase64\":\"\"}");
    }

    const jsize length = env->GetArrayLength(raw);
    std::vector<uint8_t> input(static_cast<size_t>(length));
    env->GetByteArrayRegion(raw, 0, length, reinterpret_cast<jbyte*>(input.data()));

    std::vector<uint8_t> output(input.size());
    size_t outputLength = 0;
    const int32_t status = omi_normalize_packet(
        input.data(), input.size(), output.data(), output.size(), &outputLength);
    const std::string payload = base64Encode(output.data(), outputLength);
    const std::string result = "{\"status\":" + std::to_string(status) +
                               ",\"payloadLength\":" + std::to_string(outputLength) +
                               ",\"payloadBase64\":\"" + payload + "\"}";
    return env->NewStringUTF(result.c_str());
}
