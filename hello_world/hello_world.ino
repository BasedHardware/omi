#include <PDM.h>

const int sampleRate = 16000;
const int recordDuration = 5; // Recording duration in seconds
const int bufferSize = 256;
bool isRecording = false;

void setup() {
  Serial.begin(9600);
  while (!Serial);

  Serial.println("Serial Audio Recorder");

  PDM.onReceive(onPDMdata);
  PDM.setBufferSize(bufferSize);
  PDM.setGain(20);

  if (!PDM.begin(1, sampleRate)) {
    Serial.println("Failed to start PDM!");
    while (1);
  }

  isRecording = true; // Start recording automatically
}

void loop() {
  if (isRecording) {
    recordAudio();
  }
}

void recordAudio() {
  Serial.println("Recording audio...");
  unsigned long startTime = millis();
  short sampleBuffer[bufferSize];

  while (millis() - startTime < recordDuration * 1000) {
    int samplesRead = PDM.read(sampleBuffer, min(PDM.available(), bufferSize));
    for (int i = 0; i < samplesRead; i++) {
      Serial.write((byte*)&sampleBuffer[i], sizeof(short));
    }
  }

  Serial.println("\nRecording finished.");
  isRecording = false;
}

void onPDMdata() {
  // Implement this function if needed for handling PDM data.
}
