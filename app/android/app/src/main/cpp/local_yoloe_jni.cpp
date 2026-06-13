#include <jni.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include <android/log.h>
#include <net.h>

namespace {

constexpr const char* kTag = "LocalYoloeNative";
constexpr int kInputSize = 640;
constexpr int kClassCount = 4585;
constexpr int kBoxValues = 4;
constexpr int kMaskCoeffCount = 32;

struct Detection {
    int class_id;
    float confidence;
    float x0;
    float y0;
    float x1;
    float y1;
};

struct DetectorHandle {
    ncnn::Net net;
};

float intersectionOverUnion(const Detection& a, const Detection& b) {
    const float inter_x0 = std::max(a.x0, b.x0);
    const float inter_y0 = std::max(a.y0, b.y0);
    const float inter_x1 = std::min(a.x1, b.x1);
    const float inter_y1 = std::min(a.y1, b.y1);
    const float inter_w = std::max(0.0f, inter_x1 - inter_x0);
    const float inter_h = std::max(0.0f, inter_y1 - inter_y0);
    const float inter_area = inter_w * inter_h;
    const float area_a = std::max(0.0f, a.x1 - a.x0) * std::max(0.0f, a.y1 - a.y0);
    const float area_b = std::max(0.0f, b.x1 - b.x0) * std::max(0.0f, b.y1 - b.y0);
    const float denom = area_a + area_b - inter_area;
    if (denom <= 0.0f) return 0.0f;
    return inter_area / denom;
}

void applyNms(std::vector<Detection>& detections, float iou_threshold, int max_detections) {
    std::sort(detections.begin(), detections.end(), [](const Detection& a, const Detection& b) {
        return a.confidence > b.confidence;
    });

    std::vector<Detection> kept;
    kept.reserve(std::min<int>(max_detections, detections.size()));
    for (const Detection& detection : detections) {
        bool suppressed = false;
        for (const Detection& prior : kept) {
            if (detection.class_id == prior.class_id && intersectionOverUnion(detection, prior) > iou_threshold) {
                suppressed = true;
                break;
            }
        }
        if (!suppressed) {
            kept.push_back(detection);
            if (static_cast<int>(kept.size()) >= max_detections) break;
        }
    }
    detections.swap(kept);
}

float outputAt(const ncnn::Mat& output, int row, int anchor) {
    if (output.dims == 2) {
        if (output.w == 8400) return output.row(row)[anchor];
        return output.row(anchor)[row];
    }
    if (output.dims == 3) {
        if (output.w == 8400) return output.channel(0).row(row)[anchor];
        return output.channel(0).row(anchor)[row];
    }
    return 0.0f;
}

int outputAnchorCount(const ncnn::Mat& output) {
    if (output.dims == 2) return output.w == 8400 ? output.w : output.h;
    if (output.dims == 3) return output.w == 8400 ? output.w : output.h;
    return 0;
}

int outputValueCount(const ncnn::Mat& output) {
    if (output.dims == 2) return output.w == 8400 ? output.h : output.w;
    if (output.dims == 3) return output.w == 8400 ? output.h : output.w;
    return 0;
}

std::vector<Detection> parseDetections(
    const ncnn::Mat& output,
    float confidence_threshold,
    float iou_threshold,
    int max_detections
) {
    const int anchors = outputAnchorCount(output);
    const int values = outputValueCount(output);
    const int class_count = std::min(kClassCount, std::max(0, values - kBoxValues - kMaskCoeffCount));
    std::vector<Detection> detections;

    if (anchors <= 0 || class_count <= 0) {
        __android_log_print(ANDROID_LOG_ERROR, kTag, "Unexpected out0 shape dims=%d w=%d h=%d c=%d", output.dims, output.w, output.h, output.c);
        return detections;
    }

    for (int anchor = 0; anchor < anchors; ++anchor) {
        int best_class = -1;
        float best_confidence = confidence_threshold;
        for (int class_id = 0; class_id < class_count; ++class_id) {
            const float score = outputAt(output, kBoxValues + class_id, anchor);
            if (score > best_confidence) {
                best_confidence = score;
                best_class = class_id;
            }
        }

        if (best_class < 0) continue;

        const float cx = outputAt(output, 0, anchor);
        const float cy = outputAt(output, 1, anchor);
        const float w = outputAt(output, 2, anchor);
        const float h = outputAt(output, 3, anchor);
        Detection detection{
            best_class,
            best_confidence,
            std::clamp(cx - w * 0.5f, 0.0f, static_cast<float>(kInputSize)),
            std::clamp(cy - h * 0.5f, 0.0f, static_cast<float>(kInputSize)),
            std::clamp(cx + w * 0.5f, 0.0f, static_cast<float>(kInputSize)),
            std::clamp(cy + h * 0.5f, 0.0f, static_cast<float>(kInputSize)),
        };
        if (detection.x1 > detection.x0 && detection.y1 > detection.y0) detections.push_back(detection);
    }

    applyNms(detections, iou_threshold, max_detections);
    return detections;
}

std::string jStringToString(JNIEnv* env, jstring value) {
    const char* chars = env->GetStringUTFChars(value, nullptr);
    std::string output(chars == nullptr ? "" : chars);
    if (chars != nullptr) env->ReleaseStringUTFChars(value, chars);
    return output;
}

}  // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_com_friend_ios_LocalYoloePlugin_nativeLoad(JNIEnv* env, jobject /* thiz */, jstring param_path, jstring bin_path) {
    auto handle = std::make_unique<DetectorHandle>();
    handle->net.opt.use_vulkan_compute = false;
    handle->net.opt.num_threads = 2;
    handle->net.opt.use_packing_layout = true;

    const std::string param = jStringToString(env, param_path);
    const std::string bin = jStringToString(env, bin_path);

    if (handle->net.load_param(param.c_str()) != 0) {
        __android_log_print(ANDROID_LOG_ERROR, kTag, "Failed to load param: %s", param.c_str());
        return 0;
    }
    if (handle->net.load_model(bin.c_str()) != 0) {
        __android_log_print(ANDROID_LOG_ERROR, kTag, "Failed to load model: %s", bin.c_str());
        return 0;
    }

    return reinterpret_cast<jlong>(handle.release());
}

extern "C" JNIEXPORT jfloatArray JNICALL
Java_com_friend_ios_LocalYoloePlugin_nativeDetect(
    JNIEnv* env,
    jobject /* thiz */,
    jlong native_handle,
    jintArray argb_pixels,
    jint width,
    jint height,
    jfloat confidence_threshold,
    jfloat iou_threshold,
    jint max_detections
) {
    auto* handle = reinterpret_cast<DetectorHandle*>(native_handle);
    if (handle == nullptr || width <= 0 || height <= 0 || argb_pixels == nullptr) {
        return env->NewFloatArray(0);
    }

    std::vector<jint> pixels(static_cast<size_t>(width) * static_cast<size_t>(height));
    env->GetIntArrayRegion(argb_pixels, 0, static_cast<jsize>(pixels.size()), pixels.data());

    std::vector<unsigned char> rgb(pixels.size() * 3);
    for (size_t i = 0; i < pixels.size(); ++i) {
        const uint32_t pixel = static_cast<uint32_t>(pixels[i]);
        rgb[i * 3] = static_cast<unsigned char>((pixel >> 16) & 0xff);
        rgb[i * 3 + 1] = static_cast<unsigned char>((pixel >> 8) & 0xff);
        rgb[i * 3 + 2] = static_cast<unsigned char>(pixel & 0xff);
    }

    ncnn::Mat input = ncnn::Mat::from_pixels(rgb.data(), ncnn::Mat::PIXEL_RGB, width, height);
    const float norm[3] = {1.0f / 255.0f, 1.0f / 255.0f, 1.0f / 255.0f};
    input.substract_mean_normalize(nullptr, norm);

    ncnn::Extractor extractor = handle->net.create_extractor();
    if (extractor.input("in0", input) != 0) {
        __android_log_print(ANDROID_LOG_ERROR, kTag, "Failed to set input blob in0");
        return env->NewFloatArray(0);
    }

    ncnn::Mat output;
    if (extractor.extract("out0", output) != 0) {
        __android_log_print(ANDROID_LOG_ERROR, kTag, "Failed to extract output blob out0");
        return env->NewFloatArray(0);
    }

    std::vector<Detection> detections = parseDetections(output, confidence_threshold, iou_threshold, max_detections);
    std::vector<float> flat;
    flat.reserve(detections.size() * 6);
    for (const Detection& detection : detections) {
        flat.push_back(static_cast<float>(detection.class_id));
        flat.push_back(detection.confidence);
        flat.push_back(detection.x0);
        flat.push_back(detection.y0);
        flat.push_back(detection.x1);
        flat.push_back(detection.y1);
    }

    jfloatArray result = env->NewFloatArray(static_cast<jsize>(flat.size()));
    if (!flat.empty()) env->SetFloatArrayRegion(result, 0, static_cast<jsize>(flat.size()), flat.data());
    return result;
}

extern "C" JNIEXPORT void JNICALL
Java_com_friend_ios_LocalYoloePlugin_nativeClose(JNIEnv* /* env */, jobject /* thiz */, jlong native_handle) {
    auto* handle = reinterpret_cast<DetectorHandle*>(native_handle);
    delete handle;
}