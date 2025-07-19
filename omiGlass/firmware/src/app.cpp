#include "app.h"

#include <BLE2902.h>
#include <BLEAdvertisedDevice.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <BLEUtils.h>

#include "config.h" // Use config.h for all configurations
#include "esp_camera.h"
#include "esp_sleep.h"
#include "config.h"  // Use config.h for all configurations
#include <Update.h>
#include <esp_partition.h>

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
#define DEVICE_INFORMATION_SERVICE_UUID (uint16_t) 0x180A
#define MANUFACTURER_NAME_STRING_CHAR_UUID (uint16_t) 0x2A29
#define MODEL_NUMBER_STRING_CHAR_UUID (uint16_t) 0x2A24
#define FIRMWARE_REVISION_STRING_CHAR_UUID (uint16_t) 0x2A26
#define HARDWARE_REVISION_STRING_CHAR_UUID (uint16_t) 0x2A27

// Main Friend Service - using config.h UUIDs
static BLEUUID serviceUUID(OMI_SERVICE_UUID);
static BLEUUID photoDataUUID(PHOTO_DATA_UUID);
static BLEUUID photoControlUUID(PHOTO_CONTROL_UUID);

// OTA Service UUIDs
static BLEUUID otaServiceUUID(OTA_SERVICE_UUID);
static BLEUUID otaDataUUID(OTA_DATA_UUID);
static BLEUUID otaControlUUID(OTA_CONTROL_UUID);

// BLE Server
BLEServer *bleServer = nullptr;

// Characteristics
BLECharacteristic *photoDataCharacteristic;
BLECharacteristic *photoControlCharacteristic;
BLECharacteristic *batteryLevelCharacteristic;

// OTA Characteristics
BLECharacteristic *otaDataCharacteristic;
BLECharacteristic *otaControlCharacteristic;

// State
bool connected = false;
bool isCapturingPhotos = false;
int captureInterval = 0; // Interval in ms
unsigned long lastCaptureTime = 0;

size_t sent_photo_bytes = 0;
size_t sent_photo_frames = 0;
bool photoDataUploading = false;

// OTA State
ota_state_t otaState = OTA_IDLE;
uint8_t *otaBuffer = nullptr;
size_t otaBufferSize = 0;
size_t otaReceivedBytes = 0;
size_t otaTotalBytes = 0;
bool otaUpdateStarted = false;

// -------------------------------------------------------------------------
// Camera Frame
// -------------------------------------------------------------------------
camera_fb_t *fb = nullptr;
image_orientation_t current_photo_orientation = ORIENTATION_0_DEGREES;

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
void handleOtaControl(uint8_t command);
void handleOtaData(uint8_t* data, size_t length);
void otaStart();
void otaEnd();
void otaAbort();

// -------------------------------------------------------------------------
// Button ISR
// -------------------------------------------------------------------------
void IRAM_ATTR buttonISR()
{
    buttonPressed = true;
}

// -------------------------------------------------------------------------
// LED Functions
// -------------------------------------------------------------------------
void updateLED()
{
    unsigned long now = millis();
    static unsigned long bootStartTime = 0;
    static unsigned long powerOffStartTime = 0;

    switch (ledMode) {
    case LED_BOOT_SEQUENCE:
        if (bootStartTime == 0)
            bootStartTime = now;

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
        if (powerOffStartTime == 0)
            powerOffStartTime = now;

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

void blinkLED(int count, int delayMs)
{
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
void handleButton()
{
    if (!buttonPressed)
        return;

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
void enterPowerSave()
{
    if (!powerSaveMode) {
        setCpuFrequencyMhz(MIN_CPU_FREQ_MHZ); // 40MHz for idle
        powerSaveMode = true;
    }
}

<<<<<<< HEAD
void exitPowerSave()
{
    if (powerSaveMode) {
        setCpuFrequencyMhz(NORMAL_CPU_FREQ_MHZ); // Back to 80MHz
        powerSaveMode = false;
    }
=======
// -------------------------------------------------------------------------
// OTA Functions
// -------------------------------------------------------------------------

void handleOtaControl(uint8_t command) {
  switch (command) {
    case OTA_CMD_START:
      Serial.println("OTA: Starting firmware update");
      otaStart();
      break;
    case OTA_CMD_END:
      if (otaState == OTA_RECEIVING) {
        // Arduino Update library handles validation internally
        Serial.print("OTA: Received end command. Total bytes received: ");
        Serial.println(otaReceivedBytes);
        otaEnd();
      } else {
        Serial.println("Ignoring OTA_CMD_END, not in receiving state.");
      }
      break;
    case OTA_CMD_ABORT:
      if (otaState == OTA_RECEIVING) {
        otaAbort();
      } else {
        Serial.println("Ignoring OTA_CMD_ABORT, not in an OTA session.");
      }
      break;
    default:
      Serial.print("Unknown OTA command: ");
      Serial.println(command);
      break;
  }
}

void handleOtaData(uint8_t* data, size_t length) {
  if (otaState != OTA_RECEIVING) {
    Serial.println("Ignoring OTA data, not in receiving state.");
    return;
  }

  if (!data || length == 0) return;
  
  // Update activity timestamp to prevent power save mode during OTA
  lastActivity = millis();

  if (length > 0) {
    // Validate we don't exceed maximum firmware size
    if (otaReceivedBytes + length > OTA_MAX_FIRMWARE_SIZE) {
        Serial.println("OTA Error: Firmware too large. Aborting.");
        otaAbort();
        return;
    }

    // Write data using Arduino Update library
    size_t written = Update.write(data, length);
    if (written != length) {
      Serial.print("OTA: Update.write failed. Expected: ");
      Serial.print(length);
      Serial.print(", Written: ");
      Serial.println(written);
      Serial.print("Error: ");
      Serial.println(Update.errorString());
      otaAbort();
      return;
    }
    otaReceivedBytes += length;
    
    // progress report every 10KB
    static size_t lastReportedBytes = 0;
    if (otaReceivedBytes - lastReportedBytes >= 10240) {
      Serial.print("OTA Progress: ");
      Serial.print(otaReceivedBytes);
      Serial.println(" bytes received");
      lastReportedBytes = otaReceivedBytes;
    }
  }
}

void otaStart() {
  // Stop photo capture during OTA
  isCapturingPhotos = false;
  photoDataUploading = false;
  
  // Disable power save mode during OTA for maximum stability
  if (powerSaveMode) exitPowerSave();
  lightSleepEnabled = false;
  
  if (!Update.begin(UPDATE_SIZE_UNKNOWN)) {
    Serial.print("OTA: Update.begin failed: ");
    Serial.println(Update.errorString());
    otaState = OTA_ERROR;
    return;
  }

  Serial.println("OTA: Update library initialized successfully");

  otaUpdateStarted = true;
  otaState = OTA_RECEIVING;
  otaReceivedBytes = 0;
  otaTotalBytes = 0;
  
  Serial.println("OTA: Ready to receive firmware data");
}

void otaEnd() {
  Serial.println("OTA: Ending firmware update");

  if (!otaUpdateStarted) {
    Serial.println("OTA Error: Update not started.");
    otaAbort();
    return;
  }

  Serial.println("OTA: Finalizing update");
  
  // Finalize the update
  if (!Update.end(true)) {
    Serial.print("OTA: Update.end failed: ");
    Serial.println(Update.errorString());
    otaAbort();
    return;
  }

  // Verify the update
  if (!Update.isFinished()) {
    Serial.println("OTA Error: Update not finished properly.");
    otaAbort();
    return;
  }

  otaUpdateStarted = false;
  otaState = OTA_SUCCESS;
  ledMode = LED_ON;  // Set LED to solid on for success indication
  
  Serial.println("OTA update successful! Rebooting in 3 seconds...");
  uint8_t success_cmd = (uint8_t)OTA_SUCCESS;
  otaControlCharacteristic->setValue(&success_cmd, 1);
  otaControlCharacteristic->notify();

  delay(3000);
  esp_restart();
}

void otaAbort() {
  if (otaUpdateStarted) {
    Update.abort();
    otaUpdateStarted = false;
  }
  
  otaState = OTA_IDLE;
  otaReceivedBytes = 0;
  otaTotalBytes = 0;
  
  // Re-enable power saving features
  lightSleepEnabled = true;
  isCapturingPhotos = true;
  
  Serial.println("OTA: Update aborted");
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
>>>>>>> 0713f3b9e (add ota updates for omi glass)
}

void enableLightSleep()
{
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
        if (sleepTime > 15000)
            sleepTime = 15000;                           // Max 15 seconds
        esp_sleep_enable_timer_wakeup(sleepTime * 1000); // Wake 5s before photo or max 15s
        esp_light_sleep_start();
        lastActivity = millis(); // Update activity time after wake
    }
}

void shutdownDevice()
{
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

class ServerHandler : public BLEServerCallbacks
{
    void onConnect(BLEServer *server) override
    {
        connected = true;
        lastActivity = millis(); // Register activity - prevents sleep
        Serial.println(">>> BLE Client connected.");
        // Send current battery level on connect
        updateBatteryService();
    }
    void onDisconnect(BLEServer *server) override
    {
        connected = false;
        Serial.println("<<< BLE Client disconnected. Restarting advertising.");
        BLEDevice::startAdvertising();
    }
};

class PhotoControlCallback : public BLECharacteristicCallbacks
{
    void onWrite(BLECharacteristic *characteristic) override
    {
        if (characteristic->getLength() == 1) {
            int8_t received = characteristic->getData()[0];
            Serial.print("PhotoControl received: ");
            Serial.println(received);
            lastActivity = millis(); // Register activity - prevents sleep
            handlePhotoControl(received);
        }
    }
};

class OtaDataCallback : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    uint8_t* data = characteristic->getData();
    size_t length = characteristic->getLength();
    if (otaReceivedBytes == 0) {
      Serial.println("OTA: Started receiving firmware update");
    }
    lastActivity = millis(); // Register activity - prevents sleep
    handleOtaData(data, length);
  }
};

class OtaControlCallback : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    if (characteristic->getLength() == 1) {
      uint8_t command = characteristic->getData()[0];
      Serial.print("OTA Control received: ");
      Serial.println(command);
      lastActivity = millis(); // Register activity - prevents sleep
      handleOtaControl(command);
    }
  }
};

// -------------------------------------------------------------------------
// Battery Functions
// -------------------------------------------------------------------------
void readBatteryLevel()
{
    // Take multiple ADC readings for stability
    int adcSum = 0;
    for (int i = 0; i < 10; i++) {
        int value = analogRead(BATTERY_ADC_PIN);
        adcSum += value;
        delay(10);
    }
    int adcValue = adcSum / 10;

    // ESP32-S3 ADC: 12-bit (0-4095), reference voltage ~3.3V
    float adcVoltage = (adcValue / 4095.0f) * 3.3f;

    // Apply voltage divider ratio to get actual battery voltage
    batteryVoltage = adcVoltage * VOLTAGE_DIVIDER_RATIO;

    // Clamp voltage to reasonable range
    if (batteryVoltage > 5.0f)
        batteryVoltage = 5.0f;
    if (batteryVoltage < 2.5f)
        batteryVoltage = 2.5f;

    // Load-compensated battery calculation (accounts for voltage sag under load)
    float loadCompensatedMax = BATTERY_MAX_VOLTAGE;
    float loadCompensatedMin = BATTERY_MIN_VOLTAGE;

    // More accurate percentage calculation for load conditions
    if (batteryVoltage >= loadCompensatedMax) {
        batteryPercentage = 100;
    } else if (batteryVoltage <= loadCompensatedMin) {
        batteryPercentage = 0;
    } else {
        float range = loadCompensatedMax - loadCompensatedMin;
        batteryPercentage = (int) (((batteryVoltage - loadCompensatedMin) / range) * 100.0f);
    }

    // Smooth percentage changes to avoid jumpy readings
    static int lastBatteryPercentage = batteryPercentage;
    if (abs(batteryPercentage - lastBatteryPercentage) > 5) {
        batteryPercentage = lastBatteryPercentage + (batteryPercentage > lastBatteryPercentage ? 2 : -2);
    }
    lastBatteryPercentage = batteryPercentage;

    // Clamp percentage
    if (batteryPercentage > 100)
        batteryPercentage = 100;
    if (batteryPercentage < 0)
        batteryPercentage = 0;

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

void updateBatteryService()
{
    if (batteryLevelCharacteristic) {
        uint8_t batteryLevel = (uint8_t) batteryPercentage;
        batteryLevelCharacteristic->setValue(&batteryLevel, 1);

        if (connected) {
            batteryLevelCharacteristic->notify();
        }
    }
}

// -------------------------------------------------------------------------
// configure_ble()
// -------------------------------------------------------------------------
<<<<<<< HEAD
void configure_ble()
{
    Serial.println("Initializing BLE...");
    BLEDevice::init(BLE_DEVICE_NAME);
    BLEServer *server = BLEDevice::createServer();
    server->setCallbacks(new ServerHandler());

    // Main service
    BLEService *service = server->createService(serviceUUID);
=======
void configure_ble() {
  Serial.println("Initializing BLE...");
  
  // Increase BLE stack size to prevent stack corruption
  // esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
  // bt_cfg.controller_task_stack_size = 4096; // Increase from default (typically 3072)
  // esp_bt_controller_init(&bt_cfg);
  
  BLEDevice::init(BLE_DEVICE_NAME);
  bleServer = BLEDevice::createServer();
  bleServer->setCallbacks(new ServerHandler());

  // Main service
  BLEService *service = bleServer->createService(serviceUUID);
>>>>>>> 0713f3b9e (add ota updates for omi glass)

    // Photo Data characteristic
    photoDataCharacteristic = service->createCharacteristic(
        photoDataUUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
    BLE2902 *ccc = new BLE2902();
    ccc->setNotifications(true);
    photoDataCharacteristic->addDescriptor(ccc);

    // Photo Control characteristic
    photoControlCharacteristic = service->createCharacteristic(photoControlUUID, BLECharacteristic::PROPERTY_WRITE);
    photoControlCharacteristic->setCallbacks(new PhotoControlCallback());
    uint8_t controlValue = 0;
    photoControlCharacteristic->setValue(&controlValue, 1);

<<<<<<< HEAD
    // Battery Service
    BLEService *batteryService = server->createService(BATTERY_SERVICE_UUID);
    batteryLevelCharacteristic = batteryService->createCharacteristic(
        BATTERY_LEVEL_UUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
    BLE2902 *batteryCcc = new BLE2902();
    batteryCcc->setNotifications(true);
    batteryLevelCharacteristic->addDescriptor(batteryCcc);

    // Set initial battery level
    readBatteryLevel();
    uint8_t initialBatteryLevel = (uint8_t) batteryPercentage;
    batteryLevelCharacteristic->setValue(&initialBatteryLevel, 1);
=======
  // Battery Service
  BLEService *batteryService = bleServer->createService(BATTERY_SERVICE_UUID);
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

  // OTA Service
  BLEService *otaService = bleServer->createService(otaServiceUUID);
  otaDataCharacteristic = otaService->createCharacteristic(
      otaDataUUID,
      BLECharacteristic::PROPERTY_WRITE);
  otaDataCharacteristic->setCallbacks(new OtaDataCallback());
  otaControlCharacteristic = otaService->createCharacteristic(
      otaControlUUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_READ);
  otaControlCharacteristic->setCallbacks(new OtaControlCallback());
  uint8_t command = 0;
  otaControlCharacteristic->setValue(&command, 1);
  
  BLE2902 *otaCcc = new BLE2902();
  otaCcc->setNotifications(false); // Start with notifications disabled
  otaControlCharacteristic->addDescriptor(otaCcc);

  // Device Information Service
  BLEService *deviceInfoService = bleServer->createService(DEVICE_INFORMATION_SERVICE_UUID);
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
>>>>>>> 0713f3b9e (add ota updates for omi glass)

    // Device Information Service
    BLEService *deviceInfoService = server->createService(DEVICE_INFORMATION_SERVICE_UUID);
    BLECharacteristic *manufacturerNameCharacteristic =
        deviceInfoService->createCharacteristic(MANUFACTURER_NAME_STRING_CHAR_UUID, BLECharacteristic::PROPERTY_READ);
    BLECharacteristic *modelNumberCharacteristic =
        deviceInfoService->createCharacteristic(MODEL_NUMBER_STRING_CHAR_UUID, BLECharacteristic::PROPERTY_READ);
    BLECharacteristic *firmwareRevisionCharacteristic =
        deviceInfoService->createCharacteristic(FIRMWARE_REVISION_STRING_CHAR_UUID, BLECharacteristic::PROPERTY_READ);
    BLECharacteristic *hardwareRevisionCharacteristic =
        deviceInfoService->createCharacteristic(HARDWARE_REVISION_STRING_CHAR_UUID, BLECharacteristic::PROPERTY_READ);

<<<<<<< HEAD
    manufacturerNameCharacteristic->setValue(MANUFACTURER_NAME);
    modelNumberCharacteristic->setValue(BLE_DEVICE_NAME);
    firmwareRevisionCharacteristic->setValue(FIRMWARE_VERSION_STRING);
    hardwareRevisionCharacteristic->setValue(HARDWARE_REVISION);

    // Start services
    service->start();
    batteryService->start();
    deviceInfoService->start();
=======
  // Start services
  service->start();
  batteryService->start();
  deviceInfoService->start();
  otaService->start();

  // Start advertising
  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(deviceInfoService->getUUID());
  advertising->addServiceUUID(service->getUUID());
  advertising->addServiceUUID(batteryService->getUUID());
  advertising->addServiceUUID(otaService->getUUID());
  advertising->setScanResponse(true);
  advertising->setMinPreferred(BLE_ADV_MIN_INTERVAL);
  advertising->setMaxPreferred(BLE_ADV_MAX_INTERVAL);
  BLEDevice::startAdvertising();
>>>>>>> 0713f3b9e (add ota updates for omi glass)

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
bool take_photo()
{
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

    // Set fixed orientation for the captured photo
    current_photo_orientation = FIXED_IMAGE_ORIENTATION;
    Serial.println("Photo orientation set to 180 degrees (fixed).");

    lastActivity = millis(); // Register activity
    return true;
}

void handlePhotoControl(int8_t controlValue)
{
    if (controlValue == -1) {
        Serial.println("Received command: Single photo.");
        isCapturingPhotos = true;
        captureInterval = 0;
    } else if (controlValue == 0) {
        Serial.println("Received command: Stop photo capture.");
        isCapturingPhotos = false;
        captureInterval = 0;
    } else if (controlValue >= 5 && controlValue <= 300) {
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
<<<<<<< HEAD
void configure_camera()
{
    Serial.println("Initializing camera...");
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
    config.xclk_freq_hz = CAMERA_XCLK_FREQ;

    // Use config.h camera settings optimized for battery life
    config.frame_size = CAMERA_FRAME_SIZE;
    config.pixel_format = PIXFORMAT_JPEG;
    config.fb_count = 1;
    config.jpeg_quality = CAMERA_JPEG_QUALITY;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Camera init failed with error 0x%x\n", err);
    } else {
        Serial.println("Camera initialized successfully.");
    }
=======
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
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
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
>>>>>>> 0713f3b9e (add ota updates for omi glass)
}

// -------------------------------------------------------------------------
// Setup & Loop
// -------------------------------------------------------------------------

// A small buffer for sending photo chunks over BLE
static uint8_t *s_compressed_frame_2 = nullptr;

<<<<<<< HEAD
void setup_app()
{
    Serial.begin(921600);
    Serial.println("Setup started...");

    // Initialize GPIO
    pinMode(POWER_BUTTON_PIN, INPUT_PULLUP);
    pinMode(STATUS_LED_PIN, OUTPUT);
=======
void setup_app() {
  Serial.begin(921600);
  Serial.println("Setup started...");
  
  // Initialize GPIO
  pinMode(POWER_BUTTON_PIN, INPUT_PULLUP);
  pinMode(STATUS_LED_PIN, OUTPUT);
>>>>>>> 0713f3b9e (add ota updates for omi glass)

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
    s_compressed_frame_2 = (uint8_t *) ps_calloc(202, sizeof(uint8_t));
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
    // Battery voltage divider
    analogReadResolution(12);                           // optional: set 12-bit resolution
    analogSetPinAttenuation(BATTERY_ADC_PIN, ADC_11db); // set attenuation for full 3.3V range

    readBatteryLevel();
    deviceState = DEVICE_ACTIVE;

    Serial.println("Setup complete.");
    Serial.println("Light sleep optimization enabled for extended battery life.");
}

void loop_app()
{
    unsigned long now = millis();

    // Handle button presses
    handleButton();

    // Update LED
    updateLED();

<<<<<<< HEAD
    // Check for power save mode (gentle optimization)
    if (!connected && !photoDataUploading && (now - lastActivity > IDLE_THRESHOLD_MS)) {
        enterPowerSave();
    } else if (connected || photoDataUploading) {
        if (powerSaveMode)
            exitPowerSave();
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
        if ((captureInterval == 0) || (now - lastCaptureTime >= (unsigned long) captureInterval)) {
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
            size_t bytes_to_copy;
            if (sent_photo_frames == 0) {
                // First chunk: includes orientation metadata
                s_compressed_frame_2[0] = 0; // Frame index low byte
                s_compressed_frame_2[1] = 0; // Frame index high byte
                s_compressed_frame_2[2] = (uint8_t) current_photo_orientation;
                bytes_to_copy = (remaining > 199) ? 199 : remaining;
                memcpy(&s_compressed_frame_2[3], &fb->buf[sent_photo_bytes], bytes_to_copy);
                photoDataCharacteristic->setValue(s_compressed_frame_2, bytes_to_copy + 3);
            } else {
                // Subsequent chunks
                s_compressed_frame_2[0] = (uint8_t) (sent_photo_frames & 0xFF);
                s_compressed_frame_2[1] = (uint8_t) ((sent_photo_frames >> 8) & 0xFF);
                bytes_to_copy = (remaining > 200) ? 200 : remaining;
                memcpy(&s_compressed_frame_2[2], &fb->buf[sent_photo_bytes], bytes_to_copy);
                photoDataCharacteristic->setValue(s_compressed_frame_2, bytes_to_copy + 2);
            }
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
        } else {
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
        delay(20); // Fast during upload
    } else if (powerSaveMode) {
        delay(50); // Reduced delay with light sleep
    } else {
        delay(50); // Reduced delay with light sleep
    }
}
=======
  if (false) {
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
}
>>>>>>> 0713f3b9e (add ota updates for omi glass)
