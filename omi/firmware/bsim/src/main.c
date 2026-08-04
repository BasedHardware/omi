#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include "lib/core/settings.h"
#include "lib/core/transport.h"

int main(void)
{
    int err = app_settings_init();
    if (err) {
        printk("OMI_BSIM_FAIL settings %d\n", err);
        return err;
    }

    err = transport_start();
    if (err) {
        printk("OMI_BSIM_FAIL transport %d\n", err);
        return err;
    }

    printk("OMI_BSIM_READY\n");
    return 0;
}
