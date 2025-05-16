# Omi Device Connection Documentation

This document outlines the Bluetooth Low Energy (BLE) connection functionality for Omi devices based on the Flutter implementation in `omi_connection.dart`.

## Overview

The Omi connection module provides functionality to connect to Omi devices via Bluetooth Low Energy (BLE), retrieve device information, and interact with various device features such as audio streaming, button events, and more.

## Key Service and Characteristic UUIDs

```
Omi Service UUID: 19b10000-e8f2-537e-4f6c-d104768a1214

Audio Data Stream Characteristic: 19b10001-e8f2-537e-4f6c-d104768a1214
Audio Codec Characteristic: 19b10002-e8f2-537e-4f6c-d104768a1214

Button Service UUID: 23ba7924-0000-1000-7450-346eac492e92
Button Trigger Characteristic: 23ba7925-0000-1000-7450-346eac492e92

Battery Service UUID: 0000180f-0000-1000-8000-00805f9b34fb
Battery Level Characteristic: 00002a19-0000-1000-8000-00805f9b34fb
```

## Core Functions

### Connection Management

- **connect**: Establishes a connection to the Omi device
- **disconnect**: Terminates the connection with the device
- **isConnected**: Checks if the device is currently connected
- **ping**: Sends a ping to the device to check connectivity
- **requestConnectionPriority**: Requests a specific connection priority for better performance or battery efficiency (Android only)

### Audio Functions

- **getAudioCodec**: Retrieves the current audio codec used by the device
- **getBleAudioBytesListener**: Sets up a listener for audio data from the device

### Button Functions

- **getBleButtonState**: Gets the current state of the device buttons
- **getBleButtonListener**: Sets up a listener for button press events

### Battery Functions

- **retrieveBatteryLevel**: Gets the current battery level of the device
- **getBleBatteryLevelListener**: Sets up a listener for battery level changes

## Audio Codecs

The Omi device supports several audio codecs:

- PCM8 (default)
- PCM16
- Opus

## Implementation Notes

1. Always check if the device is connected before attempting to interact with it
2. Handle disconnection events gracefully
3. Clean up listeners when they are no longer needed
4. For Android devices, request a larger MTU size (512) to avoid GATT errors
5. For Android devices, you can use `requestConnectionPriority` to optimize for performance (ConnectionPriority.HIGH) or battery life (ConnectionPriority.LOW_POWER)
# TODO: Check if balanced and low_power provide enough bandwidth to support opus streaming