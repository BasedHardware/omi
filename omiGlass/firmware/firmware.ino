#include <Arduino.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>
#include "esp_camera.h"
#include "esp_sleep.h"
#include "config.h"  // Use config.h for all configurations

// Battery state
float batteryVoltage = 0.0f;
int batteryPercentage = 0;
unsigned long lastBatteryCheck = 0;

// Device power state
bool deviceActive = true;
device_state_t deviceState = DEVICE_BOOTING;

// Button and LED state
volatile bool buttonPressed = false;
unsigned long buttonPressTime = 0;
led_status_t ledMode = LED_BOOT_SEQUENCE;

// Gentle power optimization
unsigned long lastActivity = 0;
bool powerSaveMode = false;

// Light sleep optimization - saves ~15mA = adds 3-4 hours battery life
bool lightSleepEnabled = true;

// ---------------------------------------------------------------------------------
// BLE - Using config.h definitions
// ---------------------------------------------------------------------------------

// Device Information Service UUIDs  
#define DEVICE_INFORMATION_SERVICE_UUID (uint16_t)0x180A
#define MANUFACTURER_NAME_STRING_CHAR_UUID (uint16_t)0x2A29
#define MODEL_NUMBER_STRING_CHAR_UUID (uint16_t)0x2A24
#define FIRMWARE_REVISION_STRING_CHAR_UUID (uint16_t)0x2A26
#define HARDWARE_REVISION_STRING_CHAR_UUID (uint16_t)0x2A27

// Main Friend Service - using config.h UUIDs
static BLEUUID serviceUUID(OMI_SERVICE_UUID);
static BLEUUID photoDataUUID(PHOTO_DATA_UUID);
static BLEUUID photoControlUUID(PHOTO_CONTROL_UUID);

// Characteristics
BLECharacteristic *photoDataCharacteristic;
BLECharacteristic *photoControlCharacteristic;
BLECharacteristic *batteryLevelCharacteristic;

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

// Forward declarations
void handlePhotoControl(int8_t controlValue);
void readBatteryLevel();
void updateBatteryService();
void IRAM_ATTR buttonISR();
void handleButton();
void updateLED();
void blinkLED(int count, int delayMs);
void enterPowerSave();
void exitPowerSave();
void shutdownDevice();
void enableLightSleep();

// -------------------------------------------------------------------------
// Button ISR
// -------------------------------------------------------------------------
void IRAM_ATTR buttonISR() {
  buttonPressed = true;
}

// -------------------------------------------------------------------------
// LED Functions
// -------------------------------------------------------------------------
void updateLED() {
  unsigned long now = millis();
  static unsigned long bootStartTime = 0;
  static unsigned long powerOffStartTime = 0;
  
  switch (ledMode) {
    case LED_BOOT_SEQUENCE:
      if (bootStartTime == 0) bootStartTime = now;
      
      // 5 quick blinks over 1.5 seconds total (inverted logic: HIGH=OFF, LOW=ON)
      if (now - bootStartTime < 1500) {
        int blinkPhase = ((now - bootStartTime) / 150) % 2;
        digitalWrite(STATUS_LED_PIN, !blinkPhase);
      } else {
        digitalWrite(STATUS_LED_PIN, HIGH); // OFF
        ledMode = LED_NORMAL_OPERATION;
        bootStartTime = 0;
      }
      break;
      
    case LED_POWER_OFF_SEQUENCE:
      if (powerOffStartTime == 0) powerOffStartTime = now;
      
      // 2 quick blinks over 800ms total (inverted logic: HIGH=OFF, LOW=ON)
      if (now - powerOffStartTime < 800) {
        int blinkPhase = ((now - powerOffStartTime) / 200) % 2;
        digitalWrite(STATUS_LED_PIN, !blinkPhase);
      } else {
        digitalWrite(STATUS_LED_PIN, HIGH); // OFF
        delay(100);
        shutdownDevice();
      }
      break;
      
    case LED_NORMAL_OPERATION:
    default:
      digitalWrite(STATUS_LED_PIN, HIGH); // OFF
      break;
  }
}

void blinkLED(int count, int delayMs) {
  for (int i = 0; i < count; i++) {
    digitalWrite(STATUS_LED_PIN, HIGH);
    delay(delayMs);
    digitalWrite(STATUS_LED_PIN, LOW);
    delay(delayMs);
  }
}

// -------------------------------------------------------------------------
// Button Handling
// -------------------------------------------------------------------------
void handleButton() {
  if (!buttonPressed) return;
  
  unsigned long now = millis();
  static unsigned long lastButtonTime = 0;
  static bool buttonDown = false;
  
  bool currentButtonState = !digitalRead(POWER_BUTTON_PIN); // Active low (pressed = true)
  
  // Simple debouncing
  if (now - lastButtonTime < 50) {
    buttonPressed = false;
    return;
  }
  
  if (currentButtonState && !buttonDown) {
    // Button just pressed
    buttonPressTime = now;
    buttonDown = true;
    lastButtonTime = now;
    
  } else if (!currentButtonState && buttonDown) {
    // Button just released
    buttonDown = false;
    unsigned long pressDuration = now - buttonPressTime;
    lastButtonTime = now;
    
    if (pressDuration >= 2000) {
      // Long press - power off
      ledMode = LED_POWER_OFF_SEQUENCE;
    } else if (pressDuration >= 50) {
      // Short press - register activity
      lastActivity = now;
      if (powerSaveMode) {
        exitPowerSave();
      }
    }
  }
  
  buttonPressed = false;
}

// -------------------------------------------------------------------------
// Power Management
// -------------------------------------------------------------------------
void enterPowerSave() {
  if (!powerSaveMode) {
    setCpuFrequencyMhz(MIN_CPU_FREQ_MHZ); // 40MHz for idle
    powerSaveMode = true;
  }
}

void exitPowerSave() {
  if (powerSaveMode) {
    setCpuFrequencyMhz(NORMAL_CPU_FREQ_MHZ); // Back to 80MHz
    powerSaveMode = false;
  }
}

void enableLightSleep() {
  if (!lightSleepEnabled || !connected || photoDataUploading) {
    return; // Don't sleep if disabled, not connected, or uploading
  }
  
  unsigned long now = millis();
  
  // Don't sleep if there was recent activity (within 5 seconds)
  if (now - lastActivity < 5000) {
    return;
  }
  
  unsigned long timeUntilNextPhoto = 0;
  
  if (isCapturingPhotos && captureInterval > 0) {
    unsigned long timeSinceLastPhoto = now - lastCaptureTime;
    if (timeSinceLastPhoto < captureInterval) {
      timeUntilNextPhoto = captureInterval - timeSinceLastPhoto;
    }
  }
  
  // Only sleep if we have at least 10 seconds until next photo
  if (timeUntilNextPhoto > 10000) {
    // Configure light sleep to wake on BLE events and timer
    unsigned long sleepTime = timeUntilNextPhoto - 5000;
    if (sleepTime > 15000) sleepTime = 15000; // Max 15 seconds
    esp_sleep_enable_timer_wakeup(sleepTime * 1000); // Wake 5s before photo or max 15s
    esp_light_sleep_start();
    lastActivity = millis(); // Update activity time after wake
  }
}

void shutdownDevice() {
  Serial.println("Shutting down device...");
  
  // Stop photo capture
  isCapturingPhotos = false;
  
  // Disconnect BLE gracefully
  if (connected) {
    Serial.println("Disconnecting BLE...");
  }
  
  // Turn off LED (inverted logic)
  digitalWrite(STATUS_LED_PIN, HIGH);
  
  // Enter deep sleep
  esp_sleep_enable_ext0_wakeup(GPIO_NUM_1, 0); // Wake on button press
  Serial.println("Entering deep sleep...");
  delay(100);
  esp_deep_sleep_start();
}

class ServerHandler : public BLEServerCallbacks {
  void onConnect(BLEServer *server) override {
    connected = true;
    lastActivity = millis(); // Register activity - prevents sleep
    Serial.println(">>> BLE Client connected.");
    // Send current battery level on connect
    updateBatteryService();
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
      lastActivity = millis(); // Register activity - prevents sleep
      handlePhotoControl(received);
    }
  }
};

// -------------------------------------------------------------------------
// Battery Functions
// -------------------------------------------------------------------------
void readBatteryLevel() {
  // Take multiple ADC readings for stability
  int adcSum = 0;
  for (int i = 0; i < 10; i++) {
    adcSum += analogRead(BATTERY_ADC_PIN);
    delay(10);
  }
  int adcValue = adcSum / 10;
  
  // ESP32-S3 ADC: 12-bit (0-4095), reference voltage ~3.3V
  float adcVoltage = (adcValue / 4095.0f) * 3.3f;
  
  // Apply voltage divider ratio to get actual battery voltage
  batteryVoltage = adcVoltage * VOLTAGE_DIVIDER_RATIO;
  
  // Clamp voltage to reasonable range
  if (batteryVoltage > 5.0f) batteryVoltage = 5.0f;
  if (batteryVoltage < 2.5f) batteryVoltage = 2.5f;
  
  // Load-compensated battery calculation (accounts for voltage sag under load)
  // Real-world Li-Po behavior: 4.1V=100%, 3.5V=0% under load
  float loadCompensatedMax = 4.1f;  // Realistic max under load
  float loadCompensatedMin = 3.5f;  // Realistic min under load
  
  // More accurate percentage calculation for load conditions
  if (batteryVoltage >= loadCompensatedMax) {
    batteryPercentage = 100;
  } else if (batteryVoltage <= loadCompensatedMin) {
    batteryPercentage = 0;
  } else {
    float range = loadCompensatedMax - loadCompensatedMin;
    batteryPercentage = (int)(((batteryVoltage - loadCompensatedMin) / range) * 100.0f);
  }
  
  // Smooth percentage changes to avoid jumpy readings
  static int lastBatteryPercentage = batteryPercentage;
  if (abs(batteryPercentage - lastBatteryPercentage) > 5) {
    batteryPercentage = lastBatteryPercentage + (batteryPercentage > lastBatteryPercentage ? 2 : -2);
  }
  lastBatteryPercentage = batteryPercentage;
  
  // Clamp percentage
  if (batteryPercentage > 100) batteryPercentage = 100;
  if (batteryPercentage < 0) batteryPercentage = 0;
  
  // Battery status with load info
  Serial.print("Battery: ");
  Serial.print(batteryVoltage);
  Serial.print("V (");
  Serial.print(batteryPercentage);
  Serial.print("%) [Load-compensated: ");
  Serial.print(loadCompensatedMin);
  Serial.print("V-");
  Serial.print(loadCompensatedMax);
  Serial.println("V]");
}

void updateBatteryService() {
  if (batteryLevelCharacteristic) {
    uint8_t batteryLevel = (uint8_t)batteryPercentage;
    batteryLevelCharacteristic->setValue(&batteryLevel, 1);
    
    if (connected) {
      batteryLevelCharacteristic->notify();
    }
  }
}

// -------------------------------------------------------------------------
// configure_ble()
// -------------------------------------------------------------------------
void configure_ble() {
  Serial.println("Initializing BLE...");
  BLEDevice::init(BLE_DEVICE_NAME);
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

  // Battery Service
  BLEService *batteryService = server->createService(BATTERY_SERVICE_UUID);
  batteryLevelCharacteristic = batteryService->createCharacteristic(
      BATTERY_LEVEL_UUID,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  BLE2902 *batteryCcc = new BLE2902();
  batteryCcc->setNotifications(true);
  batteryLevelCharacteristic->addDescriptor(batteryCcc);
  
  // Set initial battery level
  readBatteryLevel();
  uint8_t initialBatteryLevel = (uint8_t)batteryPercentage;
  batteryLevelCharacteristic->setValue(&initialBatteryLevel, 1);

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

  manufacturerNameCharacteristic->setValue(MANUFACTURER_NAME);
  modelNumberCharacteristic->setValue(BLE_DEVICE_NAME);
  firmwareRevisionCharacteristic->setValue(FIRMWARE_VERSION_STRING);
  hardwareRevisionCharacteristic->setValue(HARDWARE_REVISION);

  // Start services
  service->start();
  batteryService->start();
  deviceInfoService->start();

  // Start advertising
  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(deviceInfoService->getUUID());
  advertising->addServiceUUID(service->getUUID());
  advertising->addServiceUUID(batteryService->getUUID());
  advertising->setScanResponse(true);
  advertising->setMinPreferred(BLE_ADV_MIN_INTERVAL);
  advertising->setMaxPreferred(BLE_ADV_MAX_INTERVAL);
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
  
  lastActivity = millis(); // Register activity
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

    // Use fixed interval from config for optimal battery life
    captureInterval = PHOTO_CAPTURE_INTERVAL_MS;
    Serial.print("Using configured interval: ");
    Serial.print(captureInterval / 1000);
    Serial.println(" seconds");

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
  config.xclk_freq_hz = CAMERA_XCLK_FREQ;

  // Use config.h camera settings optimized for battery life
  config.frame_size   = CAMERA_FRAME_SIZE;
  config.pixel_format = PIXFORMAT_JPEG;
  config.fb_count     = 1;
  config.jpeg_quality = CAMERA_JPEG_QUALITY;
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

  // Initialize GPIO
  pinMode(POWER_BUTTON_PIN, INPUT_PULLUP);
  pinMode(STATUS_LED_PIN, OUTPUT);
  
  // LED uses inverted logic: HIGH = OFF, LOW = ON
  digitalWrite(STATUS_LED_PIN, HIGH);
  
  // Setup button interrupt
  attachInterrupt(digitalPinToInterrupt(POWER_BUTTON_PIN), buttonISR, CHANGE);
  
  // Start LED boot sequence
  ledMode = LED_BOOT_SEQUENCE;
  
  // Power optimization from config.h
  setCpuFrequencyMhz(NORMAL_CPU_FREQ_MHZ);
  lastActivity = millis();
  
  configure_ble();
  configure_camera();

  // Allocate buffer for photo chunks (200 bytes + 2 for frame index)
  s_compressed_frame_2 = (uint8_t *)ps_calloc(202, sizeof(uint8_t));
  if (!s_compressed_frame_2) {
    Serial.println("Failed to allocate chunk buffer!");
  } else {
    Serial.println("Chunk buffer allocated successfully.");
  }

  // Set default capture interval from config
  isCapturingPhotos = true;
  captureInterval = PHOTO_CAPTURE_INTERVAL_MS;
  lastCaptureTime = millis() - captureInterval;
  Serial.print("Default capture interval set to ");
  Serial.print(PHOTO_CAPTURE_INTERVAL_MS / 1000);
  Serial.println(" seconds.");
  
  // Initial battery reading
  readBatteryLevel();
  deviceState = DEVICE_ACTIVE;
  
  Serial.println("Setup complete.");
  Serial.println("Light sleep optimization enabled for extended battery life.");
}

void loop() {
  unsigned long now = millis();

  // Handle button presses
  handleButton();
  
  // Update LED
  updateLED();
  
  // Check for power save mode (gentle optimization)
  if (!connected && !photoDataUploading && (now - lastActivity > IDLE_THRESHOLD_MS)) {
    enterPowerSave();
  } else if (connected || photoDataUploading) {
    if (powerSaveMode) exitPowerSave();
    lastActivity = now;
  }

  // Check battery level periodically
  if (now - lastBatteryCheck >= BATTERY_TASK_INTERVAL_MS) {
    readBatteryLevel();
    updateBatteryService();
    lastBatteryCheck = now;
  }
  
  // Force battery update on first connection
  static bool firstBatteryUpdate = true;
  if (connected && firstBatteryUpdate) {
    readBatteryLevel();
    updateBatteryService();
    firstBatteryUpdate = false;
  }

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
      
      lastActivity = now; // Register activity
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

  // Light sleep optimization - major power savings while maintaining BLE
  if (!photoDataUploading) {
    enableLightSleep();
  }
  
  // Adaptive delays for power saving (gentle optimization)
  if (photoDataUploading) {
    delay(20);  // Fast during upload
  } else if (powerSaveMode) {
    delay(50);  // Reduced delay with light sleep
  } else {
    delay(50);  // Reduced delay with light sleep
  }
}
