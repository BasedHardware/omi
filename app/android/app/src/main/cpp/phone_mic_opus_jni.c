/*
 * JNI shim bridging Kotlin `PhoneMicOpusEncoder` to libopus for batch
 * (transcribe-later) phone-mic capture. It exposes exactly three static natives —
 * create / encode-one-frame / destroy — and never calls back into Java (no
 * FindClass/GetMethodID), so the default ProGuard keep rule for JNI is enough.
 *
 * Why we hand-declare the opus prototypes instead of including its headers:
 * libopus.so already ships in the APK via the opus_flutter_android plugin (soname
 * `libopus.so`, all four ABIs, full C API exported), but its headers live only in
 * the plugin's pub-cache checkout and are not referenceable from an app/android
 * build. opus has a stable C ABI, so we pin the four entry points we call here and
 * resolve them at runtime with dlopen("libopus.so")/dlsym rather than vendoring
 * headers or the source. The two `#define`s below are the two opus_defines.h
 * values we need, copied for the same reason.
 */

#include <android/log.h>
#include <dlfcn.h>
#include <jni.h>
#include <pthread.h>
#include <stdint.h>

#define LOG_TAG "PhoneMicOpus"
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// opus_defines.h values (headers not referenceable from a repo build; ABI is stable).
#define OPUS_APPLICATION_VOIP 2048
#define OPUS_SET_BITRATE_REQUEST 4002

// Frame geometry, mirrored from the Kotlin/iOS encoder: 320 samples * 2 bytes =
// 640 bytes of PCM16 mono per 20 ms frame; 4000 is opus's recommended safe packet
// ceiling and never truncates a 32 kbit/s VOIP packet.
#define FRAME_SAMPLES 320
#define FRAME_BYTES 640
#define MAX_PACKET_BYTES 4000

// Hand-declared opus prototypes (stable C ABI). opus_encoder_ctl is variadic; for
// OPUS_SET_BITRATE its single trailing argument is an opus_int32 (int32_t).
typedef void *(*opus_encoder_create_fn)(int32_t sample_rate, int channels, int application, int *error);
typedef int (*opus_encode_fn)(void *st, const int16_t *pcm, int frame_size, uint8_t *data, int32_t max_data_bytes);
typedef int (*opus_encoder_ctl_fn)(void *st, int request, ...);
typedef void (*opus_encoder_destroy_fn)(void *st);

static opus_encoder_create_fn p_opus_encoder_create = NULL;
static opus_encode_fn p_opus_encode = NULL;
static opus_encoder_ctl_fn p_opus_encoder_ctl = NULL;
static opus_encoder_destroy_fn p_opus_encoder_destroy = NULL;

static pthread_once_t g_opus_once = PTHREAD_ONCE_INIT;
static int g_opus_ready = 0;

/*
 * Resolve the four opus entry points once. Kotlin has already
 * System.loadLibrary("opus")'d before the first nativeCreate, so dlopen by soname
 * returns a handle to the already-mapped library — we never try an absolute path
 * (nativeLibraryDir is empty under AGP's non-extracted native-libs default).
 * Encoder creation only ever happens on the controller's single audio executor, but
 * pthread_once guards the resolve so correctness never silently depends on that.
 */
static void opus_resolve(void)
{
    void *lib = dlopen("libopus.so", RTLD_NOW);
    if (lib == NULL) {
        LOGE("dlopen(libopus.so) failed: %s", dlerror());
        return;
    }
    p_opus_encoder_create = (opus_encoder_create_fn) dlsym(lib, "opus_encoder_create");
    p_opus_encode = (opus_encode_fn) dlsym(lib, "opus_encode");
    p_opus_encoder_ctl = (opus_encoder_ctl_fn) dlsym(lib, "opus_encoder_ctl");
    p_opus_encoder_destroy = (opus_encoder_destroy_fn) dlsym(lib, "opus_encoder_destroy");
    if (p_opus_encoder_create == NULL || p_opus_encode == NULL || p_opus_encoder_ctl == NULL ||
        p_opus_encoder_destroy == NULL) {
        LOGE("dlsym failed (create=%p encode=%p ctl=%p destroy=%p)",
             (void *) p_opus_encoder_create,
             (void *) p_opus_encode,
             (void *) p_opus_encoder_ctl,
             (void *) p_opus_encoder_destroy);
        return;
    }
    g_opus_ready = 1;
}

// jlong opaque encoder handle, or 0 on ANY failure (dlopen/dlsym/create/ctl).
JNIEXPORT jlong JNICALL Java_com_friend_ios_phonemic_PhoneMicOpusEncoder_nativeCreate(JNIEnv *env,
                                                                                      jclass clazz,
                                                                                      jint sampleRate,
                                                                                      jint channels,
                                                                                      jint application,
                                                                                      jint bitrate)
{
    (void) env;
    (void) clazz;
    pthread_once(&g_opus_once, opus_resolve);
    if (!g_opus_ready) {
        return 0;
    }
    int err = 0;
    void *enc = p_opus_encoder_create((int32_t) sampleRate, (int) channels, (int) application, &err);
    if (enc == NULL || err != 0) {
        LOGE("opus_encoder_create failed (err=%d)", err);
        return 0;
    }
    int ctl = p_opus_encoder_ctl(enc, OPUS_SET_BITRATE_REQUEST, (int32_t) bitrate);
    if (ctl != 0) {
        LOGE("opus_encoder_ctl(SET_BITRATE) failed (err=%d)", ctl);
        p_opus_encoder_destroy(enc);
        return 0;
    }
    return (jlong) (intptr_t) enc;
}

// Encode one whole frame (exactly 640 bytes PCM16 mono) into a fresh jbyteArray;
// NULL on a null/zero handle, wrong-size input, encode error, or OOM.
JNIEXPORT jbyteArray JNICALL Java_com_friend_ios_phonemic_PhoneMicOpusEncoder_nativeEncodeFrame(JNIEnv *env,
                                                                                                jclass clazz,
                                                                                                jlong handle,
                                                                                                jbyteArray pcm)
{
    (void) clazz;
    if (handle == 0 || pcm == NULL) {
        return NULL;
    }
    jsize len = (*env)->GetArrayLength(env, pcm);
    if (len != FRAME_BYTES) {
        LOGE("nativeEncodeFrame expected %d bytes, got %d", FRAME_BYTES, (int) len);
        return NULL;
    }
    // Android target ABIs are all little-endian, so the PCM16LE bytes map directly
    // onto int16_t samples (same as the iOS encoder binding Data to Int16).
    int16_t frame[FRAME_SAMPLES];
    (*env)->GetByteArrayRegion(env, pcm, 0, FRAME_BYTES, (jbyte *) frame);
    uint8_t out[MAX_PACKET_BYTES];
    int written = p_opus_encode((void *) (intptr_t) handle, frame, FRAME_SAMPLES, out, MAX_PACKET_BYTES);
    if (written <= 0) {
        LOGE("opus_encode failed (ret=%d)", written);
        return NULL;
    }
    jbyteArray packet = (*env)->NewByteArray(env, written);
    if (packet == NULL) {
        return NULL; // OOM — a pending OutOfMemoryError is already set
    }
    (*env)->SetByteArrayRegion(env, packet, 0, written, (const jbyte *) out);
    return packet;
}

// Destroy the encoder. Zero-guarded so a double destroy from Kotlin is a no-op.
JNIEXPORT void JNICALL Java_com_friend_ios_phonemic_PhoneMicOpusEncoder_nativeDestroy(JNIEnv *env,
                                                                                      jclass clazz,
                                                                                      jlong handle)
{
    (void) env;
    (void) clazz;
    if (handle == 0) {
        return;
    }
    p_opus_encoder_destroy((void *) (intptr_t) handle);
}
