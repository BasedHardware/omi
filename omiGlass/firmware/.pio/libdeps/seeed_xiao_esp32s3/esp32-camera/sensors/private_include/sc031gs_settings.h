// Copyright 2022-2023 Espressif Systems (Shanghai) PTE LTD
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//Preview Type:0:DVP Raw 10 bit// 1:Raw 8 bit// 2:YUV422// 3:RAW16
//Preview Type:4:RGB565// 5:Pixart SPI// 6:MIPI 10bit// 7:MIPI 12bit// 8: MTK SPI
//port  0:MIPI// 1:Parallel// 2:MTK// 3:SPI// 4:TEST// 5: HISPI// 6 : Z2P/Z4P
//I2C Mode    :0:Normal 8Addr,8Data//  1:Samsung 8 Addr,8Data// 2:Micron 8 Addr,16Data
//I2C Mode    :3:Stmicro 16Addr,8Data//4:Micron2 16 Addr,16Data
//Out Format  :0:YCbYCr/RG_GB// 1:YCrYCb/GR_BG// 2:CbYCrY/GB_RG// 3:CrYCbY/BG_GR
//MCLK Speed  :0:6M//1:8M//2:10M//3:11.4M//4:12M//5:12.5M//6:13.5M//7:15M//8:18M//9:24M
//pin  :BIT0 pwdn// BIT1:reset
//avdd  0:2.8V// 1:2.5V// 2:1.8V
//dovdd  0:2.8V// 1:2.5V// 2:1.8V
//dvdd  0:1.8V// 1:1.5V// 2:1.2V

/*
[database]
DBName=Dothinkey

[vendor]
VendorName=SmartSens

[sensor]
SensorName=SC031GS
width=200
height=200
port=1
type=1
pin=2
SlaveID=0x60
mode=3
FlagReg=0x36FF
FlagMask=0xff
FlagData=0x00
FlagReg1=0x36FF
FlagMask1=0xff
FlagData1=0x00
outformat=3
mclk=10
avdd=2.800000
dovdd=2.800000
dvdd=1.500000

Ext0=0
Ext1=0
Ext2=0
AFVCC=2.513000
VPP=0.000000
*/
#include <stdint.h>

#define SC031GS_OUTPUT_WINDOW_START_X_H_REG        0x3212
#define SC031GS_OUTPUT_WINDOW_START_X_L_REG        0x3213
#define SC031GS_OUTPUT_WINDOW_START_Y_H_REG        0x3210
#define SC031GS_OUTPUT_WINDOW_START_Y_L_REG        0x3211
#define SC031GS_OUTPUT_WINDOW_WIDTH_H_REG          0x3208
#define SC031GS_OUTPUT_WINDOW_WIDTH_L_REG          0x3209
#define SC031GS_OUTPUT_WINDOW_HIGH_H_REG           0x320a
#define SC031GS_OUTPUT_WINDOW_HIGH_L_REG           0x320b
#define SC031GS_LED_STROBE_ENABLE_REG              0x3361 // When the camera is in exposure, this PAD LEDSTROBE will be high to drive the external LED.

#define REG_NULL			0xFFFF
#define REG_DELAY           0X0000

struct sc031gs_regval {
	uint16_t addr;
	uint8_t val;
};

// 200*200, xclk=10M, fps=120fps
static const struct sc031gs_regval sc031gs_default_init_regs[] = {
    {0x0103, 0x01}, // soft reset.
	{REG_DELAY, 10}, // delay.
	{0x0100, 0x00},
	{0x36e9, 0x80},
	{0x36f9, 0x80},
	{0x300f, 0x0f},
	{0x3018, 0x1f},
	{0x3019, 0xff},
	{0x301c, 0xb4},
	{0x301f, 0x7b},
	{0x3028, 0x82},
	{0x3200, 0x00},
	{0x3201, 0xdc},
	{0x3202, 0x00},
	{0x3203, 0x98},
	{0x3204, 0x01},
	{0x3205, 0xb3},
	{0x3206, 0x01},
	{0x3207, 0x67},
	{SC031GS_OUTPUT_WINDOW_WIDTH_H_REG, 0x00},
	{SC031GS_OUTPUT_WINDOW_WIDTH_L_REG, 0xc8},
	{SC031GS_OUTPUT_WINDOW_HIGH_H_REG, 0x00},
	{SC031GS_OUTPUT_WINDOW_HIGH_L_REG, 0xc8},
	{0x320c, 0x03},
	{0x320d, 0x6b},
	{0x320e, 0x01}, //default 120fps: {0x320e, 0x01},{0x320f, 0x40}, 58fps: {0x320e, 0x02},{0x320f, 0xab}; 30fps: {0x320e, 0x05}, {0x320f, 0x34}
	{0x320f, 0x40}, 
	{SC031GS_OUTPUT_WINDOW_START_Y_H_REG, 0x00},
	{SC031GS_OUTPUT_WINDOW_START_Y_L_REG, 0x08},
	{SC031GS_OUTPUT_WINDOW_START_X_H_REG, 0x00},
	{SC031GS_OUTPUT_WINDOW_START_X_L_REG, 0x04},
	{0x3220, 0x10},
	{0x3223, 0x50},
	{0x3250, 0xf0},
	{0x3251, 0x02},
	{0x3252, 0x01},
	{0x3253, 0x3b},
	{0x3254, 0x02},
	{0x3255, 0x07},
	{0x3304, 0x48},
	{0x3306, 0x38},
	{0x3309, 0x50},
	{0x330b, 0xe0},
	{0x330c, 0x18},
	{0x330f, 0x20},
	{0x3310, 0x10},
	{0x3314, 0x70},
	{0x3315, 0x38},
	{0x3316, 0x68},
	{0x3317, 0x0d},
	{0x3329, 0x5c},
	{0x332d, 0x5c},
	{0x332f, 0x60},
	{0x3335, 0x64},
	{0x3344, 0x64},
	{0x335b, 0x80},
	{0x335f, 0x80},
	{0x3366, 0x06},
	{0x3385, 0x41},
	{0x3387, 0x49},
	{0x3389, 0x01},
	{0x33b1, 0x03},
	{0x33b2, 0x06},
	{0x3621, 0xa4},
	{0x3622, 0x05},
	{0x3624, 0x47},
	{0x3631, 0x48},
	{0x3633, 0x52},
	{0x3635, 0x18},
	{0x3636, 0x25},
	{0x3637, 0x89},
	{0x3638, 0x0f},
	{0x3639, 0x08},
	{0x363a, 0x00},
	{0x363b, 0x48},
	{0x363c, 0x06},
	{0x363e, 0xf8},
	{0x3640, 0x00},
	{0x3641, 0x01},
	{0x36ea, 0x39},
	{0x36eb, 0x1e},
	{0x36ec, 0x0e},
	{0x36ed, 0x23},
	{0x36fa, 0x39},
	{0x36fb, 0x10},
	{0x36fc, 0x01},
	{0x36fd, 0x03},
	{0x3908, 0x91},
	{0x3d08, 0x01},
	{0x3d04, 0x04},
	{0x3e01, 0x13},
	{0x3e02, 0xa0},
	{0x3e06, 0x0c},
	{0x3f04, 0x03},
	{0x3f05, 0x4b},
	{0x4500, 0x59},
	{0x4501, 0xc4},
	{0x4809, 0x01},
	{0x4837, 0x39},
	{0x5011, 0x00},
	{0x36e9, 0x04},
	{0x36f9, 0x04},
	{0x0100, 0x01},

	//delay 10ms
	{REG_DELAY, 0X0a},
	{0x4418, 0x08},
	{0x4419, 0x80},
	{0x363d, 0x10},
	{0x3630, 0x48},

	// [gain<4] 
	{0x3317, 0x0d},
	{0x3314, 0x70},

	// [gain>=4]
	{0x3314, 0x68},
	{0x3317, 0x0e},
	{REG_NULL, 0x00},
};
