#define CAMERA_MODEL_XIAO_ESP32S3
#include <I2S.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>
#include "esp_camera.h"
#include "camera_pins.h"
#include "mulaw.h"

// Audio

// Uncomment to switch the codec
// Opus is still under development
// Mulaw is used with the web app
// PCM is used with the Friend app

// To use with the web app, comment CODEC_PCM and
// uncomment CODEC_MULAW

// #define CODEC_OPUS
// #define CODEC_MULAW
#define CODEC_PCM

#ifdef CODEC_OPUS

#include <opus.h>

#define OPUS_APPLICATION OPUS_APPLICATION_VOIP
#define OPUS_BITRATE 16000

OpusEncoder *opus_encoder = nullptr;

#define CHANNELS 1
#define MAX_PACKET_SIZE 1000

#define SAMPLE_RATE 16000
#define SAMPLE_BITS 16

#else
#ifdef CODEC_MULAW

#define SAMPLE_RATE 8000
#define SAMPLE_BITS 16

#else

#define FRAME_SIZE 160
#define SAMPLE_RATE 16000
#define SAMPLE_BITS 16

#endif
#endif

//
// BLE
//

// Device Information Service
#define DEVICE_INFORMATION_SERVICE_UUID (uint16_t)0x180A
#define MANUFACTURER_NAME_STRING_CHAR_UUID (uint16_t)0x2A29
#define MODEL_NUMBER_STRING_CHAR_UUID (uint16_t)0x2A24
#define FIRMWARE_REVISION_STRING_CHAR_UUID (uint16_t)0x2A26
#define HARDWARE_REVISION_STRING_CHAR_UUID (uint16_t)0x2A27

// Battery Level Service
#define BATTERY_SERVICE_UUID (uint16_t)0x180F
#define BATTERY_LEVEL_CHAR_UUID (uint16_t)0x2A19

// Main Friend Service
static BLEUUID serviceUUID("19B10000-E8F2-537E-4F6C-D104768A1214");
static BLEUUID audioDataUUID("19B10001-E8F2-537E-4F6C-D104768A1214");
static BLEUUID audioCodecUUID("19B10002-E8F2-537E-4F6C-D104768A1214");
static BLEUUID photoDataUUID("19B10005-E8F2-537E-4F6C-D104768A1214");
static BLEUUID photoControlUUID("19B10006-E8F2-537E-4F6C-D104768A1214");

BLECharacteristic *audioDataCharacteristic;
BLECharacteristic *photoDataCharacteristic;
BLECharacteristic *photoControlCharacteristic;

BLECharacteristic *batteryLevelCharacteristic;

// State

bool connected = false;

uint16_t audio_frame_count = 0;

bool isCapturingPhotos = false;
int captureInterval = 0;
unsigned long lastCaptureTime = 0;

size_t sent_photo_bytes = 0;
size_t sent_photo_frames = 0;
bool photoDataUploading = false;

uint8_t batteryLevel = 100;
unsigned long lastBatteryUpdate = 0;

void handlePhotoControl(int8_t controlValue);

class ServerHandler : public BLEServerCallbacks
{
  void onConnect(BLEServer *server)
  {
    connected = true;
  }

  void onDisconnect(BLEServer *server)
  {
    connected = false;
    BLEDevice::startAdvertising();
  }
};

class PhotoControlCallback : public BLECharacteristicCallbacks
{
  void onWrite(BLECharacteristic *characteristic)
  {
    if (characteristic->getLength() == 1)
    {
      handlePhotoControl(characteristic->getData()[0]);
    }
  }
};

void configure_ble() {
  BLEDevice::init("OpenGlass");
  BLEServer *server = BLEDevice::createServer();

  // Main service

  BLEService *service = server->createService(serviceUUID);

  // Audio characteristics
  audioDataCharacteristic = service->createCharacteristic(
    audioDataUUID,
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
  );
  BLE2902 *ccc = new BLE2902();
  ccc->setNotifications(true);
  audioDataCharacteristic->addDescriptor(ccc);

  BLECharacteristic *audioCodecCharacteristic = service->createCharacteristic(
    audioCodecUUID,
    BLECharacteristic::PROPERTY_READ);
#ifdef CODEC_OPUS
  uint8_t codecId = 20; // Opus 16khz
#else
#ifdef CODEC_MULAW
  uint8_t codecId = 11; // MuLaw 8khz
#else
  uint8_t codecId = 1; // PCM 8khz
#endif
#endif
  audioCodecCharacteristic->setValue(&codecId, 1);

  // Photo characteristics

  photoDataCharacteristic = service->createCharacteristic(
      photoDataUUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  ccc = new BLE2902();
  ccc->setNotifications(true);
  photoDataCharacteristic->addDescriptor(ccc);

  BLECharacteristic *photoControlCharacteristic = service->createCharacteristic(
      photoControlUUID,
      BLECharacteristic::PROPERTY_WRITE);
  photoControlCharacteristic->setCallbacks(new PhotoControlCallback());
  uint8_t controlValue = 0;
  photoControlCharacteristic->setValue(&controlValue, 1);

  // Device Information Service

  BLEService *deviceInfoService = server->createService(BLEUUID(DEVICE_INFORMATION_SERVICE_UUID));
  BLECharacteristic *manufacturerNameCharacteristic = deviceInfoService->createCharacteristic(
      BLEUUID(MANUFACTURER_NAME_STRING_CHAR_UUID),
      BLECharacteristic::PROPERTY_READ);
  BLECharacteristic *modelNumberCharacteristic = deviceInfoService->createCharacteristic(
      BLEUUID(MODEL_NUMBER_STRING_CHAR_UUID),
      BLECharacteristic::PROPERTY_READ);
  BLECharacteristic *firmwareRevisionCharacteristic = deviceInfoService->createCharacteristic(
      BLEUUID(FIRMWARE_REVISION_STRING_CHAR_UUID),
      BLECharacteristic::PROPERTY_READ);
  BLECharacteristic *hardwareRevisionCharacteristic = deviceInfoService->createCharacteristic(
      BLEUUID(HARDWARE_REVISION_STRING_CHAR_UUID),
      BLECharacteristic::PROPERTY_READ);

  manufacturerNameCharacteristic->setValue("Based Hardware");
  modelNumberCharacteristic->setValue("OpenGlass");
  firmwareRevisionCharacteristic->setValue("1.0.1");
  hardwareRevisionCharacteristic->setValue("Seeed Xiao ESP32S3 Sense");

  // Battery Service
  BLEService *batteryService = server->createService(BLEUUID(BATTERY_SERVICE_UUID));
  batteryLevelCharacteristic = batteryService->createCharacteristic(
      BLEUUID(BATTERY_LEVEL_CHAR_UUID),
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  ccc = new BLE2902();
  ccc->setNotifications(true);
  batteryLevelCharacteristic->addDescriptor(ccc);
  batteryLevelCharacteristic->setValue(&batteryLevel, 1);

  // Start the services
  service->start();
  deviceInfoService->start();
  batteryService->start();

  server->setCallbacks(new ServerHandler());

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(BLEUUID(BATTERY_SERVICE_UUID));
  advertising->addServiceUUID(BLEUUID(DEVICE_INFORMATION_SERVICE_UUID));
  advertising->addServiceUUID(service->getUUID());
  advertising->setScanResponse(true);
  advertising->setMinPreferred(0x06);
  advertising->setMaxPreferred(0x12);
  BLEDevice::startAdvertising();
}

camera_fb_t *fb;

bool take_photo() {
  // Release buffer
  if (fb) {
    esp_camera_fb_return(fb);
  }

  // Take a photo
  fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Failed to get camera frame buffer");
    return false;
  }

  return true;
}

void handlePhotoControl(int8_t controlValue)
{
  if (controlValue == -1)
  {
    // Take a single photo
    isCapturingPhotos = true;
    captureInterval = 0;
  }
  else if (controlValue == 0)
  {
    // Stop taking photos
    isCapturingPhotos = false;
    captureInterval = 0;
  }
  else if (controlValue >= 5 && controlValue <= 300)
  {
    // Start taking photos at specified interval
    captureInterval = (controlValue / 5) * 5000; // Round to nearest 5 seconds and convert to milliseconds
    isCapturingPhotos = true;
    lastCaptureTime = millis() - captureInterval;
  }
}

//
// Microphone
//

#ifdef CODEC_OPUS

static size_t recording_buffer_size = FRAME_SIZE * 2; // 16-bit samples
static size_t compressed_buffer_size = MAX_PACKET_SIZE;
#define VOLUME_GAIN 2

#else
#ifdef CODEC_MULAW

static size_t recording_buffer_size = 400;
static size_t compressed_buffer_size = 400 + 3; /* header */
#define VOLUME_GAIN 2

#else

static size_t recording_buffer_size = FRAME_SIZE * 2; // 16-bit samples
static size_t compressed_buffer_size = recording_buffer_size + 3; /* header */
#define VOLUME_GAIN 2

#endif
#endif

static uint8_t *s_recording_buffer = nullptr;
static uint8_t *s_compressed_frame = nullptr;
static uint8_t *s_compressed_frame_2 = nullptr;

void configure_microphone() {

  // start I2S at 16 kHz with 16-bits per sample
  I2S.setAllPins(-1, 42, 41, -1, -1);
  if (!I2S.begin(PDM_MONO_MODE, SAMPLE_RATE, SAMPLE_BITS)) {
    Serial.println("Failed to initialize I2S!");
    while (1); // do nothing
  }

  // Allocate buffers
  s_recording_buffer = (uint8_t *) ps_calloc(recording_buffer_size, sizeof(uint8_t));
  s_compressed_frame = (uint8_t *) ps_calloc(compressed_buffer_size, sizeof(uint8_t));
  s_compressed_frame_2 = (uint8_t *) ps_calloc(compressed_buffer_size, sizeof(uint8_t));
}

size_t read_microphone() {
  size_t bytes_recorded = 0;
  esp_i2s::i2s_read(esp_i2s::I2S_NUM_0, s_recording_buffer, recording_buffer_size, &bytes_recorded, portMAX_DELAY);
  return bytes_recorded;
}

//
// Camera
//

void configure_camera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size = FRAMESIZE_UXGA;
  config.pixel_format = PIXFORMAT_JPEG; // for streaming
  config.fb_count = 1;

  // High quality (psram)
  // config.jpeg_quality = 10;
  // config.fb_count = 2;
  // config.grab_mode = CAMERA_GRAB_LATEST;

  // Low quality (and in local ram)
  config.jpeg_quality = 10;
  config.frame_size = FRAMESIZE_SVGA;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  // config.fb_location = CAMERA_FB_IN_DRAM;

  // camera init
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }
}

void updateBatteryLevel()
{
  // TODO:
  batteryLevelCharacteristic->setValue(&batteryLevel, 1);
  batteryLevelCharacteristic->notify();
}

//
// Main
//

// static uint8_t *s_compressed_frame_2 = nullptr;
// static size_t compressed_buffer_size = 400 + 3;
void setup() {
  Serial.begin(921600);
  // SD.begin(21);
  configure_ble();
  // s_compressed_frame_2 = (uint8_t *) ps_calloc(compressed_buffer_size, sizeof(uint8_t));
#ifdef CODEC_OPUS
  int opus_err;
  opus_encoder = opus_encoder_create(SAMPLE_RATE, CHANNELS, OPUS_APPLICATION, &opus_err);
  if (opus_err != OPUS_OK || !opus_encoder)
  {
    Serial.println("Failed to create Opus encoder!");
    while (1)
      ; // do nothing
  }
  opus_encoder_ctl(opus_encoder, OPUS_SET_BITRATE(OPUS_BITRATE));
#endif
  configure_microphone();
  configure_camera();
}

void loop() {
  // Read from mic
  size_t bytes_recorded = read_microphone();

  // Push audio to BLE
  if (bytes_recorded > 0 && connected)
  {
#ifdef CODEC_OPUS
    int16_t samples[FRAME_SIZE];
    for (size_t i = 0; i < bytes_recorded; i += 2)
    {
      samples[i / 2] = ((s_recording_buffer[i + 1] << 8) | s_recording_buffer[i]) << VOLUME_GAIN;
    }

    int encoded_bytes = opus_encode(opus_encoder, samples, FRAME_SIZE, &s_compressed_frame[3], MAX_PACKET_SIZE - 3);

    if (encoded_bytes > 0)
    {
#else
#ifdef CODEC_MULAW
    for (size_t i = 0; i < bytes_recorded; i += 2)
    {
      int16_t sample = ((s_recording_buffer[i + 1] << 8) | s_recording_buffer[i]) << VOLUME_GAIN;
      s_compressed_frame[i / 2 + 3] = linear2ulaw(sample);
    }

    int encoded_bytes = bytes_recorded / 2;
#else
    for (size_t i = 0; i < bytes_recorded / 4; i++)
    {
      int16_t sample = ((int16_t *)s_recording_buffer)[i * 2] << VOLUME_GAIN; // Read every other 16-bit sample
      s_compressed_frame[i * 2 + 3] = sample & 0xFF;           // Low byte
      s_compressed_frame[i * 2 + 4] = (sample >> 8) & 0xFF;    // High byte
    }

    int encoded_bytes = bytes_recorded / 2;
#endif
#endif

    s_compressed_frame[0] = audio_frame_count & 0xFF;
    s_compressed_frame[1] = (audio_frame_count >> 8) & 0xFF;
    s_compressed_frame[2] = 0;

    size_t out_buffer_size = encoded_bytes + 3;
    audioDataCharacteristic->setValue(s_compressed_frame, out_buffer_size);
    audioDataCharacteristic->notify();
    audio_frame_count++;
#ifdef CODEC_OPUS
    }
#endif
  }

  // Take a photo
  unsigned long now = millis();

  // Don't take a photo if we are already sending data for previous photo
  if (isCapturingPhotos && !photoDataUploading && connected)
  {
    if ((captureInterval == 0)
      || ((now - lastCaptureTime) >= captureInterval))
    {
      if (captureInterval == 0) {
        // Single photo requested
        isCapturingPhotos = false;
      }

      // Take the photo
      if (take_photo())
      {
        photoDataUploading = true;
        sent_photo_bytes = 0;
        sent_photo_frames = 0;
        lastCaptureTime = now;
      }
    }
  }

  // Push photo data to BLE
  if (photoDataUploading) {
    size_t remaining = fb->len - sent_photo_bytes;
    if (remaining > 0) {
      // Populate buffer
      s_compressed_frame_2[0] = sent_photo_frames & 0xFF;
      s_compressed_frame_2[1] = (sent_photo_frames >> 8) & 0xFF;
      size_t bytes_to_copy = remaining;
      if (bytes_to_copy > 200) {
        bytes_to_copy = 200;
      }
      memcpy(&s_compressed_frame_2[2], &fb->buf[sent_photo_bytes], bytes_to_copy);

      // Push to BLE
      photoDataCharacteristic->setValue(s_compressed_frame_2, bytes_to_copy + 2);
      photoDataCharacteristic->notify();
      sent_photo_bytes += bytes_to_copy;
      sent_photo_frames++;
    } else {
      // End flag
      s_compressed_frame_2[0] = 0xFF;
      s_compressed_frame_2[1] = 0xFF;
      photoDataCharacteristic->setValue(s_compressed_frame_2, 2);
      photoDataCharacteristic->notify();

      photoDataUploading = false;
    }
  }

  // Update battery level
  if (now - lastBatteryUpdate > 60000)
  {
    updateBatteryLevel();
    lastBatteryUpdate = millis();
  }

  // Delay
  delay(20);
}
