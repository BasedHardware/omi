import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/http/api/device.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/device.dart';
import 'package:nordic_dfu/nordic_dfu.dart';
import 'package:path_provider/path_provider.dart';
import 'package:http/http.dart' as http;

mixin FirmwareMixin<T extends StatefulWidget> on State<T> {
  Map latestFirmwareDetails = {};
  bool isDownloading = false;
  bool isDownloaded = false;
  int downloadProgress = 1;
  bool isInstalling = false;
  bool isInstalled = false;
  int installProgress = 1;
  List<String> otaUpdateSteps = [];

  // TODO: thinh, use connection directly
  Future _bleDisconnectDevice(BtDevice btDevice) async {
    var connection = await ServiceManager.instance().device.ensureConnection(btDevice.id);
    if (connection == null) {
      return Future.value(null);
    }
    return await connection.disconnect();
  }

  Future<void> startDfu(BtDevice btDevice, {bool fileInAssets = false}) async {
    setState(() {
      isInstalling = true;
    });
    await _bleDisconnectDevice(btDevice);
    await Future.delayed(const Duration(seconds: 2));

    String firmwareFile = '${(await getApplicationDocumentsDirectory()).path}/firmware.zip';
    NordicDfu dfu = NordicDfu();
    await dfu.startDfu(
      btDevice.id,
      firmwareFile,
      fileInAsset: fileInAssets,
      numberOfPackets: 8,
      enableUnsafeExperimentalButtonlessServiceInSecureDfu: true,
      iosSpecialParameter: const IosSpecialParameter(
        packetReceiptNotificationParameter: 8,
        forceScanningForNewAddressInLegacyDfu: true,
        connectionTimeout: 60,
      ),
      androidSpecialParameter: const AndroidSpecialParameter(
        packetReceiptNotificationsEnabled: true,
        rebootTime: 1000,
      ),
      onProgressChanged: (deviceAddress, percent, speed, avgSpeed, currentPart, partsTotal) {
        debugPrint('deviceAddress: $deviceAddress, percent: $percent');
        setState(() {
          installProgress = percent.toInt();
        });
      },
      onError: (deviceAddress, error, errorType, message) =>
          debugPrint('deviceAddress: $deviceAddress, error: $error, errorType: $errorType, message: $message'),
      onDeviceConnecting: (deviceAddress) => debugPrint('deviceAddress: $deviceAddress, onDeviceConnecting'),
      onDeviceConnected: (deviceAddress) => debugPrint('deviceAddress: $deviceAddress, onDeviceConnected'),
      onDfuProcessStarting: (deviceAddress) => debugPrint('deviceAddress: $deviceAddress, onDfuProcessStarting'),
      onDfuProcessStarted: (deviceAddress) => debugPrint('deviceAddress: $deviceAddress, onDfuProcessStarted'),
      onEnablingDfuMode: (deviceAddress) => debugPrint('deviceAddress: $deviceAddress, onEnablingDfuMode'),
      onFirmwareValidating: (deviceAddress) => debugPrint('address: $deviceAddress, onFirmwareValidating'),
      onDfuCompleted: (deviceAddress) {
        debugPrint('deviceAddress: $deviceAddress, onDfuCompleted');
        setState(() {
          isInstalling = false;
          isInstalled = true;
        });
      },
    );
  }

  Future getLatestVersion(
      {required String deviceModelNumber,
      required String firmwareRevision,
      required String hardwareRevision,
      required String manufacturerName}) async {
    latestFirmwareDetails = await getLatestFirmwareVersion(
      deviceModelNumber: deviceModelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
    );
    if (latestFirmwareDetails['ota_update_steps'] != null) {
      otaUpdateSteps = List<String>.from(latestFirmwareDetails['ota_update_steps']);
    }
  }

  Future<(String, bool, String)> shouldUpdateFirmware({required String currentFirmware}) async {
    return DeviceUtils.shouldUpdateFirmware(
        currentFirmware: currentFirmware, latestFirmwareDetails: latestFirmwareDetails);
  }

  Future downloadFirmware() async {
    final zipUrl = latestFirmwareDetails['zip_url'];
    if (zipUrl == null) {
      debugPrint('Error: zip_url is null in latestFirmwareDetails');
      return;
    }

    var httpClient = http.Client();
    var request = http.Request('GET', Uri.parse(zipUrl));
    var response = httpClient.send(request);
    String dir = (await getApplicationDocumentsDirectory()).path;

    List<List<int>> chunks = [];
    int downloaded = 0;
    setState(() {
      isDownloading = true;
      isDownloaded = false;
    });
    response.asStream().listen((http.StreamedResponse r) {
      r.stream.listen((List<int> chunk) {
        // Display percentage of completion
        debugPrint('downloadPercentage: ${downloaded / r.contentLength! * 100}');
        setState(() {
          downloadProgress = (downloaded / r.contentLength! * 100).toInt();
        });
        chunks.add(chunk);
        downloaded += chunk.length;
      }, onDone: () async {
        // Display percentage of completion
        debugPrint('downloadPercentage: ${downloaded / r.contentLength! * 100}');

        // Save the file
        File file = File('$dir/firmware.zip');
        final Uint8List bytes = Uint8List(r.contentLength!);
        int offset = 0;
        for (List<int> chunk in chunks) {
          bytes.setRange(offset, offset + chunk.length, chunk);
          offset += chunk.length;
        }
        await file.writeAsBytes(bytes);
        setState(() {
          isDownloading = false;
          isDownloaded = true;
        });
        return;
      });
    });
  }
}
