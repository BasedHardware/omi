import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/utils/ble/connect.dart';
import 'package:nordic_dfu/nordic_dfu.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'package:version/version.dart';
import 'package:http/http.dart' as http;

mixin FirmwareMixin<T extends StatefulWidget> on State<T> {
  Map latestFirmwareDetails = {};
  bool isDownloading = false;
  bool isDownloaded = false;
  int downloadProgress = 1;
  bool isInstalling = false;
  bool isInstalled = false;
  int installProgress = 1;

  Future<void> startDfu(BTDeviceStruct btDevice, {bool fileInAssets = false}) async {
    setState(() {
      isInstalling = true;
    });
    bleDisconnectDevice(btDevice);
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

  Future getLatestVersion({required String deviceName}) async {
    int device = deviceName == 'Friend' ? 1 : 2;
    var res = await makeApiCall(
        url: "${Env.apiBaseUrl}v1/firmware/latest?device=$device", headers: {}, body: '', method: 'GET');
    if (res == null) {
      latestFirmwareDetails = {};
      return;
    }
    if (res.statusCode == 200) {
      latestFirmwareDetails = jsonDecode(res.body);
    }
  }

  Future<(String, bool)> shouldUpdateFirmware({required String currentFirmware, required String deviceName}) async {
    Version currentVersion = Version.parse(currentFirmware);
    if (latestFirmwareDetails.isEmpty) {
      return ('Latest Version Not Available', false);
    }
    if (latestFirmwareDetails.isEmpty || latestFirmwareDetails['version'] == null) {
      return ('Latest Version Not Available', false);
    }
    if (latestFirmwareDetails['version'] == null || latestFirmwareDetails['draft']) {
      return ('Latest Version Not Available', false);
    }
    Version latestVersion = Version.parse(latestFirmwareDetails['version']);
    Version minVersion = Version.parse(latestFirmwareDetails['min_version']);
    if (currentVersion < minVersion) {
      return (
        'The minimum version required to enable OTA Updates is ${minVersion.toString()}. You are on $currentFirmware. Please Update to ${minVersion.toString()} manually.',
        false
      );
    } else {
      if (latestVersion > currentVersion) {
        PackageInfo packageInfo = await PackageInfo.fromPlatform();
        if (Version.parse(packageInfo.version) <= Version.parse(latestFirmwareDetails['min_app_version']) &&
            int.parse(packageInfo.buildNumber) < int.parse(latestFirmwareDetails['min_app_version_code'])) {
          return (
            'The latest version of firmware is not compatible with this version of App (${packageInfo.version}+${packageInfo.buildNumber}). Please update the app from ${Platform.isAndroid ? 'Play Store' : 'App Store'}',
            false
          );
        } else {
          return ('A new version is available! Update your Friend now.', true);
        }
      } else {
        return ('You are already on the latest version', false);
      }
    }
  }

  Future downloadFirmware() async {
    var httpClient = http.Client();
    var request = http.Request('GET', Uri.parse(latestFirmwareDetails['zip_url']));
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
