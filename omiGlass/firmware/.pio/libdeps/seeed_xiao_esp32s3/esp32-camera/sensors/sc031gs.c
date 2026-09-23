/*
 * SC031GS driver.
 * 
 * Copyright 2022-2023 Espressif Systems (Shanghai) PTE LTD
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

#include "sc031gs.h"
#include "sc031gs_settings.h"

#if defined(ARDUINO_ARCH_ESP32) && defined(CONFIG_ARDUHAL_ESP_LOG)
#include "esp32-hal-log.h"
#else
#include "esp_log.h"
static const char* TAG = "sc031gs";
#endif

#define SC031GS_PID_LOW_REG           0x3107
#define SC031GS_PID_HIGH_REG          0x3108
#define SC031GS_MAX_FRAME_WIDTH       (640)
#define SC031GS_MAX_FRAME_HIGH        (480)
#define SC031GS_GAIN_CTRL_COARSE_REG  0x3e08
#define SC031GS_GAIN_CTRL_FINE_REG    0x3e09

#define SC031GS_PIDH_MAGIC 0x00 // High byte of sensor ID
#define SC031GS_PIDL_MAGIC 0x31 // Low byte of sensor ID

static int get_reg(sensor_t *sensor, int reg, int mask)
{
    int ret = SCCB_Read16(sensor->slv_addr, reg & 0xFFFF);
    if(ret > 0){
        ret &= mask;
    }
    return ret;
}

static int set_reg(sensor_t *sensor, int reg, int mask, int value)
{
    int ret = 0;
    ret = SCCB_Read16(sensor->slv_addr, reg & 0xFFFF);
    if(ret < 0){
        return ret;
    }
    value = (ret & ~mask) | (value & mask);
    ret = SCCB_Write16(sensor->slv_addr, reg & 0xFFFF, value);
    return ret;
}

static int set_reg_bits(sensor_t *sensor, uint16_t reg, uint8_t offset, uint8_t length, uint8_t value)
{
    int ret = 0;
    ret = SCCB_Read16(sensor->slv_addr, reg);
    if(ret < 0){
        return ret;
    }
    uint8_t mask = ((1 << length) - 1) << offset;
    value = (ret & ~mask) | ((value << offset) & mask);
    ret = SCCB_Write16(sensor->slv_addr, reg, value);
    return ret;
}

static int write_regs(uint8_t slv_addr, const struct sc031gs_regval *regs)
{
    int i = 0, ret = 0;
    while (!ret && regs[i].addr != REG_NULL) {
        if (regs[i].addr == REG_DELAY) {
            vTaskDelay(regs[i].val / portTICK_PERIOD_MS);
        } else {
            ret = SCCB_Write16(slv_addr, regs[i].addr, regs[i].val);
        }
        i++;
    }
    return ret;
}

#define WRITE_REGS_OR_RETURN(regs) ret = write_regs(slv_addr, regs); if(ret){return ret;}
#define WRITE_REG_OR_RETURN(reg, val) ret = set_reg(sensor, reg, 0xFF, val); if(ret){return ret;}
#define SET_REG_BITS_OR_RETURN(reg, offset, length, val) ret = set_reg_bits(sensor, reg, offset, length, val); if(ret){return ret;}

static int set_hmirror(sensor_t *sensor, int enable)
{
    int ret = 0;
    if(enable) {
        SET_REG_BITS_OR_RETURN(0x3221, 1, 2, 0x3); // mirror on
    } else {
        SET_REG_BITS_OR_RETURN(0x3221, 1, 2, 0x0); // mirror off
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
    SET_REG_BITS_OR_RETURN(0x4501, 3, 1, enable & 0x01); // enable test pattern mode
    SET_REG_BITS_OR_RETURN(0x3902, 6, 1, 1); // enable auto BLC, disable auto BLC if set to 0
    SET_REG_BITS_OR_RETURN(0x3e06, 0, 2, 3); // digital gain: 00->1x, 01->2x, 03->4x.
    return ret;
}

static int set_special_effect(sensor_t *sensor, int sleep_mode_enable) // For sc03ags sensor, This API used for sensor sleep mode control.
{
    // Add some others special control in this API, use switch to control different funcs, such as ctrl_id.
    int ret = 0;
    SET_REG_BITS_OR_RETURN(0x0100, 0, 1, !(sleep_mode_enable & 0x01)); // 0: enable sleep mode. In sleep mode, the registers can be accessed.
    return ret;
}

int set_bpc(sensor_t *sensor, int enable) // // For sc03ags sensor, This API used to control BLC
{
    int ret = 0;
    SET_REG_BITS_OR_RETURN(0x3900, 0, 1, enable & 0x01);
    SET_REG_BITS_OR_RETURN(0x3902, 6, 1, enable & 0x01);
    return ret;
}

static int set_agc_gain(sensor_t *sensor, int gain)
{
    // sc031gs doesn't support AGC, use this func to control.
    int ret = 0;
    uint32_t coarse_gain, fine_gain, fine_again_reg_v, coarse_gain_reg_v;

    if (gain < 0x20) {
        WRITE_REG_OR_RETURN(0x3314, 0x3a);
        WRITE_REG_OR_RETURN(0x3317, 0x20);
    } else {
        WRITE_REG_OR_RETURN(0x3314, 0x44);
        WRITE_REG_OR_RETURN(0x3317, 0x0f);
    }

    if (gain < 0x20) { /*1x ~ 2x*/
        fine_gain = gain - 16;
        coarse_gain = 0x03;
        fine_again_reg_v = ((0x01 << 4) & 0x10) |
            (fine_gain & 0x0f);
        coarse_gain_reg_v = coarse_gain  & 0x1F;
    } else if (gain < 0x40) { /*2x ~ 4x*/
        fine_gain = (gain >> 1) - 16;
        coarse_gain = 0x7;
        fine_again_reg_v = ((0x01 << 4) & 0x10) |
            (fine_gain & 0x0f);
        coarse_gain_reg_v = coarse_gain  & 0x1F;
    } else if (gain < 0x80) { /*4x ~ 8x*/
        fine_gain = (gain >> 2) - 16;
        coarse_gain = 0xf;
        fine_again_reg_v = ((0x01 << 4) & 0x10) |
            (fine_gain & 0x0f);
        coarse_gain_reg_v = coarse_gain  & 0x1F;
    } else { /*8x ~ 16x*/
        fine_gain = (gain >> 3) - 16;
        coarse_gain = 0x1f;
        fine_again_reg_v = ((0x01 << 4) & 0x10) |
            (fine_gain & 0x0f);
        coarse_gain_reg_v = coarse_gain  & 0x1F;
    }

    WRITE_REG_OR_RETURN(SC031GS_GAIN_CTRL_COARSE_REG, coarse_gain_reg_v);
    WRITE_REG_OR_RETURN(SC031GS_GAIN_CTRL_FINE_REG, fine_again_reg_v);
    
    return ret;
}

static int set_aec_value(sensor_t *sensor, int value)
{
    // For now, HDR is disabled, the sensor work in normal mode.
    int ret = 0;
    WRITE_REG_OR_RETURN(0x3e01, value & 0xFF); // AE target high
    WRITE_REG_OR_RETURN(0x3e02, (value >> 8) & 0xFF); // AE target low

    return ret;
}

static int reset(sensor_t *sensor)
{
    int ret = write_regs(sensor->slv_addr, sc031gs_default_init_regs);
    if (ret) {
        ESP_LOGE(TAG, "reset fail");
    }
    // printf("reg 0x3d04=%02x\r\n", get_reg(sensor, 0x3d04, 0xff));
    // set_colorbar(sensor, 1);
    return ret;
}

static int set_output_window(sensor_t *sensor, int offset_x, int offset_y, int w, int h)
{
    int ret = 0;
    //sc:H_start={0x3212[1:0],0x3213},H_length={0x3208[1:0],0x3209},
    // printf("%d, %d, %d, %d\r\n", ((offset_x>>8) & 0x03), offset_x & 0xff, ((w>>8) & 0x03), w & 0xff);

    WRITE_REG_OR_RETURN(SC031GS_OUTPUT_WINDOW_START_X_H_REG, 0x0); // For now, we use x_start is 0x04
    WRITE_REG_OR_RETURN(SC031GS_OUTPUT_WINDOW_START_X_L_REG, 0x04);
    WRITE_REG_OR_RETURN(SC031GS_OUTPUT_WINDOW_WIDTH_H_REG, ((w>>8) & 0x03));
    WRITE_REG_OR_RETURN(SC031GS_OUTPUT_WINDOW_WIDTH_L_REG, w & 0xff);

    //sc:V_start={0x3210[1:0],0x3211},V_length={0x320a[1:0],0x320b},
    // printf("%d, %d, %d, %d\r\n", ((offset_y>>8) & 0x03), offset_y & 0xff, ((h>>8) & 0x03), h & 0xff);
    WRITE_REG_OR_RETURN(SC031GS_OUTPUT_WINDOW_START_Y_H_REG, 0x0); // For now, we use y_start is 0x08
    WRITE_REG_OR_RETURN(SC031GS_OUTPUT_WINDOW_START_Y_L_REG, 0x08);
    WRITE_REG_OR_RETURN(SC031GS_OUTPUT_WINDOW_HIGH_H_REG, ((h>>8) & 0x03));
    WRITE_REG_OR_RETURN(SC031GS_OUTPUT_WINDOW_HIGH_L_REG, h & 0xff);

    vTaskDelay(10 / portTICK_PERIOD_MS);

    return ret;
}

static int set_framesize(sensor_t *sensor, framesize_t framesize)
{
    uint16_t w = resolution[framesize].width;
    uint16_t h = resolution[framesize].height;
    if(w > SC031GS_MAX_FRAME_WIDTH || h > SC031GS_MAX_FRAME_HIGH) {
        goto err; 
    }

    if(w != 200 || h != 200) {
        ESP_LOGE(TAG, "Only support 200*200 for now, contact us if you want to use other resolutions");
        goto err; 
    }

    uint16_t offset_x = (640-w) /2 + 4;   
    uint16_t offset_y = (480-h) /2 + 4;
    
    if(set_output_window(sensor, offset_x, offset_y, w, h)) {
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
    case PIXFORMAT_GRAYSCALE:
    break;
    default:
        ESP_LOGE(TAG, "Only support GRAYSCALE(Y8)");
        return -1;
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

int sc031gs_detect(int slv_addr, sensor_id_t *id)
{
    if (SC031GS_SCCB_ADDR == slv_addr) {
        uint8_t MIDL = SCCB_Read16(slv_addr, SC031GS_PID_HIGH_REG);
        uint8_t MIDH = SCCB_Read16(slv_addr, SC031GS_PID_LOW_REG);
        uint16_t PID = MIDH << 8 | MIDL;
        if (SC031GS_PID == PID) {
            id->PID = PID;
            return PID;
        } else {
            ESP_LOGI(TAG, "Mismatch PID=0x%x", PID);
        }
    }
    return 0;
}

int sc031gs_init(sensor_t *sensor)
{
    // Set function pointers
    sensor->reset = reset;
    sensor->init_status = init_status;
    sensor->set_pixformat = set_pixformat;
    sensor->set_framesize = set_framesize;
    
    sensor->set_colorbar = set_colorbar;
    sensor->set_hmirror = set_hmirror;
    sensor->set_vflip = set_vflip;
    sensor->set_agc_gain = set_agc_gain;
    sensor->set_aec_value = set_aec_value;
    sensor->set_special_effect = set_special_effect;
    
    //not supported
    sensor->set_awb_gain = set_dummy;
    sensor->set_contrast = set_dummy;
    sensor->set_sharpness = set_dummy;
    sensor->set_saturation= set_dummy;
    sensor->set_denoise = set_dummy;
    sensor->set_quality = set_dummy;
    sensor->set_special_effect = set_dummy;
    sensor->set_wb_mode = set_dummy;
    sensor->set_ae_level = set_dummy;
    
    sensor->get_reg = get_reg;
    sensor->set_reg = set_reg;
    sensor->set_xclk = set_xclk;
    
    ESP_LOGD(TAG, "sc031gs Attached");

    return 0;
}