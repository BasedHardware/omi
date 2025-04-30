#include <zephyr/kernel.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/device.h>
#include <zephyr/drivers/i2s.h>
#include <zephyr/drivers/gpio.h>
#include <math.h>
#include <zephyr/logging/log.h>
#include <zephyr/logging/log_ctrl.h>
#include "speaker.h"

LOG_MODULE_REGISTER(speaker, CONFIG_LOG_DEFAULT_LEVEL);

#define MAX_BLOCK_SIZE   10000 //24000 * 2

#define BLOCK_COUNT 2     
#define SAMPLE_FREQUENCY 8000
#define NUMBER_OF_CHANNELS 2
#define PACKET_SIZE 400
#define WORD_SIZE 16
#define NUM_CHANNELS 2

#define PI 3.14159265358979323846

K_MEM_SLAB_DEFINE_STATIC(mem_slab, MAX_BLOCK_SIZE, BLOCK_COUNT, 2);

struct device *audio_speaker;

static void* rx_buffer;
static void* buzz_buffer;
static int16_t *ptr2;
static int16_t *clear_ptr;

static uint16_t current_length;
static uint16_t offset;

struct gpio_dt_spec speaker_gpio_pin = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio0)), .pin=4, .dt_flags = GPIO_INT_DISABLE};

// ble service for speaker audio
//

// Forward declaration for speaker audio write handler if needed
// static ssize_t speaker_audio_write_handler(...)

// Speaker Service UUID (assuming this remains for audio)
static struct bt_uuid_128 speaker_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0xCAB1AB95, 0x2EA5, 0x4F4D, 0xBB56, 0x874B72CFC984));
// Speaker Audio Characteristic UUID (assuming a characteristic for audio data write)
// static struct bt_uuid_128 speaker_audio_char_uuid = BT_UUID_INIT_128(...)

// Speaker Service Attributes (only speaker-related characteristics)
static struct bt_gatt_attr speaker_service_attrs[] = {
    BT_GATT_PRIMARY_SERVICE(&speaker_service_uuid),
    // Add speaker audio characteristic(s) here if needed
    // Example:
    // BT_GATT_CHARACTERISTIC(&speaker_audio_char_uuid.uuid, BT_GATT_CHRC_WRITE, BT_GATT_PERM_WRITE, NULL, speaker_audio_write_handler, NULL),
};
static struct bt_gatt_service speaker_service = BT_GATT_SERVICE(speaker_service_attrs);

// Register Speaker Service (only speaker-related)
void register_speaker_service()
{
    // Check if there are any attributes before registering
    if (ARRAY_SIZE(speaker_service_attrs) > 1) {
         int err = bt_gatt_service_register(&speaker_service);
         if (err) {
             LOG_ERR("Failed to register Speaker GATT service (err %d)", err);
         } else {
             LOG_INF("Speaker GATT service registered");
         }
    } else {
        LOG_WRN("No speaker characteristics defined, service not registered.");
    }
}

int speaker_init()
{
    LOG_INF("Speaker init");
    audio_speaker = device_get_binding("I2S_0");
    
    if (!device_is_ready(audio_speaker)) 
    {
        LOG_ERR("Speaker device is not supported : %s", audio_speaker->name);
        return -1;
    }


    if (gpio_is_ready_dt(&speaker_gpio_pin)) 
    {
		LOG_PRINTK("Speaker Pin ready\n");
	}
    else 
    {
		LOG_PRINTK("Error setting up speaker Pin\n");
        return -1;
	}
	if (gpio_pin_configure_dt(&speaker_gpio_pin, GPIO_OUTPUT_INACTIVE) < 0) 
    {
		LOG_PRINTK("Error setting up Speaker Pin\n");
        return -1;
	}
    gpio_pin_set_dt(&speaker_gpio_pin, 1);
    
    struct i2s_config config = {
    .word_size= WORD_SIZE, //how long is one left/right word.
    .channels = NUMBER_OF_CHANNELS, //how many words in a frame 2 
    .format = I2S_FMT_DATA_FORMAT_LEFT_JUSTIFIED, //format
    // .format = I2S_FMT_DATA_FORMAT_I2S,
    .options = I2S_OPT_FRAME_CLK_MASTER | I2S_OPT_BIT_CLK_MASTER | I2S_OPT_BIT_CLK_GATED, //how to configure the mclock
    .frame_clk_freq = SAMPLE_FREQUENCY, /* Sampling rate */ 
    .mem_slab = &mem_slab,/* Memory slab to store rx/tx data */
    .block_size = MAX_BLOCK_SIZE,/* size of ONE memory block in bytes */
    .timeout = -1, /* Number of milliseconds to wait in case Tx queue is full or RX queue is empty, or 0, or SYS_FOREVER_MS */
    };
    int err = i2s_configure(audio_speaker, I2S_DIR_TX, &config);
	if (err) 
    {
		LOG_ERR("Failed to configure Speaker (%d)", err);
        return -1;
	}
    err = k_mem_slab_alloc(&mem_slab, &rx_buffer, K_MSEC(200));
	if (err)
    {
		LOG_INF("Failed to allocate memory for speaker%d)", err);
        return -1;
	}

	err = k_mem_slab_alloc(&mem_slab, &buzz_buffer, K_MSEC(200));
	if (err) 
    {
		LOG_INF("Failed to allocate for chime (%d)", err);
        return -1;
	}
      
    memset(rx_buffer, 0, MAX_BLOCK_SIZE);
    memset(buzz_buffer, 0, MAX_BLOCK_SIZE);

    
    return 0;
}

uint16_t speak(uint16_t len, const void *buf) //direct from bt
{
	uint16_t amount = 0;
    amount = len;
	if (len == 4)  //if stage 1 
	{
        current_length = ((uint32_t *)buf)[0];
	    LOG_INF("About to write %u bytes", current_length);
        ptr2 = (int16_t *)rx_buffer;
        clear_ptr = (int16_t *)rx_buffer;
	}
    else 
    { //if not stage 1
        if (current_length > PACKET_SIZE) 
        {
            LOG_INF("Data length: %u", len);
            current_length = current_length - PACKET_SIZE;
            LOG_INF("remaining data: %u", current_length);

            for (int i = 0; i < (int)(len/2); i++) 
            {
                *ptr2++ = ((int16_t *)buf)[i];  
                *ptr2++ = ((int16_t *)buf)[i]; 
            }
            offset = offset + len;
        }
        else if (current_length < PACKET_SIZE) 
        {
            LOG_INF("entered the final stretch");
            LOG_INF("Data length: %u", len);
            current_length = current_length - len;
            LOG_INF("remaining data: %u", current_length);
            // memcpy(rx_buffer+offset, buf, len);
            for (int i = 0; i < len/2; i++) 
            {
                *ptr2++ = ((int16_t *)buf)[i];  
                *ptr2++ = ((int16_t *)buf)[i];  
            }
            offset = offset + len;
            LOG_INF("offset: %u", offset);
            offset = 0;
            int res= i2s_write(audio_speaker, rx_buffer,  MAX_BLOCK_SIZE);
            if (res < 0)
            {
                LOG_PRINTK("Failed to write I2S data: %d\n", res);
            }
            i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_START);// calls are probably non blocking   
            if (res != 0) 
            {
                LOG_PRINTK("Failed to drain I2S transmission: %d\n", res);
            }    
	        res =  i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
            if (res != 0) 
            {
                LOG_PRINTK("Failed to drain I2S transmission: %d\n", res);
            }
            //clear the buffer
            k_sleep(K_MSEC(4000));

            memset(clear_ptr, 0, MAX_BLOCK_SIZE);

        }

    }
    return amount;
}


void generate_gentle_chime(int16_t *buffer, int num_samples)
{
    LOG_INF("Generating gentle chime");//2500
    const float frequencies[] = {523.25, 659.25, 783.99, 1046.50}; // C5, E5, G5, C6
    const int num_freqs = sizeof(frequencies) / sizeof(frequencies[0]);//4

    for (int i = 0; i < num_samples; i++) 
    { 
        float t = (float)i / SAMPLE_FREQUENCY;//0.000125
        float sample = 0;
        for (int j = 0; j < num_freqs; j++) 
        {
           sample += sinf(2 * PI * frequencies[j] * t) * (1.0 - t);
        }
        int16_t int_sample = (int16_t)(sample / num_freqs * 32767 * 0.5);
        buffer[i * NUM_CHANNELS] = int_sample;
        buffer[i * NUM_CHANNELS + 1] = int_sample;
    }
    LOG_INF("Done generating gentle chime");
}

int play_boot_sound(void)
{
    int ret;
    int16_t *buffer = (int16_t *) buzz_buffer;
    const int samples_per_block = MAX_BLOCK_SIZE / (NUM_CHANNELS * sizeof(int16_t));

    generate_gentle_chime(buffer, samples_per_block);
    LOG_INF("Writing to speaker");
    k_sleep(K_MSEC(100));
    ret = i2s_write(audio_speaker, buffer, MAX_BLOCK_SIZE);
    if (ret) 
    {
        LOG_ERR("Failed to write initial I2S data: %d", ret);
        return ret;
    }

    ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_START);
    if (ret) 
    {
        LOG_ERR("Failed to start I2S transmission: %d", ret);
        return ret;
    }  


    ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
    if (ret != 0) 
    {
        LOG_ERR("Failed to drain I2S transmission: %d", ret);
        return ret;
    }
    k_sleep(K_MSEC(3000));  

    return 0;
}

void speaker_off()
{

    gpio_pin_set_dt(&speaker_gpio_pin, 0);
}

