---
layout: default
title: App-device protocol
nav_order: 1
---

# App-device protocol

## BLE Discovery

The app discovers the device by scanning for BLE devices with the name `Friend`.

## BLE Service and Characteristics

The Friend wearable device implements one BLE service to stream the audio data to the app.

The main service has UUID of `19B10000-E8F2-537E-4F6C-D104768A1214` and has two characteristics:
- Audio data with UUID of `19B10001-E8F2-537E-4F6C-D104768A1214`, used to send the audio data from the device to the app.
- Codec type with UUID of `19B10002-E8F2-537E-4F6C-D104768A1214`, determines what codec should be used to decode the audio data.

### Codec Type

The possible values for the codec type are:
- 0: PCM 16-bit, 16kHz, mono
- 1: PCM 8-bit, 16kHz, mono
- 10: Mu-law 16-bit, 16kHz, mono
- 11: Mu-law 8-bit, 16kHz, mono
- 20: Opus 16-bit, 16kHz, mono

The device default is PCM 8-bit, 16kHz, mono.

### Audio Data

The audio data is sent as updates to the audio characteristic. The format of the data depends on the codec type.
The data is split into packets, with each packet containing 160 samples.
Each packe talso has thrre byte header:
- The first two bytes are the overall packet number, starting from 0.
- The third byte is the index of packet in the current batch of packets.

The data is sent in little-endian format.
