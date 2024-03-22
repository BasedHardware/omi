#include <ArduinoBLE.h>
#include <PDM.h>

BLEService audioService("19B10000-E8F2-537E-4F6C-D104768A1214");
BLECharacteristic audioCharacteristic("19B10001-E8F2-537E-4F6C-D104768A1214", BLERead | BLENotify, 20); // Audio data characteristic

const int sampleRate = 16000;
const int recordDuration = 5; // Recording duration in seconds
const int bufferSize = 256;
bool isRecording = false;
bool isConnected = false;

void setup() {
  Serial.begin(9600);
  while (!Serial);

  if (!BLE.begin()) {
    Serial.println("Starting Bluetooth® Low Energy module failed!");
    while (1);
  }

  BLE.setLocalName("AudioRecorder");
  BLE.setAdvertisedService(audioService);
  audioService.addCharacteristic(audioCharacteristic);
  BLE.addService(audioService);
  BLE.advertise();

  Serial.println("BLE Audio Recorder");

  PDM.onReceive(onPDMdata);
  PDM.setBufferSize(bufferSize);
  PDM.setGain(20);

  if (!PDM.begin(1, 16000)) {
    Serial.println("Failed to start PDM!");
    while (1);
  }
}

void loop() {
  BLEDevice central = BLE.central();
  if (central) {
    if (!isConnected) {
      Serial.print("Connected to central: ");
      Serial.println(central.address());
      isConnected = true;
      isRecording = true; // Start recording automatically
    }

    if (isRecording) {
      recordAudio(central);
    }

    if (!central.connected()) {
      Serial.print("Disconnected from central: ");
      Serial.println(central.address());
      isConnected = false;
      isRecording = false;
    }
  }
}

void recordAudio(BLEDevice central) {
  Serial.println("Recording audio...");
  unsigned long startTime = millis();
  const int chunkSize = 20; // Chunk size in bytes
  short sampleBuffer[bufferSize];
  String binaryString = "";

  while (millis() - startTime < recordDuration * 1000) {
    PDM.read(sampleBuffer, min(PDM.available(), bufferSize));
    for (int i = 0; i < bufferSize; i++) {
      binaryString += String(sampleBuffer[i], BIN) + ",";
    }
  }

  Serial.println(binaryString.c_str());
  // Send the binary string over BLE
  audioCharacteristic.writeValue(binaryString.c_str());
  Serial.println("Recording finished.");
  isRecording = false;
}

void onPDMdata() {
  // No need to implement this function
}