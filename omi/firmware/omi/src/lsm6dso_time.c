#include "lsm6dso_time.h"

#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/util.h>

#include "lib/core/settings.h"
#include "rtc.h"

LOG_MODULE_REGISTER(lsm6dso_time, CONFIG_LOG_DEFAULT_LEVEL);

/* Minimal register access for ST LSM6DS3TR-C/LSM6DSx timestamp.
 *
 * Relevant registers (LSM6DS3TR-C header confirms these addresses):
 * - CTRL10_C = 0x19, timer_en is bit 5 (enables timestamp counter)
 * - WAKE_UP_DUR = 0x5C, timer_hr selects timestamp LSB
 * - TIMESTAMP0 = 0x40, 24-bit little-endian counter (TIMESTAMP0..2)
 */

#define LSM6DS_REG_CTRL10_C         0x19
#define LSM6DS_REG_WAKE_UP_DUR      0x5C
#define LSM6DS_REG_TIMESTAMP0       0x40
#define LSM6DS_REG_WHO_AM_I         0x0F

#define LSM6DS_CTRL10_TIMER_EN      BIT(5)
#define LSM6DS_WAKE_UP_DUR_TIMER_HR BIT(4)

/* LSM6DS3TR-C timestamp resolution:
 * - TIMER_HR = 0: 1 LSB = 6.4 ms (default)
 * - TIMER_HR = 1: 1 LSB = 25 us
 *
 * You said you want 6.4ms mode.
 */
#define LSM6DS_TIMESTAMP_TICK_US_6P4MS 6400ULL

/* Allow sensor time to boot after enabling its power pin. */
#define LSM6DS_POWER_ON_DELAY_MS 50

static int lsm6dso_power_ensure_on(void);

static const struct i2c_dt_spec lsm6dso_i2c = I2C_DT_SPEC_GET(DT_ALIAS(lsm6dso));
#if DT_NODE_HAS_PROP(DT_NODELABEL(lsm6dso_en_pin), gpios)
static const struct gpio_dt_spec lsm6dso_en = GPIO_DT_SPEC_GET(DT_NODELABEL(lsm6dso_en_pin), gpios);
#elif DT_NODE_HAS_PROP(DT_NODELABEL(lsm6dso_en_pin), enable_gpios)
static const struct gpio_dt_spec lsm6dso_en = GPIO_DT_SPEC_GET(DT_NODELABEL(lsm6dso_en_pin), enable_gpios);
#else
static const struct gpio_dt_spec lsm6dso_en = {0};
#endif
static const struct device *const lsm6dso_dev = DEVICE_DT_GET(DT_ALIAS(lsm6dso));

static bool did_i2c_scan;

static void lsm6dso_log_dt_whoami_best_effort(void)
{
	if (lsm6dso_i2c.bus == NULL || !device_is_ready(lsm6dso_i2c.bus)) {
		return;
	}

	uint8_t who = 0;
	int err = i2c_reg_read_byte_dt(&lsm6dso_i2c, LSM6DS_REG_WHO_AM_I, &who);
	if (err == 0) {
		LOG_WRN("DT IMU addr=0x%02x WHO_AM_I=0x%02x", lsm6dso_i2c.addr, who);
	}
}

static void lsm6dso_i2c_scan_bus_once(void)
{
	if (did_i2c_scan) {
		return;
	}
	did_i2c_scan = true;

	if (lsm6dso_i2c.bus == NULL || !device_is_ready(lsm6dso_i2c.bus)) {
		LOG_WRN("I2C scan skipped: bus not ready");
		return;
	}

	LOG_WRN("I2C scan (read WHO_AM_I@0x0F) on bus %s: start", lsm6dso_i2c.bus->name);
	for (uint16_t addr = 0x03; addr <= 0x77; addr++) {
		uint8_t who = 0;
		int err = i2c_reg_read_byte(lsm6dso_i2c.bus, addr, LSM6DS_REG_WHO_AM_I, &who);
		if (err == 0) {
			LOG_WRN("I2C device ACK at 0x%02x, WHO_AM_I=0x%02x", addr, who);
		}
	}
	LOG_WRN("I2C scan: end");
}

static void lsm6dso_i2c_resume_best_effort(void)
{
	if (lsm6dso_i2c.bus == NULL || !device_is_ready(lsm6dso_i2c.bus)) {
		return;
	}

	(void)pm_device_action_run(lsm6dso_i2c.bus, PM_DEVICE_ACTION_RESUME);
}

static void lsm6dso_try_recover_i2c_eio(const char *op)
{
	LOG_WRN("I2C EIO during %s; trying power/bus recovery", op);
	(void)lsm6dso_power_ensure_on();
	lsm6dso_i2c_resume_best_effort();
	k_sleep(K_MSEC(LSM6DS_POWER_ON_DELAY_MS));
	lsm6dso_log_dt_whoami_best_effort();
}

static void lsm6dso_force_minimal_run_mode(void)
{
	if (lsm6dso_dev == NULL || !device_is_ready(lsm6dso_dev)) {
		LOG_DBG("lsm6dso_dev not ready; skip minimal run mode");
		return;
	}

	/* 12.5 Hz = 12 + 0.5 (in micro). */
	struct sensor_value odr = { .val1 = 12, .val2 = 500000 };
	(void)sensor_attr_set(lsm6dso_dev, SENSOR_CHAN_ACCEL_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &odr);

	/* Best-effort attempt to stop gyro to save power. Not all drivers accept 0 Hz. */
	struct sensor_value gyro_odr = { .val1 = 0, .val2 = 0 };
	(void)sensor_attr_set(lsm6dso_dev, SENSOR_CHAN_GYRO_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &gyro_odr);
}

static int lsm6dso_power_ensure_on(void)
{
	if (!device_is_ready(lsm6dso_en.port)) {
		LOG_DBG("lsm6dso_en gpio not ready; assume always-on");
		return 0;
	}

	/* Best-effort: ensure enable pin is configured and driven high. */
	int err = gpio_pin_configure_dt(&lsm6dso_en, GPIO_OUTPUT);
	if (err < 0) {
		LOG_WRN("Failed to configure lsm6dso_en gpio (err %d)", err);
		return err;
	}

	err = gpio_pin_set_dt(&lsm6dso_en, 1);
	if (err < 0) {
		LOG_WRN("Failed to set lsm6dso_en gpio high (err %d)", err);
		return err;
	}

	/* Give IMU time to be ready for I2C transactions. */
	k_sleep(K_MSEC(LSM6DS_POWER_ON_DELAY_MS));
	LOG_INF("lsm6dso_en asserted");

	return 0;
}

static int lsm6dso_timestamp_enable(void)
{
	lsm6dso_i2c_resume_best_effort();
	if (!device_is_ready(lsm6dso_i2c.bus)) {
		LOG_WRN("lsm6dso i2c bus not ready");
		return -ENODEV;
	}

	uint8_t ctrl10;
	int err = i2c_reg_read_byte_dt(&lsm6dso_i2c, LSM6DS_REG_CTRL10_C, &ctrl10);
	if (err) {
		LOG_WRN("Failed to read CTRL10_C (err %d)", err);
		if (err == -EIO) {
			lsm6dso_try_recover_i2c_eio("read CTRL10_C");
			err = i2c_reg_read_byte_dt(&lsm6dso_i2c, LSM6DS_REG_CTRL10_C, &ctrl10);
			if (err) {
				LOG_WRN("Retry read CTRL10_C failed (err %d)", err);
				lsm6dso_i2c_scan_bus_once();
				return err;
			}
		} else {
		return err;
		}
	}

	ctrl10 |= LSM6DS_CTRL10_TIMER_EN;
	err = i2c_reg_write_byte_dt(&lsm6dso_i2c, LSM6DS_REG_CTRL10_C, ctrl10);
	if (err) {
		LOG_WRN("Failed to write CTRL10_C timer_en=1 (err %d)", err);
		if (err == -EIO) {
			lsm6dso_try_recover_i2c_eio("write CTRL10_C");
			err = i2c_reg_write_byte_dt(&lsm6dso_i2c, LSM6DS_REG_CTRL10_C, ctrl10);
			if (err) {
				LOG_WRN("Retry write CTRL10_C failed (err %d)", err);
				return err;
			}
		} else {
		return err;
		}
	}

	LOG_DBG("Timestamp enabled (CTRL10_C=0x%02x)", ctrl10);
	return 0;
}

static int lsm6dso_timestamp_disable(void)
{
	lsm6dso_i2c_resume_best_effort();
	if (!device_is_ready(lsm6dso_i2c.bus)) {
		LOG_WRN("lsm6dso i2c bus not ready");
		return -ENODEV;
	}

	uint8_t ctrl10;
	int err = i2c_reg_read_byte_dt(&lsm6dso_i2c, LSM6DS_REG_CTRL10_C, &ctrl10);
	if (err) {
		LOG_WRN("Failed to read CTRL10_C (err %d)", err);
		if (err == -EIO) {
			lsm6dso_try_recover_i2c_eio("read CTRL10_C (disable)");
			err = i2c_reg_read_byte_dt(&lsm6dso_i2c, LSM6DS_REG_CTRL10_C, &ctrl10);
			if (err) {
				LOG_WRN("Retry read CTRL10_C (disable) failed (err %d)", err);
				lsm6dso_i2c_scan_bus_once();
				return err;
			}
		} else {
		return err;
		}
	}

	ctrl10 &= (uint8_t)~LSM6DS_CTRL10_TIMER_EN;
	err = i2c_reg_write_byte_dt(&lsm6dso_i2c, LSM6DS_REG_CTRL10_C, ctrl10);
	if (err) {
		LOG_WRN("Failed to write CTRL10_C timer_en=0 (err %d)", err);
		if (err == -EIO) {
			lsm6dso_try_recover_i2c_eio("write CTRL10_C (disable)");
			err = i2c_reg_write_byte_dt(&lsm6dso_i2c, LSM6DS_REG_CTRL10_C, ctrl10);
			if (err) {
				LOG_WRN("Retry write CTRL10_C (disable) failed (err %d)", err);
				return err;
			}
		} else {
		return err;
		}
	}

	LOG_DBG("Timestamp disabled (CTRL10_C=0x%02x)", ctrl10);
	return 0;
}

static void lsm6dso_timestamp_restart_best_effort(void)
{
	/* Some LSM6DS variants reset the timestamp counter when timer_en is toggled.
	 * Even if it doesn't reset, we will read and store a matching base_ts.
	 */
	LOG_DBG("Restarting timestamp (toggle timer_en)");
	(void)lsm6dso_timestamp_disable();
	k_sleep(K_MSEC(2));
	(void)lsm6dso_timestamp_enable();
	k_sleep(K_MSEC(2));
}

static int lsm6dso_timestamp_set_resolution_6p4ms(void)
{
	lsm6dso_i2c_resume_best_effort();
	if (!device_is_ready(lsm6dso_i2c.bus)) {
		LOG_WRN("lsm6dso i2c bus not ready");
		return -ENODEV;
	}

	uint8_t wake_up_dur;
	int err = i2c_reg_read_byte_dt(&lsm6dso_i2c, LSM6DS_REG_WAKE_UP_DUR, &wake_up_dur);
	if (err) {
		LOG_WRN("Failed to read WAKE_UP_DUR (err %d)", err);
		if (err == -EIO) {
			lsm6dso_try_recover_i2c_eio("read WAKE_UP_DUR");
			err = i2c_reg_read_byte_dt(&lsm6dso_i2c, LSM6DS_REG_WAKE_UP_DUR, &wake_up_dur);
			if (err) {
				LOG_WRN("Retry read WAKE_UP_DUR failed (err %d)", err);
				lsm6dso_i2c_scan_bus_once();
				return err;
			}
		} else {
		return err;
		}
	}

	/* TIMER_HR=0 => 6.4ms LSB */
	wake_up_dur &= (uint8_t)~LSM6DS_WAKE_UP_DUR_TIMER_HR;
	err = i2c_reg_write_byte_dt(&lsm6dso_i2c, LSM6DS_REG_WAKE_UP_DUR, wake_up_dur);
	if (err) {
		LOG_WRN("Failed to write WAKE_UP_DUR timer_hr=0 (err %d)", err);
		if (err == -EIO) {
			lsm6dso_try_recover_i2c_eio("write WAKE_UP_DUR");
			err = i2c_reg_write_byte_dt(&lsm6dso_i2c, LSM6DS_REG_WAKE_UP_DUR, wake_up_dur);
			if (err) {
				LOG_WRN("Retry write WAKE_UP_DUR failed (err %d)", err);
				return err;
			}
		} else {
		return err;
		}
	}

	LOG_DBG("Timestamp resolution forced to 6.4ms (WAKE_UP_DUR=0x%02x)", wake_up_dur);
	return 0;
}

static int lsm6dso_timestamp_read(uint32_t *ts)
{
	if (ts == NULL) {
		return -EINVAL;
	}
	lsm6dso_i2c_resume_best_effort();
	if (!device_is_ready(lsm6dso_i2c.bus)) {
		LOG_WRN("lsm6dso i2c bus not ready");
		return -ENODEV;
	}

	/* LSM6DS3TR-C exposes a 24-bit timestamp counter (TIMESTAMP0..2). */
	uint8_t buf[3];
	int err = i2c_burst_read_dt(&lsm6dso_i2c, LSM6DS_REG_TIMESTAMP0, buf, sizeof(buf));
	if (err) {
		LOG_WRN("Failed to read TIMESTAMP0..2 (err %d)", err);
		if (err == -EIO) {
			lsm6dso_try_recover_i2c_eio("burst read TIMESTAMP");
			err = i2c_burst_read_dt(&lsm6dso_i2c, LSM6DS_REG_TIMESTAMP0, buf, sizeof(buf));
			if (err) {
				LOG_WRN("Retry read TIMESTAMP0..2 failed (err %d)", err);
				lsm6dso_i2c_scan_bus_once();
				return err;
			}
		} else {
		return err;
		}
	}

	*ts = ((uint32_t)buf[0]) | ((uint32_t)buf[1] << 8) | ((uint32_t)buf[2] << 16);
	return 0;
}

void lsm6dso_time_prepare_for_system_off(void)
{
	/* Requires a valid UTC epoch to be meaningful. */
	if (!rtc_is_valid()) {
		LOG_INF("system_off prep: skip (RTC not valid)");
		return;
	}

	LOG_INF("system_off prep: begin");

	int err = lsm6dso_power_ensure_on();
	if (err) {
		LOG_WRN("system_off prep: IMU power ensure failed (err %d)", err);
	}
	lsm6dso_force_minimal_run_mode();
	err = lsm6dso_timestamp_set_resolution_6p4ms();
	if (err) {
		LOG_WRN("system_off prep: set timestamp res failed (err %d)", err);
	}
	err = lsm6dso_timestamp_enable();
	if (err) {
		LOG_WRN("system_off prep: timestamp enable failed (err %d)", err);
	}
	lsm6dso_timestamp_restart_best_effort();

	uint32_t ts;
	err = lsm6dso_timestamp_read(&ts);
	if (err != 0) {
		LOG_WRN("system_off prep: timestamp read failed (err %d)", err);
		return;
	}
	LOG_INF("system_off prep: imu ts=0x%06x", ts & 0x00FFFFFFu);

	uint64_t epoch_s = (uint64_t)get_utc_time();
	if (epoch_s == 0) {
		LOG_WRN("system_off prep: get_utc_time() returned 0 despite rtc_is_valid");
		return;
	}
	LOG_INF("system_off prep: epoch_s=%llu", epoch_s);

	err = app_settings_save_lsm6dso_time_base(epoch_s, ts);
	if (err) {
		LOG_WRN("system_off prep: failed to save base (err %d)", err);
	} else {
		LOG_INF("system_off prep: saved base OK");
	}
}

int lsm6dso_time_boot_adjust_rtc(void)
{
	uint64_t base_epoch_s;
	uint32_t base_ts;
	int err = app_settings_get_lsm6dso_time_base(&base_epoch_s, &base_ts);
	if (err) {
		LOG_WRN("boot adjust: failed to read saved base (err %d)", err);
		return err;
	}
	if (base_epoch_s == 0) {
		LOG_DBG("boot adjust: no saved base");
		return 0;
	}
	LOG_INF("boot adjust: base_epoch_s=%llu base_ts=0x%06x", base_epoch_s, base_ts & 0x00FFFFFFu);

	err = lsm6dso_power_ensure_on();
	if (err) {
		LOG_WRN("boot adjust: IMU power ensure failed (err %d)", err);
	}
	err = lsm6dso_timestamp_set_resolution_6p4ms();
	if (err) {
		LOG_WRN("boot adjust: set timestamp res failed (err %d)", err);
	}
	err = lsm6dso_timestamp_enable();
	if (err) {
		LOG_WRN("boot adjust: timestamp enable failed (err %d)", err);
	}

	uint32_t ts_now;
	err = lsm6dso_timestamp_read(&ts_now);
	if (err) {
		LOG_WRN("boot adjust: timestamp read failed (err %d)", err);
		return err;
	}
	LOG_INF("boot adjust: ts_now=0x%06x", ts_now & 0x00FFFFFFu);

	/* Unsigned subtraction handles wraparound modulo 2^32. */
	/* Timestamp is 24-bit, so compute delta modulo 2^24 to handle wrap. */
	uint32_t delta_ticks = (ts_now - base_ts) & 0x00FFFFFFu;
	uint64_t delta_us = (uint64_t)delta_ticks * LSM6DS_TIMESTAMP_TICK_US_6P4MS;
	uint64_t delta_ms = delta_us / 1000ULL;
	LOG_INF("boot adjust: delta_ticks=%u delta_ms=%llu", delta_ticks, delta_ms);

	uint64_t new_epoch_ms = (base_epoch_s * 1000ULL) + delta_ms;
	if (new_epoch_ms == 0) {
		return 0;
	}

	err = rtc_set_utc_time_ms(new_epoch_ms);
	if (err) {
		LOG_WRN("boot adjust: rtc_set_utc_time_ms failed (err %d)", err);
		return err;
	}

	/* Clear the base so we don't reapply on every reboot. */
	err = app_settings_save_lsm6dso_time_base(0, 0);
	if (err) {
		LOG_WRN("boot adjust: failed to clear base (err %d)", err);
	}

	LOG_INF("Applied IMU timestamp delta: +%llu ms", delta_ms);
	return 1;
}
