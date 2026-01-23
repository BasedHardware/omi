import 'dart:async';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';

import 'package:version/version.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/wifi_sync_error.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/logger.dart';

class OmiDeviceConnection extends DeviceConnection {
  static const String settingsServiceUuid = '19b10010-e8f2-537e-4f6c-d104768a1214';
  static const String settingsDimRatioCharacteristicUuid = '19b10011-e8f2-537e-4f6c-d104768a1214';
  static const String settingsMicGainCharacteristicUuid = '19b10012-e8f2-537e-4f6c-d104768a1214';
  static const String featuresServiceUuid = '19b10020-e8f2-537e-4f6c-d104768a1214';
  static const String featuresCharacteristicUuid = '19b10021-e8f2-537e-4f6c-d104768a1214';

  OmiDeviceConnection(super.device, super.transport);

  get deviceId => device.id;

  @override
  Future<void> connect({Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged}) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged);
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    try {
      final data = await transport.readCharacteristic(batteryServiceUuid, batteryLevelCharacteristicUuid);
      if (data.isNotEmpty) return data[0];
      return -1;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error reading battery level: $e');
      return -1;
    }
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(batteryServiceUuid, batteryLevelCharacteristicUuid);

      final subscription = stream.listen((value) {
        if (value.isNotEmpty && onBatteryLevelChange != null) {
          Logger.debug('Battery level changed: ${value[0]}');
          onBatteryLevelChange(value[0]);
        }
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up battery listener: $e');
      return null;
    }
  }

  @override
  Future<List<int>> performGetButtonState() async {
    Logger.debug('perform button state called');
    try {
      return await transport.readCharacteristic(buttonServiceUuid, buttonTriggerCharacteristicUuid);
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error reading button state: $e');
      return <int>[];
    }
  }

  @override
  Future<StreamSubscription?> performGetBleButtonListener({
    required void Function(List<int>) onButtonReceived,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(buttonServiceUuid, buttonTriggerCharacteristicUuid);

      Logger.debug('Subscribed to button stream from Omi Device');
      final subscription = stream.listen((value) {
        Logger.debug("new button value $value");
        if (value.isNotEmpty) onButtonReceived(value);
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up button listener: $e');
      return null;
    }
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(omiServiceUuid, audioDataStreamCharacteristicUuid);

      Logger.debug('Subscribed to audioBytes stream from Omi Device');
      final subscription = stream.listen((value) {
        if (value.isNotEmpty) onAudioBytesReceived(value);
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up audio listener: $e');
      return null;
    }
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    try {
      final codecValue = await transport.readCharacteristic(omiServiceUuid, audioCodecCharacteristicUuid);

      var codecId = 1;
      if (codecValue.isNotEmpty) {
        codecId = codecValue[0];
      }

      switch (codecId) {
        case 1:
          return BleAudioCodec.pcm8;
        case 20:
          return BleAudioCodec.opus;
        case 21:
          return BleAudioCodec.opusFS320;
        default:
          Logger.debug('OmiDeviceConnection: Unknown codec id: $codecId');
          return BleAudioCodec.pcm8;
      }
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error reading audio codec: $e');
      return BleAudioCodec.pcm8;
    }
  }

  @override
  Future<List<int>> getStorageList() async {
    if (await isConnected()) {
      Logger.debug('storage list called');
      return await performGetStorageList();
    }
    Logger.debug('storage list error');
    return Future.value(<int>[]);
  }

  @override
  Future<List<int>> performGetStorageList() async {
    Logger.debug('perform storage list called');
    try {
      final storageValue =
          await transport.readCharacteristic(storageDataStreamServiceUuid, storageReadControlCharacteristicUuid);

      List<int> storageLengths = [];
      if (storageValue.isNotEmpty) {
        int totalEntries = (storageValue.length / 4).toInt();
        Logger.debug('Storage list: $totalEntries items');

        for (int i = 0; i < totalEntries; i++) {
          int baseIndex = i * 4;
          var result = ((storageValue[baseIndex] |
                      (storageValue[baseIndex + 1] << 8) |
                      (storageValue[baseIndex + 2] << 16) |
                      (storageValue[baseIndex + 3] << 24)) &
                  0xFFFFFFFF)
              .toSigned(32);
          storageLengths.add(result);
        }
      }
      Logger.debug('Storage lengths: ${storageLengths.length} items: ${storageLengths.join(', ')}');
      return storageLengths;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error reading storage list: $e');
      return <int>[];
    }
  }

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    try {
      final stream =
          transport.getCharacteristicStream(storageDataStreamServiceUuid, storageDataStreamCharacteristicUuid);

      final subscription = stream.listen((value) {
        if (value.isNotEmpty) onStorageBytesReceived(value);
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up storage listener: $e');
      return null;
    }
  }

  // level
  //   1 - play 20ms
  //   2 - play 50ms
  //   3 - play 500ms
  @override
  Future<bool> performPlayToSpeakerHaptic(int level) async {
    try {
      Logger.debug('About to play to speaker haptic');
      await transport
          .writeCharacteristic(speakerDataStreamServiceUuid, speakerDataStreamCharacteristicUuid, [level & 0xFF]);
      return true;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error playing haptic: $e');
      return false;
    }
  }

  @override
  Future<bool> performWriteToStorage(int numFile, int command, int offset) async {
    try {
      Logger.debug('About to write to storage bytes');
      Logger.debug('about to send $numFile');
      Logger.debug('about to send $command');
      Logger.debug('about to send offset$offset');

      var offsetBytes = [
        (offset >> 24) & 0xFF,
        (offset >> 16) & 0xFF,
        (offset >> 8) & 0xFF,
        offset & 0xFF,
      ];

      await transport.writeCharacteristic(storageDataStreamServiceUuid, storageDataStreamCharacteristicUuid,
          [command & 0xFF, numFile & 0xFF, offsetBytes[0], offsetBytes[1], offsetBytes[2], offsetBytes[3]]);
      return true;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error writing to storage: $e');
      return false;
    }
  }

  @override
  Future performCameraStartPhotoController() async {
    try {
      // Capture photo once every 5s
      await transport.writeCharacteristic(omiServiceUuid, imageCaptureControlCharacteristicUuid, [0x05]);
      print('cameraStartPhotoController');
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error starting photo capture: $e');
    }
  }

  @override
  Future performCameraStopPhotoController() async {
    try {
      await transport.writeCharacteristic(omiServiceUuid, imageCaptureControlCharacteristicUuid, [0x00]);
      print('cameraStopPhotoController');
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error stopping photo capture: $e');
    }
  }

  Future performCameraTakePhoto() async {
    try {
      // -1 tells the firmware to take a single photo
      await transport.writeCharacteristic(omiServiceUuid, imageCaptureControlCharacteristicUuid, [-1]);
      print('cameraTakePhoto');
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error taking photo: $e');
    }
  }

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() async {
    try {
      // Try to read from the image data stream characteristic to see if it exists
      await transport.readCharacteristic(omiServiceUuid, imageDataStreamCharacteristicUuid);
      return true;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Photo streaming characteristic not available: $e');
      return false;
    }
  }

  Future<StreamSubscription?> _getBleImageBytesListener({
    required void Function(List<int>) onImageBytesReceived,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(omiServiceUuid, imageDataStreamCharacteristicUuid);

      Logger.debug('Subscribed to imageBytes stream from Omi Device');
      final subscription = stream.listen((value) {
        if (value.isNotEmpty) onImageBytesReceived(value);
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up image listener: $e');
      return null;
    }
  }

  @override
  Future<StreamSubscription?> performGetImageListener({
    required void Function(OrientedImage orientedImage) onImageReceived,
  }) async {
    if (!await hasPhotoStreamingCharacteristic()) {
      return null;
    }
    print("OpenGlassDevice getImageListener called");

    var buffer = BytesBuilder();
    var nextExpectedFrame = 0;
    var isTransferring = false;
    ImageOrientation? currentOrientation;

    Version newFirmwareVersion = Version.parse("2.1.1");
    Version deviceFirmwareVersion;
    try {
      deviceFirmwareVersion = Version.parse(device.firmwareRevision);
    } catch (e) {
      deviceFirmwareVersion = Version(0, 0, 0);
    }

    var bleBytesStream = await _getBleImageBytesListener(
      onImageBytesReceived: (List<int> value) async {
        if (value.length < 2) return;

        Uint8List chunk = Uint8List.fromList(value);
        int frameIndex = chunk[0] | (chunk[1] << 8);

        // End of image marker 0xFFFF
        if (frameIndex == 0xFFFF) {
          if (isTransferring) {
            final imageBytes = buffer.toBytes();
            if (imageBytes.isNotEmpty) {
              Logger.debug('Completed image bytes length: ${imageBytes.length}');
              try {
                onImageReceived(OrientedImage(
                  imageBytes: imageBytes,
                  orientation: currentOrientation ?? ImageOrientation.orientation0,
                ));
              } catch (e) {
                Logger.debug('Error processing image: $e');
              }
            }
          }
          // Reset for next image
          buffer.clear();
          isTransferring = false;
          nextExpectedFrame = 0;
          currentOrientation = null;
          return;
        }

        // If we get frame 0, it's the start of a new image. Reset everything.
        if (frameIndex == 0) {
          buffer.clear();
          isTransferring = true;
          nextExpectedFrame = 0;
          currentOrientation = null;
        }

        // If we are not in a transfer state, ignore the packet unless it's frame 0.
        if (!isTransferring) {
          Logger.debug("Ignoring packet with frame $frameIndex, waiting for frame 0 to start transfer.");
          return;
        }

        // Check if the frame is the one we expect.
        if (frameIndex == nextExpectedFrame) {
          if (frameIndex == 0) {
            if (deviceFirmwareVersion >= newFirmwareVersion) {
              // New firmware: parse orientation from packet
              if (chunk.length > 2) {
                currentOrientation = ImageOrientation.fromValue(chunk[2]);
                if (chunk.length > 3) {
                  buffer.add(chunk.sublist(3));
                }
              } else {
                // Malformed packet, default orientation
                currentOrientation = ImageOrientation.orientation0;
              }
            } else {
              // Old firmware: default to 180 degrees and treat whole chunk as data
              currentOrientation = ImageOrientation.orientation180;
              if (chunk.length > 2) {
                buffer.add(chunk.sublist(2));
              }
            }
          } else {
            if (chunk.length > 2) {
              buffer.add(chunk.sublist(2));
            }
          }
          nextExpectedFrame++;
        } else {
          // Out of order frame. The image is now corrupt.
          // We should discard everything and wait for the next frame 0.
          Logger.debug('Frame out of order. Expected $nextExpectedFrame, got $frameIndex. Discarding image.');
          buffer.clear();
          isTransferring = false;
          nextExpectedFrame = 0;
          currentOrientation = null;
        }

        // Safety break for oversized buffer
        if (buffer.length > 200 * 1024) {
          Logger.debug("Buffer size exceeded 200KB without a complete image. Resetting.");
          buffer.clear();
          isTransferring = false;
          nextExpectedFrame = 0;
          currentOrientation = null;
        }
      },
    );
    bleBytesStream?.onDone(() {
      Logger.debug('Image listener done');
      cameraStopPhotoController();
    });
    return bleBytesStream;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(accelDataStreamServiceUuid, accelDataStreamCharacteristicUuid);

      final subscription = stream.listen((value) async {
        if (value.length > 4) {
          //for some reason, the very first reading is four bytes

          if (value.isNotEmpty) {
            List<double> accelerometerData = [];
            onAccelChange?.call(value[0]);

            for (int i = 0; i < 6; i++) {
              int baseIndex = i * 8;
              var result = ((value[baseIndex] |
                          (value[baseIndex + 1] << 8) |
                          (value[baseIndex + 2] << 16) |
                          (value[baseIndex + 3] << 24)) &
                      0xFFFFFFFF)
                  .toSigned(32);
              var temp = ((value[baseIndex + 4] |
                          (value[baseIndex + 5] << 8) |
                          (value[baseIndex + 6] << 16) |
                          (value[baseIndex + 7] << 24)) &
                      0xFFFFFFFF)
                  .toSigned(32);
              double axisValue = result + (temp / 1000000);
              accelerometerData.add(axisValue);
            }
            Logger.debug('Accelerometer x direction: ${accelerometerData[0]}');
            Logger.debug('Gyroscope x direction: ${accelerometerData[3]}\n');

            Logger.debug('Accelerometer y direction: ${accelerometerData[1]}');
            Logger.debug('Gyroscope y direction: ${accelerometerData[4]}\n');

            Logger.debug('Accelerometer z direction: ${accelerometerData[2]}');
            Logger.debug('Gyroscope z direction: ${accelerometerData[5]}\n');
            //simple threshold fall calcaultor
            var fall_number =
                sqrt(pow(accelerometerData[0], 2) + pow(accelerometerData[1], 2) + pow(accelerometerData[2], 2));
            if (fall_number > 30.0) {
              await NotificationUtil.triggerFallNotification();
            }
          }
        }
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up accelerometer listener: $e');
      return null;
    }
  }

  @override
  Future<void> performSetLedDimRatio(int ratio) async {
    try {
      await transport
          .writeCharacteristic(settingsServiceUuid, settingsDimRatioCharacteristicUuid, [ratio.clamp(0, 100)]);
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting LED dim ratio: $e');
    }
  }

  @override
  Future<int?> performGetLedDimRatio() async {
    try {
      final value = await transport.readCharacteristic(settingsServiceUuid, settingsDimRatioCharacteristicUuid);
      if (value.isNotEmpty) {
        return value[0];
      }
      return null;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error getting LED dim ratio: $e');
      return null;
    }
  }

  @override
  Future<int> performGetFeatures() async {
    try {
      final value = await transport.readCharacteristic(featuresServiceUuid, featuresCharacteristicUuid);
      if (value.length >= 4) {
        return ByteData.view(Uint8List.fromList(value).buffer).getUint32(0, Endian.little);
      }
      return 0;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error getting features: $e');
      return 0;
    }
  }

  @override
  Future<void> performSetMicGain(int gain) async {
    try {
      await transport.writeCharacteristic(settingsServiceUuid, settingsMicGainCharacteristicUuid, [gain.clamp(0, 100)]);
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting mic gain: $e');
    }
  }

  @override
  Future<int?> performGetMicGain() async {
    try {
      final value = await transport.readCharacteristic(settingsServiceUuid, settingsMicGainCharacteristicUuid);
      if (value.isNotEmpty) {
        return value[0];
      }
      return null;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error getting mic gain: $e');
      return null;
    }
  }

  /// Get device information from Omi device
  Future<Map<String, String>> getDeviceInfo() async {
    Map<String, String> deviceInfo = {};

    try {
      // Read model number
      try {
        final modelValue =
            await transport.readCharacteristic(deviceInformationServiceUuid, modelNumberCharacteristicUuid);
        if (modelValue.isNotEmpty) {
          deviceInfo['modelNumber'] = String.fromCharCodes(modelValue);
        }
      } catch (e) {
        Logger.debug('OmiDeviceConnection: Error reading model number: $e');
      }

      // Read firmware revision
      try {
        final firmwareValue =
            await transport.readCharacteristic(deviceInformationServiceUuid, firmwareRevisionCharacteristicUuid);
        if (firmwareValue.isNotEmpty) {
          deviceInfo['firmwareRevision'] = String.fromCharCodes(firmwareValue);
        }
      } catch (e) {
        Logger.debug('OmiDeviceConnection: Error reading firmware revision: $e');
      }

      // Read hardware revision
      try {
        final hardwareValue =
            await transport.readCharacteristic(deviceInformationServiceUuid, hardwareRevisionCharacteristicUuid);
        if (hardwareValue.isNotEmpty) {
          deviceInfo['hardwareRevision'] = String.fromCharCodes(hardwareValue);
        }
      } catch (e) {
        Logger.debug('OmiDeviceConnection: Error reading hardware revision: $e');
      }

      // Read manufacturer name
      try {
        final manufacturerValue =
            await transport.readCharacteristic(deviceInformationServiceUuid, manufacturerNameCharacteristicUuid);
        if (manufacturerValue.isNotEmpty) {
          deviceInfo['manufacturerName'] = String.fromCharCodes(manufacturerValue);
        }
      } catch (e) {
        Logger.debug('OmiDeviceConnection: Error reading manufacturer name: $e');
      }

      // Check if device has image streaming capability (for OpenGlass/OmiGlass detection)
      try {
        final chars = await transport.readCharacteristic(omiServiceUuid, imageDataStreamCharacteristicUuid);
        if (chars.isNotEmpty) {
          deviceInfo['hasImageStream'] = 'true';
        }
      } catch (e) {
        deviceInfo['hasImageStream'] = 'false';
      }
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error getting device info: $e');
    }

    // Set defaults if values are empty
    deviceInfo['modelNumber'] ??= 'Omi Device';
    deviceInfo['firmwareRevision'] ??= '1.0.2';
    deviceInfo['hardwareRevision'] ??= 'Seeed Xiao BLE Sense';
    deviceInfo['manufacturerName'] ??= 'Based Hardware';
    deviceInfo['hasImageStream'] ??= 'false';

    return deviceInfo;
  }

  @override
  Future<bool> performIsWifiSyncSupported() async {
    final features = await getFeatures();
    return (features & OmiFeatures.wifi) != 0;
  }

  @override
  Future<WifiSyncSetupResult> performSetupWifiSync(String ssid, String password) async {
    try {
      // Validate SSID length (1-32 characters)
      if (ssid.isEmpty || ssid.length > 32) {
        debugPrint('OmiDeviceConnection: Invalid SSID length: ${ssid.length}');
        return WifiSyncSetupResult.failure(
          WifiSyncErrorCode.ssidLengthInvalid,
          customMessage: 'SSID must be 1-32 characters',
        );
      }

      // Validate password length (8-63 characters for WPA2)
      if (password.isEmpty || password.length < 8 || password.length > 63) {
        debugPrint('OmiDeviceConnection: Invalid password length: ${password.length}');
        return WifiSyncSetupResult.failure(
          WifiSyncErrorCode.passwordLengthInvalid,
          customMessage: 'Password must be 8-63 characters',
        );
      }

      final List<int> command = [];

      command.add(0x01);

      // SSID
      final ssidBytes = ssid.codeUnits;
      command.add(ssidBytes.length);
      command.addAll(ssidBytes);

      // Password
      final passwordBytes = password.codeUnits;
      command.add(passwordBytes.length);
      command.addAll(passwordBytes);

      // Set up listener for the response before sending the command
      final completer = Completer<WifiSyncSetupResult>();
      StreamSubscription? responseSubscription;

      try {
        final stream = transport.getCharacteristicStream(storageDataStreamServiceUuid, storageWifiCharacteristicUuid);

        responseSubscription = stream.listen((value) {
          if (value.isNotEmpty && !completer.isCompleted) {
            final responseCode = value[0];
            final errorCode = WifiSyncErrorCode.fromCode(responseCode);
            if (errorCode.isSuccess) {
              completer.complete(WifiSyncSetupResult.success());
            } else {
              completer.complete(WifiSyncSetupResult.failure(errorCode));
            }
          }
        });

        await Future.delayed(const Duration(milliseconds: 100));

        // Send the setup command
        await transport.writeCharacteristic(storageDataStreamServiceUuid, storageWifiCharacteristicUuid, command);

        // Wait for response with timeout
        final result = await completer.future.timeout(
          const Duration(seconds: 5),
          onTimeout: () => WifiSyncSetupResult.timeout(),
        );

        return result;
      } finally {
        await responseSubscription?.cancel();
      }
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up WiFi sync: $e');
      return WifiSyncSetupResult.connectionFailed();
    }
  }

  @override
  Future<bool> performStartWifiSync() async {
    try {
      // Send WIFI_START command (0x02)
      await transport.writeCharacteristic(storageDataStreamServiceUuid, storageWifiCharacteristicUuid, [0x02]);
      return true;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error starting WiFi sync: $e');
      return false;
    }
  }

  @override
  Future<bool> performStopWifiSync() async {
    try {
      // Send WIFI_SHUTDOWN command (0x03)
      await transport.writeCharacteristic(storageDataStreamServiceUuid, storageWifiCharacteristicUuid, [0x03]);
      return true;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error stopping WiFi sync: $e');
      return false;
    }
  }

  @override
  Future<StreamSubscription?> performGetWifiSyncStatusListener({
    required void Function(int status) onStatusReceived,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(storageDataStreamServiceUuid, storageWifiCharacteristicUuid);

      final subscription = stream.listen((value) {
        if (value.isNotEmpty) {
          final status = value[0];
          onStatusReceived(status);
        }
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiDeviceConnection: Error setting up WiFi status listener: $e');
      return null;
    }
  }
}
