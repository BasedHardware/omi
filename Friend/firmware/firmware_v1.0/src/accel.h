#include <zephyr/drivers/sensor.h>
typedef struct sensors
{
    struct sensor_value a_x;
    struct sensor_value a_y;
    struct sensor_value a_z;
    struct sensor_value g_x;
    struct sensor_value g_y;
    struct sensor_value g_z;
};

int accel_start();
void accel_on();
void accel_off();
struct sensors *accel_read();
