/*
 *
 * SC101IOT DVP driver.
 *
 */
#ifndef __SC101IOT_H__
#define __SC101IOT_H__

#include "sensor.h"

/**
 * @brief Detect sensor pid
 *
 * @param slv_addr SCCB address
 * @param id Detection result
 * @return
 *     0:       Can't detect this sensor
 *     Nonzero: This sensor has been detected
 */
int sc101iot_detect(int slv_addr, sensor_id_t *id);

/**
 * @brief initialize sensor function pointers
 *
 * @param sensor pointer of sensor
 * @return
 *      Always 0
 */
int sc101iot_init(sensor_t *sensor);

#endif // __SC101IOT_H__
