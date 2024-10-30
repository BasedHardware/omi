#include <zephyr/pm/pm.h>
// #include <zephyr/usb/usb_device.h>
// #include <zephyr/drivers/usb/usb_dc.h>
// #include <zephyr/drivers/usb/device/usb_dc_nrfx.c>
#include <zephyr/logging/log.h>
#include <zephyr/usb/usb_device.h>
#include "usb.h"
#include "button.h"
#include "speaker.h"
#include "transport.h"
LOG_MODULE_REGISTER(usb, CONFIG_LOG_DEFAULT_LEVEL);
//add all device drivers here?
bool usb_charge = false;
extern bool is_off;
usb_dc_status_callback udc_status_cb(enum usb_dc_status_code status,
                         const uint8_t *param)
{
    switch (status)
    {
        case USB_DC_CONNECTED:
            usb_charge = true;
            break;
        case USB_DC_DISCONNECTED:
        if (is_off)
        {
            bt_off();
            turnoff_all();
        }
            usb_charge = false;
            break;
        default:
            usb_charge = true;
    }
    return;
    
}



int init_usb()
{
    usb_disable();
    int ret = usb_enable(udc_status_cb);
    printk("USB ret: %d\n", ret);
    return 0;
}
