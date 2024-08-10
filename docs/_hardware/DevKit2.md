---
layout: default
title: Omi DevKit 2
nav_order: 2
---

## Introduction

DevKit 2 builds on top of and expands the DevKit1 capabilities, while keeping the necklace form factor. It still runs on Xiao nRF52840, but adds 8GB onboard storage, and a speaker, and replaces the on/off switch with a programmable button. This enables the device to listen in standalone mode, although you still need to connect it to the Friend app for processing.

You can see the new device [announcement on X](https://twitter.com/kodjima33/status/1821324066651041837).

## How to get it

### Assembled Device

You can order assembled [Friend DevKit 2](https://basedhardware.com/products/friend-dev-kit-2) from the Based Hardware website.

### Parts

If you prefer to assemble the device yourself, here's the list of the parts you need:

- **[Seeed Studio XIAO nRF52840 Sense](https://www.seeedstudio.com/Seeed-XIAO-nRF52840-Sense-p-5331.html)**
- **[Adafruit 5769 Audio BFF Add-On for QT Py](https://www.adafruit.com/product/5769)**
- **[OWS-091630W50A-8 Speaker (8Ω, 1W, Top Port, 95dB)](https://www.digikey.com/en/products/detail/ole-wolff-electronics-inc/OWS-091630W50A-8/17636881)**
- **[502030 250mAh LiPo Battery](https://www.amazon.com/EEMB-Rechargeable-Connector-Parrott-Polarity/dp/B0B7R8CS2C)**
- **[4x4x1.5 SMD Button](https://www.amazon.com/4x4x1-5mm-Momentary-Tactile-Button-Switch/dp/B00FZLECO4)**
- **Micro SD Card (any)**

#### Circuit Diagram

![Circuit diagram](https://github.com/BasedHardware/Omi/blob/main/Friend/hardware/triangle%20v2%20w%20memory/circuit.png)

#### Assembly Notes

- The speaker connector on the 5769 board should be unsoldered/removed with clippers.
- Speaker connection polarity doesn't matter.
- **ETC:** To be updated.

### Firmware

The firmware for the DevKit 2 is under development. You can use the DevKit 1 firmware for now, but it will not take advantage of the new hardware features.