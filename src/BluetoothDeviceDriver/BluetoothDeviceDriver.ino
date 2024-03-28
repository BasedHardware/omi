#include <ArduinoBLE.h>
#include <mic.h>

// Settings
#define DEBUG 1      // Enable pin pulse during ISR
#define SAMPLES 4000 // Changed to 4000
#define CHUNK_SIZE 200
#define BUFFER_SIZE (SAMPLES * 4) // Doubled the buffer size to accommodate continuous recording

mic_config_t mic_config{
    .channel_cnt = 1,
    .sampling_rate = 16000,  // Keep the sampling rate at 16000
    .buf_size = 16000,       // Use the larger buffer size
    .debug_pin = LED_BUILTIN // Toggles each DAC ISR (if DEBUG is set to 1)
};

NRF52840_ADC_Class Mic(&mic_config);

uint16_t recording_buf[BUFFER_SIZE];
volatile uint32_t recording_idx = 0;
volatile uint32_t read_idx = 0;
volatile bool recording = false;
bool isConnected = false;

BLEService audioService("19B10000-E8F2-537E-4F6C-D104768A1214");
BLECharacteristic audioCharacteristic("19B10001-E8F2-537E-4F6C-D104768A1214", BLERead | BLENotify, CHUNK_SIZE * sizeof(int16_t));

void setup()
{
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
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
    digitalWrite(LED_BUILTIN, HIGH);
    while (1)
      ;
  }
  Serial.println("Mic initialization done.");
  digitalWrite(LED_BUILTIN, LOW);
  digitalWrite(LED_GREEN, HIGH);

  if (!BLE.begin())
  {
    Serial.println("Starting Bluetooth® Low Energy module failed!");
    digitalWrite(LED_BUILTIN, HIGH);
    while (1)
      ;
  }

  digitalWrite(LED_BUILTIN, LOW);
  digitalWrite(LED_GREEN, HIGH);
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

  if (Serial.available())
  {
    String resp = Serial.readStringUntil('\n');
    if (resp == "rec")
    {
      recording = true;
      digitalWrite(LED_BUILTIN, LOW);
      digitalWrite(LED_BLUE, HIGH);
      Serial.println("Recording started");
    }
    else if (resp == "stop")
    {
      recording = false;
      digitalWrite(LED_GREEN, HIGH);
      digitalWrite(LED_BLUE, LOW);
      Serial.println("Recording stopped");
    }
  }

  if (recording)
  {
    uint32_t available_samples = (recording_idx + BUFFER_SIZE - read_idx) % BUFFER_SIZE;
    if (available_samples >= CHUNK_SIZE)
    {
      Serial.print("Sending ");
      Serial.print(available_samples);
      Serial.println(" samples");

      uint16_t chunk[CHUNK_SIZE];
      for (int i = 0; i < CHUNK_SIZE; i++)
      {
        chunk[i] = recording_buf[(read_idx + i) % BUFFER_SIZE];
      }
      audioCharacteristic.writeValue(chunk, sizeof(chunk));
      read_idx = (read_idx + CHUNK_SIZE) % BUFFER_SIZE;
      delay(20);
    }
  }
}

static void audio_rec_callback(uint16_t *buf, uint32_t buf_len)
{
  if (recording)
  {
    for (uint32_t i = 0; i < buf_len; i += 4)
    {
      recording_buf[recording_idx] = buf[i];
      recording_idx = (recording_idx + 1) % BUFFER_SIZE;
    }
  }
}
