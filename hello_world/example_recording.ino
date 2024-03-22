#include <mic.h>
#if defined(WIO_TERMINAL)
#include "processing/filters.h"
#endif

// Settings
#if defined(WIO_TERMINAL)
#define DEBUG 1                 // Enable pin pulse during ISR  
#define SAMPLES 16000*10
#elif defined(ARDUINO_ARCH_NRF52840)
#endif

mic_config_t mic_config{
  .channel_cnt = 1,
  .sampling_rate = 16000,
  #if defined(WIO_TERMINAL)
    .buf_size = 320,
    .debug_pin = 1                // Toggles each DAC ISR (if DEBUG is set to 1)
  #elif defined(ARDUINO_ARCH_NRF52840)
    .buf_size = 1600,
    .debug_pin = LED_BUILTIN                // Toggles each DAC ISR (if DEBUG is set to 1)
  #endif
};

#if defined(WIO_TERMINAL)
DMA_ADC_Class Mic(&mic_config);
#elif defined(ARDUINO_ARCH_NRF52840)
NRF52840_ADC_Class Mic(&mic_config);
#endif

int16_t recording_buf[SAMPLES];
volatile uint8_t recording = 0;
volatile static bool record_ready = false;

#if defined(WIO_TERMINAL)
FilterBuHp filter;
#endif

void setup() {
  Serial.begin(57600);
  while (!Serial) {delay(10);}

#if defined(WIO_TERMINAL)
  pinMode(WIO_KEY_A, INPUT_PULLUP);
#endif
  
  Mic.set_callback(audio_rec_callback);

  if (!Mic.begin()) {
    Serial.println("init_fail");
    while (1);
  }

  Serial.println("init_ok");

}

void loop() { 
  String resp = Serial.readString();

  if (resp == "init\n" && !recording){
    Serial.println("init_ok");
  }
    
  if (resp == "rec\n" && !recording) {

      recording = 1;
      record_ready = false;  
  }

  if (!recording && record_ready)
  {
    
    Serial.println("rec_ok");
    for (int i = 0; i < SAMPLES; i++) {
      
    Serial.println(recording_buf[i]);

    }

    Serial.println("fi");
    record_ready = false; 
  }
}

static void audio_rec_callback(uint16_t *buf, uint32_t buf_len) {

  static uint32_t idx = 0;

  if (recording) {
    for (uint32_t i = 0; i < buf_len; i++) {
      
    #if defined(WIO_TERMINAL)
          // Convert 12-bit unsigned ADC value to 16-bit PCM (signed) audio value
          recording_buf[idx++] = filter.step((int16_t)(buf[i] - 1024) * 16);    //with Filter
          //recording_buf[idx++] = (int16_t)(buf[i] - 1024) * 16;               // without filter
    #elif defined(ARDUINO_ARCH_NRF52840)
          recording_buf[idx++] = buf[i];
    #endif
          
      if (idx >= SAMPLES){ 
        idx = 0;
        recording = 0;
        record_ready = true;
        break;
     } 
    }
  }
}
