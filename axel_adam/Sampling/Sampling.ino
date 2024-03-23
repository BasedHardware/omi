#include <ArduinoBLE.h>
#include <mic.h>

// Settings
#define DEBUG 1      // Enable pin pulse during ISR
#define SAMPLES 8000 // Changed to 8000
#define CHUNK_SIZE 122

mic_config_t mic_config{
    .channel_cnt = 1,
    .sampling_rate = 16000,  // Keep the sampling rate at 16000
    .buf_size = SAMPLES * 2, // Doubled the buffer size to accommodate 16kHz data
    .debug_pin = LED_BUILTIN // Toggles each DAC ISR (if DEBUG is set to 1)
};

NRF52840_ADC_Class Mic(&mic_config);

uint16_t recording_buf[SAMPLES];
volatile uint8_t recording = 0;
bool isConnected = false;
volatile static bool record_ready = false;

BLEService audioService("19B10000-E8F2-537E-4F6C-D104768A1214");
BLECharacteristic audioCharacteristic("19B10001-E8F2-537E-4F6C-D104768A1214", BLERead | BLENotify, SAMPLES * sizeof(int16_t)); // Updated size

void setup()
{
  Serial.begin(115200);
  while (!Serial)
  {
    delay(10);
  }

#if defined(WIO_TERMINAL)
  pinMode(WIO_KEY_A, INPUT_PULLUP);
  Serial.println("WIO_TERMINAL");
#elif defined(ARDUINO_ARCH_NRF52840)
  Serial.println("ARDUINO_ARCH_NRF52840");
#endif

  Mic.set_callback(audio_rec_callback);
  if (!Mic.begin())
  {
    Serial.println("Mic initialization failed");
    while (1)
      ;
  }
  Serial.println("Mic initialization done.");

  if (!BLE.begin())
  {
    Serial.println("Starting Bluetooth® Low Energy module failed!");
    while (1)
      ;
  }

  BLE.setLocalName("AudioRecorder");
  BLE.setAdvertisedService(audioService);
  audioService.addCharacteristic(audioCharacteristic);
  BLE.addService(audioService);
  BLE.advertise();

  Serial.println("BLE Audio Recorder");
}

void loop()
{
  BLEDevice central = BLE.central();
  if (central && !isConnected)
  {
    Serial.print("Connected to central: ");
    Serial.println(central.address());
    isConnected = true;
    Serial.println("Type 'rec' to start recording");
  }

  String resp = Serial.readString();

  if (resp == "init\n" && !recording)
  {
    Serial.println("init_ok");
  }

  if (resp == "rec\n" && !recording)
  {
    recording = 1;
    record_ready = false;
  }

  if (record_ready)
  {
    int chunkCount = (SAMPLES + CHUNK_SIZE - 1) / CHUNK_SIZE;
    Serial.print("Sending ");
    Serial.print(chunkCount);
    Serial.println(" chunks via BLE");

    // Create an index number
    uint16_t index = 0;

    for (int chunk = 0; chunk < chunkCount; chunk++)
    {
      // Serial.println(chunk);

      int startIndex = chunk * CHUNK_SIZE;
      int endIndex = min(startIndex + CHUNK_SIZE, SAMPLES);
      int chunkSize = (endIndex - startIndex) * sizeof(int16_t); // Updated size calculation

      audioCharacteristic.writeValue(&recording_buf[startIndex], chunkSize);

      // Serial.print("Sending chunk");
      // Serial.print(chunk);
      // Serial.print(" with ");
      // Serial.print(chunkSize);
      // Serial.println(" bytes");

      // audioCharacteristic.writeValue(&chunkData, CHUNK_SIZE * 2);
      delay(50);
      // ++index;
    }
    // Send a specific value to indicate the end of audio data transmission
    uint8_t endSignal = 0xFF; // Example: Use 0xFF as the end signal value
    // audioCharacteristic.writeValue(&endSignal, 1);
    Serial.println("Done");
    record_ready = false;
    recording = false;
  }
}

static void audio_rec_callback(uint16_t *buf, uint32_t buf_len)
{
  static uint32_t idx = 0;
  if (recording)
  {
    // Copy samples from DMA buffer to inference buffer
    // Downsample by skipping every other sample to reduce the sample rate to 8kHz
    for (uint32_t i = 0; i < buf_len; i += 2) // Changed to i += 2 to skip every other sample
    {
      recording_buf[idx++] = buf[i];
      if (idx >= SAMPLES)
      {
        idx = 0;
        recording = 0;
        record_ready = true;
        break;
      }
    }
  }
}