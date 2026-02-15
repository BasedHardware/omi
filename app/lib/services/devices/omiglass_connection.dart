import 'dart:async';
import 'dart:typed_data';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/logger.dart';
import 'package:version/version.dart';

/// OTA Update Status for OmiGlass
class OmiGlassOtaStatus {
  final int statusCode;
  final int progress;

  OmiGlassOtaStatus(this.statusCode, this.progress);

  bool get isIdle => statusCode == otaStatusIdle;
  bool get isWifiConnecting => statusCode == otaStatusWifiConnecting;
  bool get isWifiConnected => statusCode == otaStatusWifiConnected;
  bool get isWifiFailed => statusCode == otaStatusWifiFailed;
  bool get isDownloading => statusCode == otaStatusDownloading;
  bool get isDownloadComplete => statusCode == otaStatusDownloadComplete;
  bool get isDownloadFailed => statusCode == otaStatusDownloadFailed;
  bool get isInstalling => statusCode == otaStatusInstalling;
  bool get isInstallComplete => statusCode == otaStatusInstallComplete;
  bool get isInstallFailed => statusCode == otaStatusInstallFailed;
  bool get isRebooting => statusCode == otaStatusRebooting;
  bool get isError => statusCode == otaStatusError;

  bool get isInProgress => isWifiConnecting || isWifiConnected || isDownloading || isInstalling;

  bool get isSuccess => isInstallComplete || isRebooting;

  bool get isFailed => isWifiFailed || isDownloadFailed || isInstallFailed || isError;

  String get statusMessage {
    switch (statusCode) {
      case otaStatusIdle:
        return 'Ready';
      case otaStatusWifiConnecting:
        return 'Connecting to WiFi...';
      case otaStatusWifiConnected:
        return 'WiFi connected';
      case otaStatusWifiFailed:
        return 'WiFi connection failed';
      case otaStatusDownloading:
        return 'Downloading firmware ($progress%)';
      case otaStatusDownloadComplete:
        return 'Download complete';
      case otaStatusDownloadFailed:
        return 'Download failed';
      case otaStatusInstalling:
        return 'Installing firmware ($progress%)';
      case otaStatusInstallComplete:
        return 'Installation complete';
      case otaStatusInstallFailed:
        return 'Installation failed';
      case otaStatusRebooting:
        return 'Rebooting device...';
      case otaStatusError:
        return 'Error occurred';
      default:
        return 'Unknown status: $statusCode';
    }
  }
}

/// Connection class for OmiGlass devices with OTA support
class OmiGlassConnection extends DeviceConnection {
  OmiGlassConnection(super.device, super.transport);

  StreamSubscription? _otaStatusSubscription;

  @override
  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
  }) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged);
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    try {
      final data = await transport.readCharacteristic(
        batteryServiceUuid,
        batteryLevelCharacteristicUuid,
      );
      if (data.isNotEmpty) return data[0];
      return -1;
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error reading battery level: $e');
      return -1;
    }
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(
        batteryServiceUuid,
        batteryLevelCharacteristicUuid,
      );

      final subscription = stream.listen((value) {
        if (value.isNotEmpty && onBatteryLevelChange != null) {
          Logger.debug('OmiGlass Battery level changed: ${value[0]}');
          onBatteryLevelChange(value[0]);
        }
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error setting up battery listener: $e');
      return null;
    }
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(
        omiServiceUuid,
        audioDataStreamCharacteristicUuid,
      );

      final subscription = stream.listen((value) {
        if (value.isNotEmpty) {
          onAudioBytesReceived(value);
        }
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error setting up audio listener: $e');
      return null;
    }
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    try {
      final codecData = await transport.readCharacteristic(
        omiServiceUuid,
        audioCodecCharacteristicUuid,
      );
      if (codecData.isNotEmpty) {
        final codecId = codecData[0];
        switch (codecId) {
          case 1:
            return BleAudioCodec.pcm8;
          case 20:
            return BleAudioCodec.opus;
          case 21:
            return BleAudioCodec.opusFS320;
          default:
            return BleAudioCodec.opus;
        }
      }
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error reading audio codec: $e');
    }
    return BleAudioCodec.opus;
  }

  // ==========================================================================
  // Device Info Methods
  // ==========================================================================

  Future<Map<String, dynamic>> getDeviceInfo() async {
    Map<String, dynamic> deviceInfo = {};
    try {
      try {
        final modelValue = await transport.readCharacteristic(
          deviceInformationServiceUuid,
          modelNumberCharacteristicUuid,
        );
        if (modelValue.isNotEmpty) {
          deviceInfo['modelNumber'] = String.fromCharCodes(modelValue);
        }
      } catch (e) {
        Logger.debug('OmiGlassConnection: Error reading model number: $e');
      }

      try {
        final firmwareValue = await transport.readCharacteristic(
          deviceInformationServiceUuid,
          firmwareRevisionCharacteristicUuid,
        );
        if (firmwareValue.isNotEmpty) {
          deviceInfo['firmwareRevision'] = String.fromCharCodes(firmwareValue);
        }
      } catch (e) {
        Logger.debug('OmiGlassConnection: Error reading firmware revision: $e');
      }

      try {
        final hardwareValue = await transport.readCharacteristic(
          deviceInformationServiceUuid,
          hardwareRevisionCharacteristicUuid,
        );
        if (hardwareValue.isNotEmpty) {
          deviceInfo['hardwareRevision'] = String.fromCharCodes(hardwareValue);
        }
      } catch (e) {
        Logger.debug('OmiGlassConnection: Error reading hardware revision: $e');
      }

      try {
        final manufacturerValue = await transport.readCharacteristic(
          deviceInformationServiceUuid,
          manufacturerNameCharacteristicUuid,
        );
        if (manufacturerValue.isNotEmpty) {
          deviceInfo['manufacturerName'] = String.fromCharCodes(manufacturerValue);
        }
      } catch (e) {
        Logger.debug('OmiGlassConnection: Error reading manufacturer name: $e');
      }

      try {
        final serialValue = await transport.readCharacteristic(
          deviceInformationServiceUuid,
          serialNumberCharacteristicUuid,
        );
        if (serialValue.isNotEmpty) {
          deviceInfo['serialNumber'] = String.fromCharCodes(serialValue);
        }
      } catch (e) {
        Logger.debug('OmiGlassConnection: Error reading serial number: $e');
      }
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error getting device info: $e');
    }

    deviceInfo['modelNumber'] ??= 'OMI Glass';
    deviceInfo['manufacturerName'] ??= 'Based Hardware';

    return deviceInfo;
  }

  // ==========================================================================
  // OTA Update Methods
  // ==========================================================================

  /// Check if device supports OTA updates
  Future<bool> isOtaSupported() async {
    try {
      // Try to read from OTA control characteristic
      await transport.readCharacteristic(
        omiGlassOtaServiceUuid,
        omiGlassOtaControlCharacteristicUuid,
      );
      return true;
    } catch (e) {
      Logger.debug('OmiGlassConnection: OTA not supported - $e');
      return false;
    }
  }

  /// Set WiFi credentials for OTA update
  Future<bool> setOtaWifiCredentials(String ssid, String password) async {
    try {
      if (ssid.isEmpty || ssid.length > 32) {
        Logger.debug('OmiGlassConnection: Invalid SSID length: ${ssid.length}');
        return false;
      }
      if (password.isEmpty || password.length > 64) {
        Logger.debug('OmiGlassConnection: Invalid password length: ${password.length}');
        return false;
      }

      final List<int> command = [];
      command.add(otaCmdSetWifi);

      // Add SSID
      final ssidBytes = ssid.codeUnits;
      command.add(ssidBytes.length);
      command.addAll(ssidBytes);

      // Add password
      final passwordBytes = password.codeUnits;
      command.add(passwordBytes.length);
      command.addAll(passwordBytes);

      await transport.writeCharacteristic(
        omiGlassOtaServiceUuid,
        omiGlassOtaControlCharacteristicUuid,
        command,
      );

      Logger.debug('OmiGlassConnection: WiFi credentials set for SSID: $ssid');
      return true;
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error setting WiFi credentials: $e');
      return false;
    }
  }

  /// Set firmware URL for OTA update
  Future<bool> setOtaFirmwareUrl(String url) async {
    try {
      if (url.isEmpty || url.length > 256) {
        Logger.debug('OmiGlassConnection: Invalid URL length');
        return false;
      }

      final List<int> command = [];
      command.add(otaCmdSetUrl);

      // URL length as 2 bytes (big-endian)
      final urlBytes = url.codeUnits;
      command.add((urlBytes.length >> 8) & 0xFF);
      command.add(urlBytes.length & 0xFF);
      command.addAll(urlBytes);

      await transport.writeCharacteristic(
        omiGlassOtaServiceUuid,
        omiGlassOtaControlCharacteristicUuid,
        command,
      );

      Logger.debug('OmiGlassConnection: Firmware URL set: $url');
      return true;
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error setting firmware URL: $e');
      return false;
    }
  }

  /// Start OTA update process
  Future<bool> startOtaUpdate() async {
    try {
      await transport.writeCharacteristic(
        omiGlassOtaServiceUuid,
        omiGlassOtaControlCharacteristicUuid,
        [otaCmdStartOta],
      );

      Logger.debug('OmiGlassConnection: OTA update started');
      return true;
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error starting OTA update: $e');
      return false;
    }
  }

  /// Cancel ongoing OTA update
  Future<bool> cancelOtaUpdate() async {
    try {
      await transport.writeCharacteristic(
        omiGlassOtaServiceUuid,
        omiGlassOtaControlCharacteristicUuid,
        [otaCmdCancelOta],
      );

      Logger.debug('OmiGlassConnection: OTA update cancelled');
      return true;
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error cancelling OTA update: $e');
      return false;
    }
  }

  /// Get current OTA status
  Future<OmiGlassOtaStatus?> getOtaStatus() async {
    try {
      final data = await transport.readCharacteristic(
        omiGlassOtaServiceUuid,
        omiGlassOtaControlCharacteristicUuid,
      );

      if (data.length >= 2) {
        return OmiGlassOtaStatus(data[0], data[1]);
      } else if (data.isNotEmpty) {
        return OmiGlassOtaStatus(data[0], 0);
      }
      return null;
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error getting OTA status: $e');
      return null;
    }
  }

  /// Subscribe to OTA status updates
  Future<StreamSubscription?> subscribeToOtaStatus({
    required void Function(OmiGlassOtaStatus status) onStatusReceived,
    void Function()? onStreamEnded,
    void Function(dynamic error)? onStreamError,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(
        omiGlassOtaServiceUuid,
        omiGlassOtaDataCharacteristicUuid,
      );

      _otaStatusSubscription = stream.listen(
        (value) {
          if (value.isNotEmpty) {
            final status = OmiGlassOtaStatus(
              value[0],
              value.length > 1 ? value[1] : 0,
            );
            Logger.debug('OmiGlassConnection: OTA status update: ${status.statusMessage}');
            onStatusReceived(status);
          }
        },
        onError: (error) {
          Logger.debug('OmiGlassConnection: OTA status stream error: $error');
          onStreamError?.call(error);
        },
        onDone: () {
          Logger.debug('OmiGlassConnection: OTA status stream ended');
          onStreamEnded?.call();
        },
        cancelOnError: false,
      );

      return _otaStatusSubscription;
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error subscribing to OTA status: $e');
      return null;
    }
  }

  /// Perform full OTA update with WiFi credentials and firmware URL
  Future<bool> performOtaUpdate({
    required String ssid,
    required String password,
    required String firmwareUrl,
    void Function(OmiGlassOtaStatus status)? onStatusUpdate,
    void Function()? onConnectionLost,
  }) async {
    try {
      // Step 1: Set WiFi credentials
      if (!await setOtaWifiCredentials(ssid, password)) {
        Logger.debug('OmiGlassConnection: Failed to set WiFi credentials');
        return false;
      }

      // Small delay to allow device to process
      await Future.delayed(const Duration(milliseconds: 200));

      // Step 2: Set firmware URL
      if (!await setOtaFirmwareUrl(firmwareUrl)) {
        Logger.debug('OmiGlassConnection: Failed to set firmware URL');
        return false;
      }

      // Small delay
      await Future.delayed(const Duration(milliseconds: 200));

      // Step 3: Subscribe to status updates if callback provided
      if (onStatusUpdate != null) {
        await subscribeToOtaStatus(
          onStatusReceived: onStatusUpdate,
          onStreamEnded: onConnectionLost,
          onStreamError: (_) => onConnectionLost?.call(),
        );
      }

      // Step 4: Start OTA update
      if (!await startOtaUpdate()) {
        Logger.debug('OmiGlassConnection: Failed to start OTA update');
        return false;
      }

      return true;
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error performing OTA update: $e');
      return false;
    }
  }

  @override
  Future<void> disconnect() async {
    await _otaStatusSubscription?.cancel();
    _otaStatusSubscription = null;
    await super.disconnect();
  }

  // ==========================================================================
  // Image Stream Methods (OmiGlass has camera)
  // ==========================================================================

  Future<StreamSubscription?> performGetBleImageBytesListener({
    required void Function(List<int>) onImageBytesReceived,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(
        omiServiceUuid,
        imageDataStreamCharacteristicUuid,
      );

      final subscription = stream.listen((value) {
        if (value.isNotEmpty) {
          onImageBytesReceived(value);
        }
      });

      return subscription;
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error setting up image listener: $e');
      return null;
    }
  }

  // ==========================================================================
  // Abstract Method Implementations (stubs for unsupported features)
  // ==========================================================================

  @override
  Future<List<int>> performGetButtonState() async => [];

  @override
  Future<StreamSubscription?> performGetBleButtonListener({
    required void Function(List<int>) onButtonReceived,
  }) async =>
      null;

  @override
  Future<bool> performIsWifiSyncSupported() async => false;

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    // OmiGlass doesn't support storage streaming
    return null;
  }

  @override
  Future performCameraStartPhotoController() async {
    // OmiGlass camera control - could be implemented if needed
    try {
      await transport.writeCharacteristic(
        omiServiceUuid,
        imageCaptureControlCharacteristicUuid,
        [0x05], // Start interval capture (5 = minimum accepted by firmware, range 5-300)
      );
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error starting photo controller: $e');
    }
  }

  @override
  Future performCameraStopPhotoController() async {
    // OmiGlass camera control - could be implemented if needed
    try {
      await transport.writeCharacteristic(
        omiServiceUuid,
        imageCaptureControlCharacteristicUuid,
        [0x00], // Stop capture command
      );
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error stopping photo controller: $e');
    }
  }

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() async {
    // OmiGlass has camera capability
    try {
      await transport.readCharacteristic(
        omiServiceUuid,
        imageDataStreamCharacteristicUuid,
      );
      return true;
    } catch (e) {
      return false;
    }
  }

  @override
  Future<StreamSubscription?> performGetImageListener({
    required void Function(OrientedImage orientedImage) onImageReceived,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(
        omiServiceUuid,
        imageDataStreamCharacteristicUuid,
      );

      var buffer = BytesBuilder();
      var nextExpectedFrame = 0;
      var isTransferring = false;
      ImageOrientation? currentOrientation;

      // Firmware version check for orientation byte support
      Version newFirmwareVersion = Version.parse("2.1.1");
      Version deviceFirmwareVersion;
      try {
        deviceFirmwareVersion = Version.parse(device.firmwareRevision);
      } catch (e) {
        deviceFirmwareVersion = Version(0, 0, 0);
      }

      return stream.listen((value) {
        if (value.length < 2) return;

        Uint8List chunk = Uint8List.fromList(value);
        int frameIndex = chunk[0] | (chunk[1] << 8);

        // End of image marker 0xFFFF
        if (frameIndex == 0xFFFF) {
          if (isTransferring) {
            final imageBytes = buffer.toBytes();
            if (imageBytes.isNotEmpty) {
              Logger.debug('OmiGlass: Completed image bytes length: ${imageBytes.length}');
              try {
                onImageReceived(OrientedImage(
                  imageBytes: imageBytes,
                  orientation: currentOrientation ?? ImageOrientation.orientation0,
                ));
              } catch (e) {
                Logger.debug('OmiGlass: Error processing image: $e');
              }
            }
          }
          buffer.clear();
          isTransferring = false;
          nextExpectedFrame = 0;
          currentOrientation = null;
          return;
        }

        // Frame 0 starts a new image
        if (frameIndex == 0) {
          buffer.clear();
          isTransferring = true;
          nextExpectedFrame = 0;
          currentOrientation = null;
        }

        if (!isTransferring) {
          Logger.debug('OmiGlass: Ignoring packet with frame $frameIndex, waiting for frame 0.');
          return;
        }

        if (frameIndex == nextExpectedFrame) {
          if (frameIndex == 0) {
            if (deviceFirmwareVersion >= newFirmwareVersion) {
              // New firmware: parse orientation from packet
              // First chunk: [frame_lo, frame_hi, orientation, ...jpeg_data...]
              if (chunk.length > 2) {
                currentOrientation = ImageOrientation.fromValue(chunk[2]);
                if (chunk.length > 3) {
                  buffer.add(chunk.sublist(3));
                }
              } else {
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
            // Subsequent chunks: [frame_lo, frame_hi, ...jpeg_data...]
            if (chunk.length > 2) {
              buffer.add(chunk.sublist(2));
            }
          }
          nextExpectedFrame++;
        } else {
          Logger.debug('OmiGlass: Frame out of order. Expected $nextExpectedFrame, got $frameIndex. Discarding.');
          buffer.clear();
          isTransferring = false;
          nextExpectedFrame = 0;
          currentOrientation = null;
        }

        // Safety limit
        if (buffer.length > 200 * 1024) {
          Logger.debug('OmiGlass: Buffer exceeded 200KB. Resetting.');
          buffer.clear();
          isTransferring = false;
          nextExpectedFrame = 0;
          currentOrientation = null;
        }
      });
    } catch (e) {
      Logger.debug('OmiGlassConnection: Error setting up image listener: $e');
      return null;
    }
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  }) async {
    // OmiGlass doesn't have accelerometer
    return null;
  }

  @override
  Future<int> performGetFeatures() async {
    // OmiGlass features - battery and camera
    return OmiFeatures.battery;
  }

  @override
  Future<void> performSetLedDimRatio(int ratio) async {
    // OmiGlass doesn't support LED dimming through app
  }

  @override
  Future<int?> performGetLedDimRatio() async {
    // OmiGlass doesn't support LED dimming through app
    return null;
  }

  @override
  Future<void> performSetMicGain(int gain) async {
    // OmiGlass doesn't support mic gain adjustment through app
  }

  @override
  Future<int?> performGetMicGain() async {
    // OmiGlass doesn't support mic gain adjustment through app
    return null;
  }
}
