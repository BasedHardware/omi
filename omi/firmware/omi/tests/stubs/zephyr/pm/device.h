#ifndef Z_STUB_PM_H
#define Z_STUB_PM_H

#include <zephyr/device.h>

enum pm_device_action {
    PM_DEVICE_ACTION_SUSPEND,
    PM_DEVICE_ACTION_RESUME,
};

int pm_device_action_run(const struct device *dev, enum pm_device_action action);

#endif
