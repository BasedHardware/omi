#ifndef _WDOG_FACADE_H_
#define _WDOG_FACADE_H_

/**
 * @brief Feed (kick) the watchdog to prevent system reset.
 */
void watchdog_feed(void);

/**
 * @brief Initialize the watchdog timer.
 *
 * @return 0 on success, negative error code on failure to initialize.
 */
int watchdog_init(void);

/**
 * @brief Disable the watchdog timer.
 *
 * @return 0 on success, negative error code on failure to initialize.
 */
int watchdog_deinit(void);

#endif /*_WDOG_FACADE_H_*/

