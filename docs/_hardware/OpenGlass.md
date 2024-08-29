---
layout: default
title: OpenGlass DevKit
nav_order: 3
---

## Introduction

OpenGlass DevKit is a small clip-on device you can attach to your glasses. It runs on Xiao ESp32S3 Sense platform, and features camera and microphone. The device also has a slot for an SD card, which is currently not utilized.

OpenGlass takes continuous photos and records audio, and sends the data to the app for processing. It expands the memories with pictures, and allows you to capture every moment, remember important people, and understand the world around you. The device is designed to be used with the same Friend companion app as the rest of the devices.

You can see a demo of the first OpenGlass prototype in action [here](https://youtu.be/DsM_-c2e1ew).

## How to get it

### Assembled Device

Currently, the OpenGlass DevKit is not available for purchase. You can find the list of the parts and the 3D printed case in the OpenGlass section of the [Omi repository](https://github.com/BasedHardware/Omi/tree/main/OpenGlass) and assemble the device yourself.

### Parts

If you prefer to assemble the device yourself, here's the list of the parts you need:

[Seeed Studio XIAO ESP32 S3 Sense](https://www.amazon.com/dp/B0C69FFVHH/ref=dp_iou_view_item?ie=UTF8&psc=1)
[EEMB LP502030 3.7v 250mAH battery](https://www.amazon.com/EEMB-Battery-Rechargeable-Lithium-Connector/dp/B08VRZTHDL)
[3D printed glasses mount case](https://storage.googleapis.com/scott-misc/openglass_case.stl)

### Firmware

The firmware for the OpenGlass DevKit, and can be found in the Github repository as well. Since it's based on Arduino, you can use the Arduino IDE or CLI to build and flash the firmware to the device.