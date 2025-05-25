import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/env/env.dart';
import 'package:omi/http/api/device.dart';
import 'package:omi/main.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/omi_connection.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:http/http.dart' as http;
import 'package:omi/utils/logger.dart';
import 'package:http/http.dart' show MediaType;
import 'package:omi/backend/http/shared.dart';

class DeviceProvider extends ChangeNotifier implements IDeviceServiceSubsciption {
  CaptureProvider? captureProvider;

  bool isConnecting = false;
  bool isConnected = false;
  bool isDeviceV2Connected = false;
  BtDevice? connectedDevice;
  BtDevice? pairedDevice;
  StreamSubscription<List<int>>? _bleBatteryLevelListener;
  int batteryLevel = -1;
  bool _hasLowBatteryAlerted = false;
  Timer? _reconnectionTimer;
  DateTime? _reconnectAt;
  final int _connectionCheckSeconds = 7;

  bool _havingNewFirmware = false;
  bool get havingNewFirmware => _havingNewFirmware && pairedDevice != null && isConnected;

  // Current and latest firmware versions for UI display
  String get currentFirmwareVersion => pairedDevice?.firmwareRevision ?? 'Unknown';
  String _latestFirmwareVersion = '';
  String get latestFirmwareVersion => _latestFirmwareVersion;

  Timer? _disconnectNotificationTimer;

  // Image stream listener
  StreamSubscription? _bleImageBytesListener;

  DeviceProvider() {
    ServiceManager.instance().device.subscribe(this, this);
  }

  void setProviders(CaptureProvider provider) {
    captureProvider = provider;
    notifyListeners();
  }

  void setConnectedDevice(BtDevice? device) async {
    connectedDevice = device;
    pairedDevice = device;
    await getDeviceInfo();
    print('setConnectedDevice: $device');
    notifyListeners();
  }

  Future getDeviceInfo() async {
    if (connectedDevice != null) {
      if (pairedDevice?.firmwareRevision != null && pairedDevice?.firmwareRevision != 'Unknown') {
        return;
      }
      var connection = await ServiceManager.instance().device.ensureConnection(connectedDevice!.id);
      pairedDevice = await connectedDevice!.getDeviceInfo(connection);
      SharedPreferencesUtil().btDevice = pairedDevice!;
    } else {
      if (SharedPreferencesUtil().btDevice.id.isEmpty) {
        pairedDevice = BtDevice.empty();
      } else {
        pairedDevice = SharedPreferencesUtil().btDevice;
      }
    }
    notifyListeners();
  }

  // TODO: thinh, use connection directly
  Future _bleDisconnectDevice(BtDevice btDevice) async {
    var connection = await ServiceManager.instance().device.ensureConnection(btDevice.id);
    if (connection == null) {
      return Future.value(null);
    }
    return await connection.disconnect();
  }

  Future<StreamSubscription<List<int>>?> _getBleBatteryLevelListener(
    String deviceId, {
    void Function(int)? onBatteryLevelChange,
  }) async {
    {
      var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
      if (connection == null) {
        return Future.value(null);
      }
      return connection.getBleBatteryLevelListener(onBatteryLevelChange: onBatteryLevelChange);
    }
  }

  Future<List<int>> _getStorageList(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return [];
    }
    return connection.getStorageList();
  }

  Future<BtDevice?> _getConnectedDevice() async {
    var deviceId = SharedPreferencesUtil().btDevice.id;
    if (deviceId.isEmpty) {
      return null;
    }
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    return connection?.device;
  }

  initiateBleBatteryListener() async {
    if (connectedDevice == null) {
      return;
    }
    _bleBatteryLevelListener?.cancel();
    _bleBatteryLevelListener = await _getBleBatteryLevelListener(
      connectedDevice!.id,
      onBatteryLevelChange: (int value) {
        batteryLevel = value;
        if (batteryLevel < 20 && !_hasLowBatteryAlerted) {
          _hasLowBatteryAlerted = true;
          NotificationService.instance.createNotification(
            title: "Low Battery Alert",
            body: "Your device is running low on battery. Time for a recharge! 🔋",
          );
        } else if (batteryLevel > 20) {
          _hasLowBatteryAlerted = true;
        }
        notifyListeners();
      },
    );
    notifyListeners();
  }

  Future periodicConnect(String printer) async {
    _reconnectionTimer?.cancel();
    _reconnectionTimer = Timer.periodic(Duration(seconds: _connectionCheckSeconds), (t) async {
      debugPrint("Period connect seconds: $_connectionCheckSeconds, triggered timer at ${DateTime.now()}");
      if (SharedPreferencesUtil().btDevice.id.isEmpty) {
        t.cancel();
        return;
      }
      if (_reconnectAt != null && _reconnectAt!.isAfter(DateTime.now())) {
        return;
      }
      print("isConnected: $isConnected, isConnecting: $isConnecting, connectedDevice: $connectedDevice");
      if ((!isConnected && connectedDevice == null)) {
        if (isConnecting) {
          return;
        }
        await scanAndConnectToDevice();
      } else {
        t.cancel();
      }
    });
  }

  Future<BtDevice?> _scanAndConnectDevice({bool autoConnect = true, bool timeout = false}) async {
    var device = await _getConnectedDevice();
    if (device != null) {
      return device;
    }

    int timeoutCounter = 0;
    while (true) {
      if (timeout && timeoutCounter >= 10) return null;
      await ServiceManager.instance().device.discover(desirableDeviceId: SharedPreferencesUtil().btDevice.id);
      if (connectedDevice != null) {
        return connectedDevice;
      }

      // If the device is not found, wait for a bit before retrying.
      await Future.delayed(const Duration(seconds: 2));
      timeoutCounter += 2;
    }
  }

  Future scanAndConnectToDevice() async {
    updateConnectingStatus(true);
    if (isConnected) {
      if (connectedDevice == null) {
        connectedDevice = await _getConnectedDevice();
        SharedPreferencesUtil().deviceName = connectedDevice!.name;
        MixpanelManager().deviceConnected();
      }

      setIsConnected(true);
      updateConnectingStatus(false);
      notifyListeners();
      return;
    }

    // else
    var device = await _scanAndConnectDevice();
    debugPrint('inside scanAndConnectToDevice $device in device_provider');
    if (device != null) {
      var cDevice = await _getConnectedDevice();
      if (cDevice != null) {
        setConnectedDevice(cDevice);
        setIsDeviceV2Connected();
        SharedPreferencesUtil().deviceName = cDevice.name;
        MixpanelManager().deviceConnected();
        setIsConnected(true);
      }
      debugPrint('device is not null $cDevice');
    }
    updateConnectingStatus(false);

    notifyListeners();
  }

  void updateConnectingStatus(bool value) {
    isConnecting = value;
    notifyListeners();
  }

  void setIsConnected(bool value) {
    isConnected = value;
    if (isConnected) {
      _reconnectionTimer?.cancel();
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _bleBatteryLevelListener?.cancel();
    _reconnectionTimer?.cancel();
    _bleImageBytesListener?.cancel(); // Cancel image listener on dispose
    ServiceManager.instance().device.unsubscribe(this);
    super.dispose();
  }

  void onDeviceDisconnected() async {
    debugPrint('onDisconnected inside: $connectedDevice');
    _havingNewFirmware = false;
    setConnectedDevice(null);
    setIsDeviceV2Connected();
    setIsConnected(false);
    updateConnectingStatus(false);

    captureProvider?.updateRecordingDevice(null);

    // Wals
    ServiceManager.instance().wal.getSyncs().sdcard.setDevice(null);

    InstabugLog.logInfo('Omi Device Disconnected');
    _disconnectNotificationTimer?.cancel();
    _disconnectNotificationTimer = Timer(const Duration(seconds: 30), () {
      NotificationService.instance.createNotification(
        title: 'Your Omi Device Disconnected',
        body: 'Please reconnect to continue using your Omi.',
      );
    });
    MixpanelManager().deviceDisconnected();

    // Retired 1s to prevent the race condition made by standby power of ble device
    Future.delayed(const Duration(seconds: 1), () {
      periodicConnect('coming from onDisconnect');
    });
  }

  Future<(String, bool, String)> shouldUpdateFirmware() async {
    if (pairedDevice == null || connectedDevice == null) {
      return ('No paired device is connected', false, '');
    }

    var device = pairedDevice!;
    var latestFirmwareDetails = await getLatestFirmwareVersion(
      deviceModelNumber: device.modelNumber,
      firmwareRevision: device.firmwareRevision,
      hardwareRevision: device.hardwareRevision,
      manufacturerName: device.manufacturerName,
    );

    return await DeviceUtils.shouldUpdateFirmware(
        currentFirmware: device.firmwareRevision, latestFirmwareDetails: latestFirmwareDetails);
  }

  void _onDeviceConnected(BtDevice device) async {
    debugPrint('_onConnected inside: $connectedDevice');
    _disconnectNotificationTimer?.cancel();
    NotificationService.instance.clearNotification(1);
    setConnectedDevice(device);

    setIsDeviceV2Connected();
    setIsConnected(true);

    await initiateBleBatteryListener();
    if (batteryLevel != -1 && batteryLevel < 20) {
      _hasLowBatteryAlerted = false;
    }
    updateConnectingStatus(false);

    // Check if the connected device is an Omi device before starting image listener
    var connection = await ServiceManager.instance().device.ensureConnection(device.id);
    if (connection is OmiDeviceConnection) {
      _bleImageBytesListener?.cancel(); // Cancel previous listener if exists
      _bleImageBytesListener = await (connection as OmiDeviceConnection).getBleImageBytesListener(
        onImageReceived: (Uint8List imageData) async {
          debugPrint('Received complete image from BLE, size: ${imageData.length}');
          
          // ** IMMEDIATE LOCAL DISPLAY **
          // Create a local image object for immediate display
          final timestamp = DateTime.now();
          final localImage = {
            'id': 'local_${timestamp.millisecondsSinceEpoch}',
            'data': imageData,
            'timestamp': timestamp,
            'uploaded': false,
            'thumbnail_url': null,
          };
          
          // Notify listeners immediately for local display
          // TODO: Add this to a local images list in CaptureProvider
          captureProvider?.addLocalImage(localImage);
          
          // ** BACKGROUND CLOUD UPLOAD **
          // Upload to cloud in background without blocking UI
          _uploadImageToCloud(imageData);
        },
      );
    }

    await captureProvider?.streamDeviceRecording(device: device);

    await getDeviceInfo();
    SharedPreferencesUtil().deviceName = device.name;

    // Wals
    ServiceManager.instance().wal.getSyncs().sdcard.setDevice(device);

    notifyListeners();

    // Check firmware updates
    _checkFirmwareUpdates();
  }

  void _checkFirmwareUpdates() async {
    await checkFirmwareUpdates();

    // Show firmware update dialog if needed
    if (_havingNewFirmware) {
      // Use a small delay to ensure the UI is ready
      Future.delayed(const Duration(milliseconds: 500), () {
        final context = MyApp.navigatorKey.currentContext;
        if (context != null) {
          showFirmwareUpdateDialog(context);
        }
      });
    }
  }

  Future checkFirmwareUpdates() async {
    int retryCount = 0;
    const maxRetries = 3;
    const retryDelay = Duration(seconds: 3);

    while (retryCount < maxRetries) {
      try {
        var (message, hasUpdate, version) = await shouldUpdateFirmware();
        _havingNewFirmware = hasUpdate;
        _latestFirmwareVersion = version.isNotEmpty ? version : message;
        notifyListeners();
        return hasUpdate; // Return whether there's an update
      } catch (e) {
        retryCount++;
        debugPrint('Error checking firmware update (attempt $retryCount): $e');

        if (retryCount == maxRetries) {
          debugPrint('Max retries reached, giving up');
          _havingNewFirmware = false;
          notifyListeners();
          break;
        }

        await Future.delayed(retryDelay);
      }
    }
    return;
  }

  void showFirmwareUpdateDialog(BuildContext context) {
    if (!_havingNewFirmware || !SharedPreferencesUtil().showFirmwareUpdateDialog) {
      return;
    }

    showDialog(
      context: context,
      builder: (context) => ConfirmationDialog(
        title: 'Firmware Update Available',
        description:
            'A new firmware update (${_latestFirmwareVersion}) is available for your Omi device. Would you like to update now?',
        confirmText: 'Update',
        cancelText: 'Later',
        onConfirm: () {
          Navigator.of(context).pop();
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (context) => FirmwareUpdate(device: pairedDevice),
            ),
          );
        },
        onCancel: () {
          Navigator.of(context).pop();
        },
      ),
    );
  }

  Future setIsDeviceV2Connected() async {
    if (connectedDevice == null) {
      isDeviceV2Connected = false;
    } else {
      var storageFiles = await _getStorageList(connectedDevice!.id);
      isDeviceV2Connected = storageFiles.isNotEmpty;
    }
    notifyListeners();
  }

  @override
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) async {
    debugPrint("provider > device connection state changed...${deviceId}...${state}...${connectedDevice?.id}");
    switch (state) {
      case DeviceConnectionState.connected:
        var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
        if (connection == null) {
          return;
        }
        _onDeviceConnected(connection.device);
        break;
      case DeviceConnectionState.disconnected:
        if (deviceId == connectedDevice?.id) {
          onDeviceDisconnected();
        }
      default:
        debugPrint("Device connection state is not supported $state");
    }
  }

  @override
  void onDevices(List<BtDevice> devices) async {}

  @override
  void onStatusChanged(DeviceServiceStatus status) {}

  prepareDFU() {
    if (connectedDevice == null) {
      return;
    }
    _bleDisconnectDevice(connectedDevice!);
    _reconnectAt = DateTime.now().add(Duration(seconds: 30));
  }

  Future _uploadImageToCloud(Uint8List imageData) async {
    // Upload to cloud in background without blocking UI
    try {
      // Properly construct URL - ensure no double slashes
      String baseUrl = Env.apiBaseUrl ?? 'http://127.0.0.1:8000';
      if (baseUrl.endsWith('/')) {
        baseUrl = baseUrl.substring(0, baseUrl.length - 1);
      }
      final url = Uri.parse('$baseUrl/v2/files');
      debugPrint('Background uploading image to: $url');
      
      var request = http.MultipartRequest('POST', url);
      
      // Add authorization header
      request.headers.addAll({'Authorization': await getAuthHeader()});
      
      request.files.add(http.MultipartFile.fromBytes(
        'files', // The field name the backend expects for the file
        imageData,
        filename: 'openglass_image_${DateTime.now().millisecondsSinceEpoch}.jpg',
      ));
      
      // Send request with 60 second timeout (increased from default)
      var response = await request.send().timeout(
        const Duration(seconds: 60),
        onTimeout: () {
          debugPrint('Background image upload timed out after 60 seconds');
          throw TimeoutException('Background image upload timed out', const Duration(seconds: 60));
        },
      );
      
      if (response.statusCode == 200) {
        debugPrint('Background image upload successful');
        var responseBody = await response.stream.bytesToString();
        debugPrint('Upload response: $responseBody');
        
        // TODO: Update the local image record with cloud URLs when upload completes
        // This could trigger a UI update to show cloud thumbnails
      } else {
        debugPrint('Background image upload failed. Status code: ${response.statusCode}');
        var responseBody = await response.stream.bytesToString();
        debugPrint('Error response: $responseBody');
        
        // Retry once for 5xx server errors
        if (response.statusCode >= 500 && response.statusCode < 600) {
          debugPrint('Retrying background image upload due to server error...');
          await Future.delayed(const Duration(seconds: 5));
          return _uploadImageToCloudRetry(imageData);
        }
      }
    } on TimeoutException catch (e) {
      debugPrint('Background image upload timeout: $e');
      // Retry once for timeout
      debugPrint('Retrying background image upload due to timeout...');
      await Future.delayed(const Duration(seconds: 5));
      return _uploadImageToCloudRetry(imageData);
    } catch (e) {
      debugPrint('Background image upload error: $e');
    }
  }

  Future _uploadImageToCloudRetry(Uint8List imageData) async {
    // Retry upload with shorter timeout
    try {
      String baseUrl = Env.apiBaseUrl ?? 'http://127.0.0.1:8000';
      if (baseUrl.endsWith('/')) {
        baseUrl = baseUrl.substring(0, baseUrl.length - 1);
      }
      final url = Uri.parse('$baseUrl/v2/files');
      debugPrint('Retrying background image upload to: $url');
      
      var request = http.MultipartRequest('POST', url);
      request.headers.addAll({'Authorization': await getAuthHeader()});
      
      request.files.add(http.MultipartFile.fromBytes(
        'files',
        imageData,
        filename: 'openglass_image_${DateTime.now().millisecondsSinceEpoch}_retry.jpg',
      ));
      
      // Shorter timeout for retry
      var response = await request.send().timeout(
        const Duration(seconds: 30),
        onTimeout: () {
          debugPrint('Background image upload retry timed out after 30 seconds');
          throw TimeoutException('Background image upload retry timed out', const Duration(seconds: 30));
        },
      );
      
      if (response.statusCode == 200) {
        debugPrint('Background image upload retry successful');
        var responseBody = await response.stream.bytesToString();
        debugPrint('Retry upload response: $responseBody');
      } else {
        debugPrint('Background image upload retry failed. Status code: ${response.statusCode}');
        var responseBody = await response.stream.bytesToString();
        debugPrint('Retry error response: $responseBody');
      }
    } catch (e) {
      debugPrint('Background image upload retry error: $e');
    }
  }
}
