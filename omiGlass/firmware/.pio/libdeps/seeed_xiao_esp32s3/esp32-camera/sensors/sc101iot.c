/*
 * SC101IOT driver.
 * 
 * Copyright 2020-2022 Espressif Systems (Shanghai) PTE LTD
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at

 *     http://www.apache.org/licenses/LICENSE-2.0
 * 
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "sccb.h"
#include "xclk.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "sc101iot.h"
#include "sc101iot_settings.h"

#if defined(ARDUINO_ARCH_ESP32) && defined(CONFIG_ARDUHAL_ESP_LOG)
#include "esp32-hal-log.h"
#else
#include "esp_log.h"
static const char* TAG = "sc101";
#endif

#define SC101_SENSOR_ID_HIGH_REG    0XF7
#define SC101_SENSOR_ID_LOW_REG     0XF8
#define SC101_MAX_FRAME_WIDTH       (1280)
#define SC101_MAX_FRAME_HIGH        (720)

// sc101 use "i2c paging mode", so the high byte of the register needs to be written to the 0xf0 reg.
// For more information please refer to the Technical Reference Manual.
static int get_reg(sensor_t *sensor, int reg, int mask)
{
    int ret = 0;
    uint8_t reg_high = (reg>>8) & 0xFF;
    uint8_t reg_low = reg & 0xFF;

    if(SCCB_Write(sensor->slv_addr, 0xf0, reg_high)) {
        return -1;
    }

    ret = SCCB_Read(sensor->slv_addr, reg_low);
    if(ret > 0){
        ret &= mask;
    }
    return ret;
}

// sc101 use "i2c paging mode", so the high byte of the register needs to be written to the 0xf0 reg.
// For more information please refer to the Technical Reference Manual.
static int set_reg(sensor_t *sensor, int reg, int mask, int value)
{
    int ret = 0;
    uint8_t reg_high = (reg>>8) & 0xFF;
    uint8_t reg_low = reg & 0xFF;

    if(SCCB_Write(sensor->slv_addr, 0xf0, reg_high)) {
        return -1;
    }
    
    ret = SCCB_Write(sensor->slv_addr, reg_low, value & 0xFF);
    return ret;
}

static int set_regs(sensor_t *sensor, const uint8_t (*regs)[2], uint32_t regs_entry_len)
{
    int i=0, res = 0;
    while (i<regs_entry_len) {
        res = SCCB_Write(sensor->slv_addr, regs[i][0], regs[i][1]);
        if (res) {
            return res;
        }
        i++;
    }
    return res;
}

static int set_reg_bits(sensor_t *sensor, int reg, uint8_t offset, uint8_t length, uint8_t value)
{
    int ret = 0;
    ret = get_reg(sensor, reg, 0xff);
    if(ret < 0){
        return ret;
    }
    uint8_t mask = ((1 << length) - 1) << offset;
    value = (ret & ~mask) | ((value << offset) & mask);
    ret = set_reg(sensor, reg & 0xFFFF, 0xFFFF, value);
    return ret;
}

#define WRITE_REGS_OR_RETURN(regs, regs_entry_len) ret = set_regs(sensor, regs, regs_entry_len); if(ret){return ret;}
#define WRITE_REG_OR_RETURN(reg, val) ret = set_reg(sensor, reg, 0xFF, val); if(ret){return ret;}
#define SET_REG_BITS_OR_RETURN(reg, offset, length, val) ret = set_reg_bits(sensor, reg, offset, length, val); if(ret){return ret;}

static int set_hmirror(sensor_t *sensor, int enable)
{
    int ret = 0;
    if(enable) {
        SET_REG_BITS_OR_RETURN(0x3221, 1, 2, 0x3); // enable mirror
    } else {
        SET_REG_BITS_OR_RETURN(0x3221, 1, 2, 0x0); // disable mirror
    }

    return ret;
}

static int set_vflip(sensor_t *sensor, int enable)
{
    int ret = 0;
    if(enable) {
        SET_REG_BITS_OR_RETURN(0x3221, 5, 2, 0x3); // flip on
    } else {
        SET_REG_BITS_OR_RETURN(0x3221, 5, 2, 0x0); // flip off
    }

    return ret;
}

static int set_colorbar(sensor_t *sensor, int enable)
{
    int ret = 0;
    SET_REG_BITS_OR_RETURN(0x0100, 7, 1, enable & 0xff); // enable colorbar mode
    return ret;
}

static int set_raw_gma(sensor_t *sensor, int enable)
{
    int ret = 0;
    SET_REG_BITS_OR_RETURN(0x00f5, 1, 1, enable & 0xff); // enable gamma compensation

    return ret;
}

static int set_sharpness(sensor_t *sensor, int level)
{
    int ret = 0;
    SET_REG_BITS_OR_RETURN(0x00e0, 1, 1, 1); // enable edge enhancement
    WRITE_REG_OR_RETURN(0x00d0, level & 0xFF); // base value
    WRITE_REG_OR_RETURN(0x00d2, (level >> 8) & 0xFF); // limit

    return ret;
}

static int set_agc_gain(sensor_t *sensor, int gain)
{
    int ret = 0;
    SET_REG_BITS_OR_RETURN(0x0070, 1, 1, 1); // enable auto agc control
    WRITE_REG_OR_RETURN(0x0068, gain & 0xFF); // Window weight setting1
    WRITE_REG_OR_RETURN(0x0069, (gain >> 8) & 0xFF); // Window weight setting2
    WRITE_REG_OR_RETURN(0x006a, (gain >> 16) & 0xFF); // Window weight setting3
    WRITE_REG_OR_RETURN(0x006b, (gain >> 24) & 0xFF); // Window weight setting4
    
    return ret;
}

static int set_aec_value(sensor_t *sensor, int value)
{
    int ret = 0;
    SET_REG_BITS_OR_RETURN(0x0070, 0, 1, 1); // enable auto aec control
    WRITE_REG_OR_RETURN(0x0072, value & 0xFF); // AE target

    return ret;
}

static int set_awb_gain(sensor_t *sensor, int value)
{
    int ret = 0;
    SET_REG_BITS_OR_RETURN(0x00b0, 0, 1, 1); // enable awb control
    WRITE_REG_OR_RETURN(0x00c8, value & 0xFF); // blue gain
    WRITE_REG_OR_RETURN(0x00c9, (value>>8) & 0XFF); // red gain
    return ret;
}

static int set_saturation(sensor_t *sensor, int level)
{
    int ret = 0;
    SET_REG_BITS_OR_RETURN(0x00f5, 5, 1, 0); // enable saturation control
    WRITE_REG_OR_RETURN(0x0149, level & 0xFF); // blue saturation gain (/128)
    WRITE_REG_OR_RETURN(0x014a, (level>>8) & 0XFF); // red saturation gain (/128)
    return ret;
}

static int set_contrast(sensor_t *sensor, int level)
{
    int ret = 0;
    SET_REG_BITS_OR_RETURN(0x00f5, 6, 1, 0); // enable contrast control
    WRITE_REG_OR_RETURN(0x014b, level); // contrast coefficient(/64)
    return ret;
}

static int reset(sensor_t *sensor)
{
    int ret = set_regs(sensor, sc101iot_default_init_regs, sizeof(sc101iot_default_init_regs)/(sizeof(uint8_t) * 2));
    
    // Delay
    vTaskDelay(50 / portTICK_PERIOD_MS);

    // ESP_LOGI(TAG, "set_reg=%0x", set_reg(sensor, 0x0100, 0xffff, 0x00)); // write 0x80 to enter test mode if you want to test the sensor
    // ESP_LOGI(TAG, "0x0100=%0x", get_reg(sensor, 0x0100, 0xffff));
    if (ret) {
        ESP_LOGE(TAG, "reset fail");
    }
    return ret;
}

static int set_window(sensor_t *sensor, int offset_x, int offset_y, int w, int h)
{
    int ret = 0;
    //sc:H_start={0x0172[3:0],0x0170},H_end={0x0172[7:4],0x0171},
    WRITE_REG_OR_RETURN(0x0170, offset_x & 0xff);
    WRITE_REG_OR_RETURN(0x0171, (offset_x+w) & 0xff);
    WRITE_REG_OR_RETURN(0x0172, ((offset_x>>8) & 0x0f) | (((offset_x+w)>>4)&0xf0));

    //sc:V_start={0x0175[3:0],0x0173},H_end={0x0175[7:4],0x0174},
    WRITE_REG_OR_RETURN(0x0173, offset_y & 0xff);
    WRITE_REG_OR_RETURN(0x0174, (offset_y+h) & 0xff);
    WRITE_REG_OR_RETURN(0x0175, ((offset_y>>8) & 0x0f) | (((offset_y+h)>>4)&0xf0));

    vTaskDelay(10 / portTICK_PERIOD_MS);

    return ret;
}

static int set_framesize(sensor_t *sensor, framesize_t framesize)
{
    uint16_t w = resolution[framesize].width;
    uint16_t h = resolution[framesize].height;
    if(w>SC101_MAX_FRAME_WIDTH || h > SC101_MAX_FRAME_HIGH) {
        goto err; 
    }

    uint16_t offset_x = (SC101_MAX_FRAME_WIDTH-w) /2;   
    uint16_t offset_y = (SC101_MAX_FRAME_HIGH-h) /2;
    
    if(set_window(sensor, offset_x, offset_y, w, h)) {
        goto err; 
    }
    
    sensor->status.framesize = framesize;
    return 0;
err:
    ESP_LOGE(TAG, "frame size err");
    return -1;
}

static int set_pixformat(sensor_t *sensor, pixformat_t pixformat)
{
    int ret=0;
    sensor->pixformat = pixformat;

    switch (pixformat) {
    case PIXFORMAT_RGB565:
    case PIXFORMAT_RAW:
    case PIXFORMAT_GRAYSCALE:
        ESP_LOGE(TAG, "Not support");
        break;
    case PIXFORMAT_YUV422: // For now, sc101 sensor only support YUV422.
        break;
    default:
        ret = -1;
    }

    return ret;
}

static int init_status(sensor_t *sensor)
{
    return 0;
}

static int set_dummy(sensor_t *sensor, int val){ return -1; }

static int set_xclk(sensor_t *sensor, int timer, int xclk)
{
    int ret = 0;
    sensor->xclk_freq_hz = xclk * 1000000U;
    ret = xclk_timer_conf(timer, sensor->xclk_freq_hz);
    return ret;
}

int sc101iot_detect(int slv_addr, sensor_id_t *id)
{
    if (SC101IOT_SCCB_ADDR == slv_addr) {
        uint8_t MIDL = SCCB_Read(slv_addr, SC101_SENSOR_ID_LOW_REG);
        uint8_t MIDH = SCCB_Read(slv_addr, SC101_SENSOR_ID_HIGH_REG);
        uint16_t PID = MIDH << 8 | MIDL;
        if (SC101IOT_PID == PID) {
            id->PID = PID;
            return PID;
        } else {
            ESP_LOGI(TAG, "Mismatch PID=0x%x", PID);
        }
    }
    return 0;
}

int sc101iot_init(sensor_t *sensor)
{
    // Set function pointers
    sensor->reset = reset;
    sensor->init_status = init_status;
    sensor->set_pixformat = set_pixformat;
    sensor->set_framesize = set_framesize;
    sensor->set_hmirror = set_hmirror;
    sensor->set_vflip = set_vflip;
    sensor->set_colorbar = set_colorbar;
    sensor->set_raw_gma = set_raw_gma;
    sensor->set_sharpness = set_sharpness;
    sensor->set_agc_gain = set_agc_gain;
    sensor->set_aec_value = set_aec_value;
    sensor->set_awb_gain = set_awb_gain;
    sensor->set_saturation= set_saturation;
    sensor->set_contrast = set_contrast;

    sensor->set_denoise = set_dummy;
    sensor->set_quality = set_dummy;
    sensor->set_special_effect = set_dummy;
    sensor->set_wb_mode = set_dummy;
    sensor->set_ae_level = set_dummy;


    sensor->get_reg = get_reg;
    sensor->set_reg = set_reg;
    sensor->set_xclk = set_xclk;
    
    ESP_LOGD(TAG, "sc101iot Attached");

    return 0;
}