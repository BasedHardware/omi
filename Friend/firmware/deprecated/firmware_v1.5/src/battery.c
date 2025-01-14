#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/bluetooth/services/bas.h>
#include "battery.h"
#include "utils.h"
#include "transport.h"

#define GPIO_BATTERY_CHARGING_STATUS 17
#define GPIO_BATTERY_CHARGE_SPEED 13
#define GPIO_BATTERY_READ_ENABLE 14

// ADC
static const struct device *adc_battery_dev = DEVICE_DT_GET(DT_NODELABEL(adc));
#define ADC_TOTAL_SAMPLES 10 // Change this to a higher number for better averages
int16_t sample_buffer[ADC_TOTAL_SAMPLES];
#define ADC_RESOLUTION 12
#define ADC_CHANNEL 7
#define ADC_PORT SAADC_CH_PSELP_PSELP_AnalogInput7 // AIN7
#define ADC_REFERENCE ADC_REF_INTERNAL             // 0.6V
#define ADC_GAIN ADC_GAIN_1_6                      // ADC REFERENCE * 6 = 3.6V
struct adc_channel_cfg channel_7_cfg = {
    .gain = ADC_GAIN,
    .reference = ADC_REFERENCE,
    .acquisition_time = ADC_ACQ_TIME_DEFAULT,
    .channel_id = ADC_CHANNEL,
    .input_positive = ADC_PORT};
static struct adc_sequence_options options = {
    .extra_samplings = ADC_TOTAL_SAMPLES - 1,
    .interval_us = 500, // Interval between each sample
};
struct adc_sequence sequence = {
    .options = &options,
    .channels = BIT(ADC_CHANNEL),
    .buffer = sample_buffer,
    .buffer_size = sizeof(sample_buffer),
    .resolution = ADC_RESOLUTION,
};

// Battery spec
typedef struct
{
    uint16_t voltage;
    uint8_t percentage;
} BatteryState;
#define BATTERY_STATES_COUNT 12
BatteryState battery_states[BATTERY_STATES_COUNT] = {
    {4185, 100},
    {4165, 99},
    {4090, 91},
    {4030, 78},
    {3890, 63},
    {3830, 53},
    {3680, 36},
    {3660, 35},
    {3480, 14},
    {3420, 11},
    {3150, 1}, // 3240
    {0000, 0}  // Below safe level
};

// Implementation

bool read_battery_charging()
{
    return gpio_pin_get(gpio0_port, GPIO_BATTERY_CHARGING_STATUS) == 1;
}

int read_battery_voltage()
{

    // Voltage divider circuit (Should tune R1 in software if possible)
    const uint16_t R1 = 1037; // Originally 1M ohm, calibrated after measuring actual voltage values. Can happen due to resistor tolerances, temperature ect..
    const uint16_t R2 = 510;  // 510K ohm

    // We need to stop charging to get a reading
    bool was_charging = read_battery_charging();
    if (was_charging)
    {
        ASSERT_OK(gpio_pin_configure(gpio0_port, GPIO_BATTERY_CHARGE_SPEED, GPIO_OUTPUT | GPIO_ACTIVE_HIGH));
        ASSERT_OK(gpio_pin_set(gpio0_port, GPIO_BATTERY_CHARGE_SPEED, 1));
    }

    // Read ADC
    ASSERT_OK(adc_read(adc_battery_dev, &sequence));

    // Average samples
    int adc_mv = 0;
    for (uint8_t sample = 0; sample < ADC_TOTAL_SAMPLES; sample++)
    {
        adc_mv += sample_buffer[sample]; // ADC value, not millivolt yet.
    }
    adc_mv /= ADC_TOTAL_SAMPLES;

    // Convert to millivolts
    uint16_t adc_vref = adc_ref_internal(adc_battery_dev);
    ASSERT_OK(adc_raw_to_millivolts(adc_vref, ADC_GAIN, ADC_RESOLUTION, &adc_mv));

    int output = adc_mv * ((R1 + R2) / R2);

    // Enable 50ma charging
    if (was_charging)
    {
        ASSERT_OK(gpio_pin_configure(gpio0_port, GPIO_BATTERY_CHARGE_SPEED, GPIO_INPUT));
    }

    return output;
}

int battery_milivolt_to_percent(uint16_t battery_millivolt)
{

    // Ensure voltage is within bounds
    if (battery_millivolt > battery_states[0].voltage)
        return 100;
    if (battery_millivolt < battery_states[BATTERY_STATES_COUNT - 1].voltage)
        return 0;

    for (uint16_t i = 0; i < BATTERY_STATES_COUNT - 1; i++)
    {
        // Find the two points battery_millivolt is between
        if (battery_states[i].voltage >= battery_millivolt && battery_millivolt >= battery_states[i + 1].voltage)
        {
            // Linear interpolation
            return battery_states[i].percentage +
                   ((float)(battery_millivolt - battery_states[i].voltage) *
                    ((float)(battery_states[i + 1].percentage - battery_states[i].percentage) /
                     (float)(battery_states[i + 1].voltage - battery_states[i].voltage)));
        }
    }

    return -ESPIPE;
}

//
// Worker
//

bool battery_status_charge = false;
int battery_voltage = 0;
int battery_percentage = 0;
int voltage_counter = 0;
void refresh_worker(struct k_work *work);
K_WORK_DELAYABLE_DEFINE(refresh_work, refresh_worker);

void refresh_worker(struct k_work *work)
{
    // Update battery status
    battery_status_charge = read_battery_charging();

    // Update battery voltage every 10 seconds
    if (voltage_counter % 10 == 0)
    {
        battery_voltage = read_battery_voltage();
        battery_percentage = battery_milivolt_to_percent(battery_voltage);
        set_bt_batterylevel(battery_percentage);
        voltage_counter = 0;
    }
    voltage_counter++;

    // Submit the work item again with a delay
    k_work_reschedule(&refresh_work, K_MSEC(1000)); // Delay of 1 second
}

//
// Public
//

int battery_start()
{

    // Configure ADC
    ASSERT_TRUE(device_is_ready(adc_battery_dev));
    ASSERT_OK(adc_channel_setup(adc_battery_dev, &channel_7_cfg));

    // Configure GPIO pins
    ASSERT_OK(gpio_pin_configure(gpio0_port, GPIO_BATTERY_CHARGING_STATUS, GPIO_INPUT | GPIO_ACTIVE_LOW | GPIO_PULL_UP));
    ASSERT_OK(gpio_pin_configure(gpio0_port, GPIO_BATTERY_READ_ENABLE, GPIO_OUTPUT | GPIO_ACTIVE_LOW));

    // ALlow batterty readings
    ASSERT_OK(gpio_pin_set(gpio0_port, GPIO_BATTERY_READ_ENABLE, 1));

    // Set 50ma charge current
    ASSERT_OK(gpio_pin_configure(gpio0_port, GPIO_BATTERY_CHARGE_SPEED, GPIO_INPUT));

    // Load init state
    battery_status_charge = read_battery_charging();
    battery_voltage = read_battery_voltage();
    battery_percentage = battery_milivolt_to_percent(battery_voltage);
    set_bt_batterylevel(battery_percentage);

    // Start worker
    k_work_schedule(&refresh_work, K_MSEC(1000));

    return 0;
}

bool is_battery_charging()
{
    return battery_status_charge;
}

int get_battery_voltage()
{
    return battery_voltage;
}

int get_battery_percentage()
{
    return battery_percentage;
}