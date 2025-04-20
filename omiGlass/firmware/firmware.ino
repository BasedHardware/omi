#define CAMERA_MODEL_XIAO_ESP32S3
#include <Arduino.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>
#include "esp_camera.h"
#include "camera_pins.h"

// ---------------------------------------------------------------------------------
// BLE
// ---------------------------------------------------------------------------------

// Device Information Service
#define DEVICE_INFORMATION_SERVICE_UUID (uint16_t)0x180A
#define MANUFACTURER_NAME_STRING_CHAR_UUID (uint16_t)0x2A29
#define MODEL_NUMBER_STRING_CHAR_UUID (uint16_t)0x2A24
#define FIRMWARE_REVISION_STRING_CHAR_UUID (uint16_t)0x2A26
#define HARDWARE_REVISION_STRING_CHAR_UUID (uint16_t)0x2A27

// Main Friend Service
static BLEUUID serviceUUID("19B10000-E8F2-537E-4F6C-D104768A1214");
static BLEUUID photoDataUUID("19B10005-E8F2-537E-4F6C-D104768A1214");
static BLEUUID photoControlUUID("19B10006-E8F2-537E-4F6C-D104768A1214");

// Characteristics
BLECharacteristic *photoDataCharacteristic;
BLECharacteristic *photoControlCharacteristic;

// State
bool connected = false;
bool isCapturingPhotos = false;
int captureInterval = 0;         // Interval in ms
unsigned long lastCaptureTime = 0;

size_t sent_photo_bytes = 0;
size_t sent_photo_frames = 0;
bool photoDataUploading = false;

// -------------------------------------------------------------------------
// Camera Frame
// -------------------------------------------------------------------------
camera_fb_t *fb = nullptr;

// Forward declaration
void handlePhotoControl(int8_t controlValue);

class ServerHandler : public BLEServerCallbacks {
  void onConnect(BLEServer *server) override {
    connected = true;
    Serial.println(">>> BLE Client connected.");
  }
  void onDisconnect(BLEServer *server) override {
    connected = false;
    Serial.println("<<< BLE Client disconnected. Restarting advertising.");
    BLEDevice::startAdvertising();
  }
};

class PhotoControlCallback : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    if (characteristic->getLength() == 1) {
      int8_t received = characteristic->getData()[0];
      Serial.print("PhotoControl received: ");
      Serial.println(received);
      handlePhotoControl(received);
    }
  }
};

// -------------------------------------------------------------------------
// configure_ble()
// -------------------------------------------------------------------------
void configure_ble() {
  Serial.println("Initializing BLE...");
  BLEDevice::init("OpenGlass");
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ServerHandler());

  // Main service
  BLEService *service = server->createService(serviceUUID);

  // Photo Data characteristic
  photoDataCharacteristic = service->createCharacteristic(
      photoDataUUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  BLE2902 *ccc = new BLE2902();
  ccc->setNotifications(true);
  photoDataCharacteristic->addDescriptor(ccc);

  // Photo Control characteristic
  photoControlCharacteristic = service->createCharacteristic(
      photoControlUUID,
      BLECharacteristic::PROPERTY_WRITE);
  photoControlCharacteristic->setCallbacks(new PhotoControlCallback());
  uint8_t controlValue = 0;
  photoControlCharacteristic->setValue(&controlValue, 1);

  // Device Information Service
  BLEService *deviceInfoService = server->createService(DEVICE_INFORMATION_SERVICE_UUID);
  BLECharacteristic *manufacturerNameCharacteristic =
      deviceInfoService->createCharacteristic(MANUFACTURER_NAME_STRING_CHAR_UUID,
                                              BLECharacteristic::PROPERTY_READ);
  BLECharacteristic *modelNumberCharacteristic =
      deviceInfoService->createCharacteristic(MODEL_NUMBER_STRING_CHAR_UUID,
                                              BLECharacteristic::PROPERTY_READ);
  BLECharacteristic *firmwareRevisionCharacteristic =
      deviceInfoService->createCharacteristic(FIRMWARE_REVISION_STRING_CHAR_UUID,
                                              BLECharacteristic::PROPERTY_READ);
  BLECharacteristic *hardwareRevisionCharacteristic =
      deviceInfoService->createCharacteristic(HARDWARE_REVISION_STRING_CHAR_UUID,
                                              BLECharacteristic::PROPERTY_READ);

  manufacturerNameCharacteristic->setValue("Based Hardware");
  modelNumberCharacteristic->setValue("OpenGlass");
  firmwareRevisionCharacteristic->setValue("1.0.1");
  hardwareRevisionCharacteristic->setValue("Seeed Xiao ESP32S3 Sense");

  // Start services
  service->start();
  deviceInfoService->start();

  // Start advertising
  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(deviceInfoService->getUUID());
  advertising->addServiceUUID(service->getUUID());
  advertising->setScanResponse(true);
  advertising->setMinPreferred(0x06);
  advertising->setMaxPreferred(0x12);
  BLEDevice::startAdvertising();

  Serial.println("BLE initialized and advertising started.");
}

// -------------------------------------------------------------------------
// Camera
// -------------------------------------------------------------------------
bool take_photo() {
  // Release previous buffer
  if (fb) {
    Serial.println("Releasing previous camera buffer...");
    esp_camera_fb_return(fb);
    fb = nullptr;
  }

  Serial.println("Capturing photo...");
  fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Failed to get camera frame buffer!");
    return false;
  }
  Serial.print("Photo captured: ");
  Serial.print(fb->len);
  Serial.println(" bytes.");
  return true;
}

void handlePhotoControl(int8_t controlValue) {
  if (controlValue == -1) {
    Serial.println("Received command: Single photo.");
    isCapturingPhotos = true;
    captureInterval = 0;
  }
  else if (controlValue == 0) {
    Serial.println("Received command: Stop photo capture.");
    isCapturingPhotos = false;
    captureInterval = 0;
  }
  else if (controlValue >= 5 && controlValue <= 300) {
    Serial.print("Received command: Start interval capture with parameter ");
    Serial.println(controlValue);

    // ---------------------------
    // Hard-code 30s interval here
    // ---------------------------
    captureInterval = 30000;  // 30 seconds

    isCapturingPhotos = true;
    lastCaptureTime = millis() - captureInterval;
  }
}

// -------------------------------------------------------------------------
// configure_camera()
// -------------------------------------------------------------------------
void configure_camera() {
  Serial.println("Initializing camera...");
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;

  // Example: 800x600, JPEG
  config.frame_size   = FRAMESIZE_SVGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.fb_count     = 1;
  config.jpeg_quality = 10;
  config.fb_location  = CAMERA_FB_IN_PSRAM;
  config.grab_mode    = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
  }
  else {
    Serial.println("Camera initialized successfully.");
  }
}

// -------------------------------------------------------------------------
// Setup & Loop
// -------------------------------------------------------------------------

// A small buffer for sending photo chunks over BLE
static uint8_t *s_compressed_frame_2 = nullptr;

void setup() {
  Serial.begin(921600);
  Serial.println("Setup started...");

  configure_ble();
  configure_camera();

  // Allocate buffer for photo chunks (200 bytes + 2 for frame index)
  s_compressed_frame_2 = (uint8_t *)ps_calloc(202, sizeof(uint8_t));
  if (!s_compressed_frame_2) {
    Serial.println("Failed to allocate chunk buffer!");
  } else {
    Serial.println("Chunk buffer allocated successfully.");
  }

  // Force a 30s default capture interval
  isCapturingPhotos = true;
  captureInterval = 30000; // 30 seconds
  lastCaptureTime = millis() - captureInterval;
  Serial.println("Default capture interval set to 30 seconds.");
}

void loop() {
  unsigned long now = millis();

  // Check if it's time to capture a photo
  if (isCapturingPhotos && !photoDataUploading && connected) {
    if ((captureInterval == 0) || (now - lastCaptureTime >= (unsigned long)captureInterval)) {
      if (captureInterval == 0) {
        // Single shot if interval=0
        isCapturingPhotos = false;
      }
      Serial.println("Interval reached. Capturing photo...");
      if (take_photo()) {
        Serial.println("Photo capture successful. Starting upload...");
        photoDataUploading = true;
        sent_photo_bytes = 0;
        sent_photo_frames = 0;
        lastCaptureTime = now;
      }
    }
  }

  // If uploading, send chunks over BLE
  if (photoDataUploading && fb) {
    size_t remaining = fb->len - sent_photo_bytes;
    if (remaining > 0) {
      // Prepare chunk
      s_compressed_frame_2[0] = (uint8_t)(sent_photo_frames & 0xFF);
      s_compressed_frame_2[1] = (uint8_t)((sent_photo_frames >> 8) & 0xFF);
      size_t bytes_to_copy = (remaining > 200) ? 200 : remaining;
      memcpy(&s_compressed_frame_2[2], &fb->buf[sent_photo_bytes], bytes_to_copy);

      photoDataCharacteristic->setValue(s_compressed_frame_2, bytes_to_copy + 2);
      photoDataCharacteristic->notify();

      sent_photo_bytes += bytes_to_copy;
      sent_photo_frames++;

      Serial.print("Uploading chunk ");
      Serial.print(sent_photo_frames);
      Serial.print(" (");
      Serial.print(bytes_to_copy);
      Serial.print(" bytes), ");
      Serial.print(remaining - bytes_to_copy);
      Serial.println(" bytes remaining.");
    }
    else {
      // End of photo marker
      s_compressed_frame_2[0] = 0xFF;
      s_compressed_frame_2[1] = 0xFF;
      photoDataCharacteristic->setValue(s_compressed_frame_2, 2);
      photoDataCharacteristic->notify();
      Serial.println("Photo upload complete.");

      photoDataUploading = false;
      // Free camera buffer
      esp_camera_fb_return(fb);
      fb = nullptr;
      Serial.println("Camera frame buffer freed.");
    }
  }

  delay(20);
}
