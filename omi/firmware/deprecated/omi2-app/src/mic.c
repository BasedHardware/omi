#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/audio/dmic.h>
#include "config.h"
#include "mic.h"
#include "utils.h"
#include "led.h"

LOG_MODULE_REGISTER(mic, CONFIG_LOG_DEFAULT_LEVEL);

// Removed nrfx includes and PDM specific code
// Added DMIC device and GPIO definitions from device tree
static const struct device *const dmic_dev = DEVICE_DT_GET(DT_ALIAS(dmic0));
static const struct gpio_dt_spec mic_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_en_pin), gpios, {0});
static const struct gpio_dt_spec mic_thsel = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_thsel_pin), gpios, {0});
static const struct gpio_dt_spec mic_wake = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_wake_pin), gpios, {0});

// Forward declarations
static int mic_power_off(void);
static int mic_power_on(void);

// Define constants based on configuration and sample
#define BITS_PER_BYTE 8
#define SAMPLE_RATE_HZ CONFIG_MIC_SAMPLE_RATE // Use Kconfig value
#define SAMPLE_BITS 16 // T5838 is 16-bit
#define TIMEOUT_MS 1000
#define BLOCK_SIZE_BYTES ((SAMPLE_BITS / BITS_PER_BYTE) * MIC_BUFFER_SAMPLES)
#define BLOCK_COUNT 4 // Number of blocks for the slab

// Memory slab for audio buffers
K_MEM_SLAB_DEFINE_STATIC(dmic_mem_slab, BLOCK_SIZE_BYTES, BLOCK_COUNT, 4);

// DMIC stream and channel configuration
static struct pcm_stream_cfg stream_cfg = {
    .pcm_rate = SAMPLE_RATE_HZ,
    .pcm_width = SAMPLE_BITS,
    .block_size = BLOCK_SIZE_BYTES,
    .mem_slab = &dmic_mem_slab,
};

static struct dmic_cfg drv_cfg = {
    .io = {
        // Configure according to nRF5340 and T5838 specs if needed,
        // or use defaults. Using sample defaults for now.
        .min_pdm_clk_freq = 1000000,
        .max_pdm_clk_freq = 3500000,
        .min_pdm_clk_dc = 40,
        .max_pdm_clk_dc = 60,
    },
    .streams = &stream_cfg,
    .channel = {
        .req_num_streams = 1,
        // Assuming mono for now, adjust req_num_chan if stereo needed
        .req_num_chan = 1,
        // Map channel 0 to left PDM input (adjust if needed)
        // Initialize dynamically in mic_init
        // .req_chan_map_lo = dmic_build_channel_map(0, 0, PDM_CHAN_LEFT),
    },
};

// Callback and thread related variables
static volatile mix_handler _callback = NULL;
static K_THREAD_STACK_DEFINE(mic_stack_area, CONFIG_MIC_THREAD_STACK_SIZE);
static struct k_thread mic_thread_data;
static k_tid_t mic_tid;
static volatile bool mic_active = false;

// --- Replaced PDM IRQ Handler with DMIC Read Thread ---
static void mic_read_thread(void *p1, void *p2, void *p3)
{
    int ret;
    void *buffer = NULL;
    uint32_t size;

    LOG_INF("Mic read thread started");

    // Configure DMIC before starting loop
    ret = dmic_configure(dmic_dev, &drv_cfg);
    if (ret < 0) {
        LOG_ERR("Failed to configure DMIC (%d)", ret);
        mic_active = false; // Signal failure
        return;
    }

    while (mic_active) {
        // Start capture for one block
        ret = dmic_trigger(dmic_dev, DMIC_TRIGGER_START);
        if (ret < 0) {
            LOG_ERR("DMIC START trigger failed (%d)", ret);
            // Consider stopping or retrying
            k_sleep(K_MSEC(100)); // Avoid busy-looping on error
            continue;
        }

        // Read one block
        ret = dmic_read(dmic_dev, 0, &buffer, &size, TIMEOUT_MS); // Use int32_t timeout
        if (ret < 0) {
            LOG_ERR("DMIC read failed (%d)", ret);
            // Need to stop PDM first before continuing or breaking
            dmic_trigger(dmic_dev, DMIC_TRIGGER_STOP); // Attempt to stop PDM
            k_sleep(K_MSEC(100)); // Avoid busy-looping on error
            buffer = NULL; // Ensure buffer is NULL if read failed
            continue;
        }

        LOG_INF("Read %u bytes", size);

        // Stop capture after reading the block
        // Consider DMIC_TRIGGER_PAUSE if continuous capture is desired
        ret = dmic_trigger(dmic_dev, DMIC_TRIGGER_STOP);
        if (ret < 0) {
            LOG_WRN("DMIC STOP trigger failed (%d)", ret);
            // Continue processing the buffer anyway?
        }

        // Process buffer if callback exists
        if (_callback && buffer && size > 0) {
            _callback((int16_t *)buffer); // Pass the buffer to the handler
        }

        // Free the buffer back to the slab
        if (buffer) {
            k_mem_slab_free(&dmic_mem_slab, buffer);
            buffer = NULL;
        }
    }

    // Thread exiting, ensure PDM is stopped
    LOG_INF("Mic read thread stopping");
    ret = dmic_trigger(dmic_dev, DMIC_TRIGGER_STOP);
    if (ret < 0) {
        LOG_WRN("Final DMIC STOP trigger failed (%d)", ret);
    }
}

// --- Updated mic_start ---
int mic_start()
{
    if (!mic_active) {
        mic_on(); // Ensure power is on

        // Start the reading thread
        mic_active = true;
        mic_tid = k_thread_create(&mic_thread_data, mic_stack_area,
                                 K_THREAD_STACK_SIZEOF(mic_stack_area),
                                 mic_read_thread,
                                 NULL, NULL, NULL,
                                 CONFIG_MIC_THREAD_PRIORITY, 0, K_NO_WAIT);
        if (!mic_tid) {
            LOG_ERR("Failed to create mic thread");
            mic_off(); // Turn off power if thread failed
            mic_active = false;
            return -1;
        }
        k_thread_name_set(mic_tid, "mic_read");
        LOG_INF("Microphone started");
    } else {
        LOG_WRN("Microphone already started");
    }
    return 0;
}

// --- New mic_stop function ---
int mic_stop()
{
    if (mic_active) {
        mic_active = false; // Signal thread to stop
        if (mic_tid) {
            int ret = k_thread_join(mic_tid, K_MSEC(TIMEOUT_MS + 500)); // Wait for thread to finish
            if (ret) {
                 LOG_WRN("Mic thread join failed (%d)", ret);
                 // Consider k_thread_abort if necessary, but it's risky
            }
            mic_tid = NULL;
        }
        mic_off(); // Turn mic power off
        LOG_INF("Microphone stopped");
    } else {
         LOG_WRN("Microphone already stopped");
    }
    return 0;
}


// --- Added mic_init ---
int mic_init(void)
{
    int ret = 0;

    // Check device readiness
    if (!device_is_ready(dmic_dev)) {
        LOG_ERR("DMIC device %s not ready", dmic_dev->name);
        return -ENODEV;
    }

    // Set channel map dynamically
    drv_cfg.channel.req_chan_map_lo = dmic_build_channel_map(0, 0, PDM_CHAN_LEFT);

    // Configure GPIOs initially (set to off state)
    ret = mic_power_off(); // Use the refactored power off function
    if (ret < 0) {
        LOG_ERR("Failed to configure mic power GPIOs during init (%d)", ret);
        // Continue? Or return error? Returning error for now.
        return ret;
    }

    LOG_INF("Microphone initialized");
    return 0;
}


void set_mic_callback(mix_handler callback)
{
    _callback = callback;
}

// --- Updated mic_off/mic_on for new GPIOs ---
void mic_off()
{
    // Using logic from sample's mic_power_off
    int ret;
    ret = gpio_pin_configure_dt(&mic_thsel, GPIO_OUTPUT);
    if (ret < 0) LOG_ERR("Failed configure thsel (%d)", ret);
	ret = gpio_pin_set_dt(&mic_thsel, 0);
    if (ret < 0) LOG_ERR("Failed set thsel (%d)", ret);

	ret = gpio_pin_configure_dt(&mic_wake, GPIO_INPUT);
    if (ret < 0) LOG_ERR("Failed configure wake (%d)", ret);

	ret = gpio_pin_configure_dt(&mic_en, GPIO_OUTPUT);
    if (ret < 0) LOG_ERR("Failed configure en (%d)", ret);
	ret = gpio_pin_set_dt(&mic_en, 0);
    if (ret < 0) LOG_ERR("Failed set en (%d)", ret);

    LOG_INF("Mic powered off");
}


void mic_on()
{
    // Using logic from sample's mic_power_on
    int ret;
    ret = gpio_pin_configure_dt(&mic_thsel, GPIO_OUTPUT);
    if (ret < 0) LOG_ERR("Failed configure thsel (%d)", ret);
	ret = gpio_pin_set_dt(&mic_thsel, 1);
    if (ret < 0) LOG_ERR("Failed set thsel (%d)", ret);

	ret = gpio_pin_configure_dt(&mic_wake, GPIO_INPUT);
    if (ret < 0) LOG_ERR("Failed configure wake (%d)", ret);

	ret = gpio_pin_configure_dt(&mic_en, GPIO_OUTPUT);
    if (ret < 0) LOG_ERR("Failed configure en (%d)", ret);
	ret = gpio_pin_set_dt(&mic_en, 1);
    if (ret < 0) LOG_ERR("Failed set en (%d)", ret);

    // Small delay for power stabilization (optional, adjust if needed)
    k_sleep(K_MSEC(5));
    LOG_INF("Mic powered on");
}
