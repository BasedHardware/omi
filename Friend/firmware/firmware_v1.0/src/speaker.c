#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/device.h>

#include <zephyr/drivers/pwm.h>
#include <zephyr/drivers/i2s.h>
#include <zephyr/drivers/gpio.h>

#include <string.h>
#include <zephyr/logging/log.h>
#include <zephyr/logging/log_ctrl.h>

LOG_MODULE_REGISTER(speaker, CONFIG_LOG_DEFAULT_LEVEL);

#define MAX_BLOCK_SIZE   10000 //24000 * 2
#define BLOCK_COUNT 2     
#define SAMPLE_FREQUENCY 8000
#define NUMBER_OF_CHANNELS 2
#define PACKET_SIZE 400
#define WORD_SIZE 16
K_MEM_SLAB_DEFINE_STATIC(mem_slab, MAX_BLOCK_SIZE, BLOCK_COUNT, 4);
static void* rx_buffer;
static void* buzz_buffer;
static int16_t *ptr2;
static int16_t *clear_ptr;
static struct device *speaker;
static uint16_t current_length;
static uint16_t offset;
int speaker_init() {
        const struct device *speaker = device_get_binding("I2S_0");
	    if (!device_is_ready(speaker)) {
        LOG_ERR("Speaker device is not supported : %s", speaker->name);
        return 0;
    }
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
    int err = i2s_configure(speaker, I2S_DIR_TX, &config);
	if (err < 0) {
		LOG_INF("Failed to configure Microphone (%d)", err);
        return 0;
	}
    	err = k_mem_slab_alloc(&mem_slab, &rx_buffer, K_MSEC(200));
	if (err) {
		LOG_INF("Failed to allocate memory again(%d)", err);
        return 0;
	}

	err = k_mem_slab_alloc(&mem_slab, &buzz_buffer, K_MSEC(200));
	if (err) {
		LOG_INF("Failed to allocate memory again(%d)", err);
        return 0;
	}
      
        memset(rx_buffer, 0, MAX_BLOCK_SIZE);
        int16_t *noise = (int16_t*)buzz_buffer;

        memset(buzz_buffer, 0, MAX_BLOCK_SIZE);
        return 1;
}

uint16_t speak(uint16_t len, const void *buf) {
  
	uint16_t amount = 0;
    amount = len;
	if (len == 4)  //if stage 1 
	{
        current_length = ((uint32_t *)buf)[0];
	    LOG_INF("About to write %u bytes", current_length);
        ptr2 = (int16_t *)rx_buffer;
        clear_ptr = (int16_t *)rx_buffer;
	}
    else { //if not stage 1
        if (current_length > PACKET_SIZE) {
            LOG_INF("Data length: %u", len);
            current_length = current_length - PACKET_SIZE;
            LOG_INF("remaining data: %u", current_length);

            for (int i = 0; i < len/2; i++) {
                *ptr2++ = ((int16_t *)buf)[i];  
                ptr2++;

            }
            offset = offset + len;
        }
        else if (current_length < PACKET_SIZE) {
            LOG_INF("entered the final stretch");
            LOG_INF("Data length: %u", len);
            current_length = current_length - len;
            LOG_INF("remaining data: %u", current_length);
            // memcpy(rx_buffer+offset, buf, len);
            for (int i = 0; i < len/2; i++) {
                *ptr2++ = ((int16_t *)buf)[i];  
                ptr2++;
            }
            offset = offset + len;
            LOG_INF("offset: %u", offset);
            
            i2s_write(speaker, rx_buffer,  MAX_BLOCK_SIZE);
            i2s_trigger(speaker, I2S_DIR_TX, I2S_TRIGGER_START);// calls are probably non blocking       
	        i2s_trigger(speaker, I2S_DIR_TX, I2S_TRIGGER_DRAIN);

            //clear the buffer

            k_sleep(K_MSEC(4000));
            memset(clear_ptr, 0, MAX_BLOCK_SIZE);
        }

    }
    return amount;
}


void buzz() {
        i2s_write(speaker, buzz_buffer,  MAX_BLOCK_SIZE);
        i2s_trigger(speaker, I2S_DIR_TX, I2S_TRIGGER_START);// calls are probably non blocking       
	    i2s_trigger(speaker, I2S_DIR_TX, I2S_TRIGGER_DRAIN);  
        k_msleep(4000);
}