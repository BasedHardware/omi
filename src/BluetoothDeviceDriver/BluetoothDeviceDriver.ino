#include <mic.h>
#include <LSM6DS3.h> // make sure to use the library "Seeed arduino LSM6DS3"
#include <ArduinoBLE.h>

// Settings
#define DEBUG 1       // Enable pin pulse during ISR
#define SAMPLES 4000  // Changed to 4000
#define CHUNK_SIZE 200
#define BUFFER_SIZE (SAMPLES * 4)  // Doubled the buffer size to accommodate continuous recording
#define int2Pin PIN_LSM6DS3TR_C_INT1

mic_config_t mic_config{
  .channel_cnt = 1,
  .sampling_rate = 16000,   // Keep the sampling rate at 16000
  .buf_size = 16000,        // Use the larger buffer size
  .debug_pin = LED_BUILTIN  // Toggles each DAC ISR (if DEBUG is set to 1)
};

LSM6DS3 gyro(I2C_MODE, 0x6A);  // gyro init
NRF52840_ADC_Class Mic(&mic_config);

uint16_t recording_buf[BUFFER_SIZE];
volatile uint32_t recording_idx = 0;
volatile uint32_t read_idx = 0;
volatile bool recording = false;
bool isConnected = false;

uint8_t tapCount = 0;      // Amount of received taps
uint8_t prevTapCount = 0;  // Tap Counter from last loop

BLEService audioService("19B10000-E8F2-537E-4F6C-D104768A1214");
BLECharacteristic audioCharacteristic("19B10001-E8F2-537E-4F6C-D104768A1214", BLERead | BLENotify, CHUNK_SIZE * sizeof(int16_t));

void setup() {
  pinMode(int2Pin, INPUT);
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(LEDR, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  Serial.begin(115200);

  unsigned long startMillis = millis();
  while (!Serial && millis() - startMillis < 500) {
    delay(10);  // Short delay to prevent hanging in a tight loop
  }

#if defined(WIO_TERMINAL)
  pinMode(WIO_KEY_A, INPUT_PULLUP);
  Serial.println("WIO_TERMINAL");
#elif defined(ARDUINO_ARCH_NRF52840)
  Serial.println("ARDUINO_ARCH_NRF52840");
#endif

  Mic.set_callback(audio_rec_callback);
  if (!Mic.begin()) {
    Serial.println("Mic initialization failed");
    setLedRGB(true, false, false);
    while (1)
      ;
  }
  Serial.println("Mic initialization done.");
  setLedRGB(false, true, false);

  if (!BLE.begin()) {
    Serial.println("Starting Bluetooth® Low Energy module failed!");
    setLedRGB(true, false, false);
    while (1)
      ;
  }

  if (gyro.begin() != 0) {
    Serial.println("gyro error");
    setLedRGB(true, false, false);
    while (1)
      ;
  }
  Serial.println("Gyro initialization done.");

  setupDoubleTap();

  attachInterrupt(digitalPinToInterrupt(int2Pin), tapCallback, RISING);

  setLedRGB(false, true, false);
  BLE.setLocalName("AudioRecorder");

  BLE.setAdvertisedService(audioService);
  audioService.addCharacteristic(audioCharacteristic);
  BLE.addService(audioService);
  BLE.advertise();

  // Print device address
  Serial.print("Device Address: ");
  Serial.println(BLE.address());

  Serial.println("BLE Audio Recorder");
}

void loop() {
  BLEDevice central = BLE.central();

  if (central && !isConnected) {
    Serial.print("Connected to central: ");
    Serial.println(central.address());
    isConnected = true;
    Serial.println("Type 'rec' to start recording");
  }

  if (tapCount > prevTapCount) {
    Serial.println("Double tapped!");

    if (!recording) {
      // Start recording
      recording = true;
      setLedRGB(true, false, true);
      Serial.println("Recording started");
    } else {
      // Stop recording
      recording = false;
      setLedRGB(false, true, false);
      Serial.println("Recording stopped");
    }
  }

  prevTapCount = tapCount;

  if (Serial.available()) {
    String resp = Serial.readStringUntil('\n');
    if (resp == "rec" && !recording) {
      recording = true;
      setLedRGB(false, false, true);
      Serial.println("Recording started");
    } else if (resp == "stop" && recording) {
      recording = false;
      setLedRGB(false, true, false);
      Serial.println("Recording stopped");
    }
  }

  if (recording) {
    uint32_t available_samples = (recording_idx + BUFFER_SIZE - read_idx) % BUFFER_SIZE;
    if (available_samples >= CHUNK_SIZE) {
      Serial.print("Sending ");
      Serial.print(available_samples);
      Serial.println(" samples");

      uint16_t chunk[CHUNK_SIZE];
      for (int i = 0; i < CHUNK_SIZE; i++) {
        chunk[i] = recording_buf[(read_idx + i) % BUFFER_SIZE];
      }
      audioCharacteristic.writeValue(chunk, sizeof(chunk));
      read_idx = (read_idx + CHUNK_SIZE) % BUFFER_SIZE;
      delay(20);
    }
  }
}

static void audio_rec_callback(uint16_t *buf, uint32_t buf_len) {
  if (recording) {
    for (uint32_t i = 0; i < buf_len; i += 4) {
      recording_buf[recording_idx] = buf[i];
      recording_idx = (recording_idx + 1) % BUFFER_SIZE;
    }
  }
}

void setupDoubleTap() {
  // Double Tap Config
  gyro.writeRegister(LSM6DS3_ACC_GYRO_CTRL1_XL, 0x60);     //* Acc = 416Hz (High-Performance mode)// Turn on the accelerometer
  gyro.writeRegister(LSM6DS3_ACC_GYRO_TAP_CFG1, 0x8E);     // INTERRUPTS_ENABLE, SLOPE_FDS// Enable interrupts and tap detection on X, Y, Z-axis
  gyro.writeRegister(LSM6DS3_ACC_GYRO_TAP_THS_6D, 0x85);   // Set tap threshold 8C
  gyro.writeRegister(LSM6DS3_ACC_GYRO_INT_DUR2, 0x7F);     // Set Duration, Quiet and Shock time windows 7F
  gyro.writeRegister(LSM6DS3_ACC_GYRO_WAKE_UP_THS, 0x80);  // Single & double-tap enabled (SINGLE_DOUBLE_TAP = 1)
  gyro.writeRegister(LSM6DS3_ACC_GYRO_MD1_CFG, 0x08);      // Double-tap interrupt driven to INT1 pin
}

void tapCallback() {
  tapCount++;
}

void setLedRGB(bool red, bool green, bool blue) {
  digitalWrite(LEDB, blue ? LOW : HIGH);   // Blue ON when blue is true
  digitalWrite(LEDG, green ? LOW : HIGH);  // Green ON when green is true
  digitalWrite(LEDR, red ? LOW : HIGH);    // Red ON when red is true
}