import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/widgets.dart';

import 'package:flutter_archive/flutter_archive.dart';
import 'package:mcumgr_flutter/mcumgr_flutter.dart' as mcumgr;
import 'package:nordic_dfu/nordic_dfu.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import 'package:omi/backend/http/api/device.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/firmware_update_build_policy.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/manifest/manifest.dart';
import 'package:omi/utils/omi_mcu_dfu_policy.dart';

class FirmwareDfuConnectionHandoff {
  FirmwareDfuConnectionHandoff({required this.releaseUpdater, required this.resumeDeviceConnection});

  final Future<void> Function() releaseUpdater;
  final Future<void> Function() resumeDeviceConnection;
  Future<void>? _finishFuture;

  bool get hasStarted => _finishFuture != null;

  Future<void> finish() => _finishFuture ??= _finish();

  Future<void> _finish() async {
    try {
      await releaseUpdater();
    } finally {
      await resumeDeviceConnection();
    }
  }
}

mixin FirmwareMixin<T extends StatefulWidget> on State<T> {
  FirmwareUpdateBuildPolicy get firmwareUpdatePolicy => FirmwareUpdateBuildPolicy.current;

  Map latestFirmwareDetails = {};
  bool isDownloading = false;
  bool isDownloaded = false;
  int downloadProgress = 0;
  bool isInstalling = false;
  bool isInstalled = false;
  int installProgress = 0;
  bool isLegacySecureDFU = true;
  List<String> otaUpdateSteps = [];
  late final mcumgr.FirmwareUpdateManagerFactory? managerFactory =
      firmwareUpdatePolicy.allowsOmiFirmwareUpdate ? mcumgr.FirmwareUpdateManagerFactory() : null;
  mcumgr.FirmwareUpdateManager? _mcuUpdateManager;
  FirmwareDfuConnectionHandoff? _activeDfuHandoff;

  /// Process ZIP file and return firmware image list
  Future<List<mcumgr.Image>> processZipFile(Uint8List zipFileData) async {
    // Create temporary directory
    final prefix = 'firmware_${const Uuid().v4()}';
    final systemTempDir = await getTemporaryDirectory();
    final tempDir = Directory('${systemTempDir.path}/$prefix');
    await tempDir.create();

    try {
      // Write ZIP data to temporary file
      final firmwareFile = File('${tempDir.path}/firmware.zip');
      await firmwareFile.writeAsBytes(zipFileData);

      // Create destination directory for extraction
      final destinationDir = Directory('${tempDir.path}/firmware');
      await destinationDir.create();

      // Extract ZIP file
      await ZipFile.extractToDirectory(zipFile: firmwareFile, destinationDir: destinationDir);

      // Read and parse manifest.json
      final manifestFile = File('${destinationDir.path}/manifest.json');
      final manifestString = await manifestFile.readAsString();
      final manifestJson = json.decode(manifestString);
      final manifest = Manifest.fromJson(manifestJson);

      // Process firmware files
      final List<mcumgr.Image> firmwareImages = [];
      for (final file in manifest.files) {
        final firmwareFile = File('${destinationDir.path}/${file.file}');
        final firmwareFileData = await firmwareFile.readAsBytes();
        final image = mcumgr.Image(image: file.image, data: firmwareFileData);
        firmwareImages.add(image);
      }

      return firmwareImages;
    } catch (e) {
      throw Exception('Failed to process ZIP file: $e');
    } finally {
      // Cleanup: Delete temporary directory
      await tempDir.delete(recursive: true);
    }
  }

  Future<void> startDfu(BtDevice btDevice, {bool fileInAssets = false, String? zipFilePath}) async {
    if (!firmwareUpdatePolicy.allowsOmiFirmwareUpdate) {
      Logger.debug('Omi firmware updates are unavailable in the Ray-Ban DAT build');
      return;
    }
    if (isLegacySecureDFU) {
      return startLegacyDfu(btDevice, fileInAssets: fileInAssets, zipFilePath: zipFilePath);
    }
    return startMCUDfu(btDevice, fileInAssets: fileInAssets, zipFilePath: zipFilePath);
  }

  Future<void> killMcuUpdateManager() async {
    if (_mcuUpdateManager != null) {
      try {
        await _mcuUpdateManager!.kill();
      } catch (e) {
        Logger.debug('Error killing update manager: $e');
      }
      _mcuUpdateManager = null;
    }
  }

  Future<void> _releaseLegacyDfu() async {
    // nordic_dfu 6.2.0 sends abort synchronously but does not complete the
    // MethodChannel result on Android or iOS. Do not let that plugin bug strand
    // connection reclaim during page disposal.
    unawaited(NordicDfu().abortDfu());
  }

  /// Ends whichever DFU implementation currently owns BLE and reclaims the
  /// exact device connection. Safe to call from a terminal callback and page
  /// disposal concurrently.
  Future<void> finishDfuSession() async {
    final handoff = _activeDfuHandoff;
    if (handoff == null) {
      await killMcuUpdateManager();
      return;
    }
    await _finishDfuHandoff(handoff);
  }

  Future<void> _finishDfuHandoff(FirmwareDfuConnectionHandoff handoff) async {
    try {
      await handoff.finish();
    } finally {
      if (identical(_activeDfuHandoff, handoff)) {
        _activeDfuHandoff = null;
      }
    }
  }

  Future<void> _completeDfu(
    FirmwareDfuConnectionHandoff handoff, {
    required bool successful,
    Object? error,
  }) async {
    final isFirstTerminalEvent = !handoff.hasStarted;
    final finishFuture = _finishDfuHandoff(handoff);

    if (isFirstTerminalEvent && mounted) {
      setState(() {
        isInstalling = false;
        isInstalled = successful;
      });
    }
    if (error != null) {
      Logger.debug('Firmware update failed: $error');
    }

    try {
      await finishFuture;
    } catch (e) {
      Logger.error(
        'Firmware update reached a terminal state, but exact-device BLE reclaim '
        'failed after bounded retries: $e',
      );
    }
  }

  Future<void> startMCUDfu(BtDevice btDevice, {bool fileInAssets = false, String? zipFilePath}) async {
    if (!firmwareUpdatePolicy.allowsOmiFirmwareUpdate) {
      Logger.debug('MCU firmware updates are unavailable in the Ray-Ban DAT build');
      return;
    }
    String firmwareFile = zipFilePath ?? '${(await getApplicationDocumentsDirectory()).path}/firmware.zip';
    final file = File(firmwareFile);
    if (!await file.exists()) {
      Logger.debug('Firmware file not found: $firmwareFile');
      return;
    }
    final bytes = await file.readAsBytes();
    final images = await processZipFile(bytes);
    final configuration = OmiMcuDfuPolicy.createConfiguration();

    if (!mounted) return;
    setState(() {
      isInstalling = true;
    });
    final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
    final handoff = FirmwareDfuConnectionHandoff(
      releaseUpdater: killMcuUpdateManager,
      resumeDeviceConnection: deviceProvider.resumeConnectionAfterDFU,
    );
    _activeDfuHandoff = handoff;

    try {
      await deviceProvider.prepareDFU();
      await Future.delayed(const Duration(seconds: 2));

      await killMcuUpdateManager();
      final updateManager = await managerFactory!.getUpdateManager(btDevice.id);
      _mcuUpdateManager = updateManager;

      final updateStream = updateManager.setup();

      updateStream.listen(
        (state) {
          if (state == mcumgr.FirmwareUpgradeState.success) {
            Logger.debug('update success');
            unawaited(_completeDfu(handoff, successful: true));
          } else {
            Logger.debug('update state: $state');
          }
        },
        onError: (Object error, StackTrace stackTrace) {
          unawaited(_completeDfu(handoff, successful: false, error: error));
        },
        onDone: () {
          unawaited(_completeDfu(handoff, successful: false));
        },
      );

      updateManager.progressStream.listen((progress) {
        Logger.debug('progress: $progress');
        if (!mounted) return;
        setState(() {
          installProgress = (progress.bytesSent / progress.imageSize * 100).round();
        });
      });

      updateManager.logger.logMessageStream
          .where((log) => log.level.rawValue > 1) // Filter debug messages
          .listen((log) {
        Logger.debug('dfu log: ${log.message}');
      });

      await updateManager.update(images, configuration: configuration);
    } catch (e) {
      await _completeDfu(handoff, successful: false, error: e);
      rethrow;
    }
  }

  Future<void> startLegacyDfu(BtDevice btDevice, {bool fileInAssets = false, String? zipFilePath}) async {
    if (!firmwareUpdatePolicy.allowsOmiFirmwareUpdate) {
      Logger.debug('Legacy firmware updates are unavailable in the Ray-Ban DAT build');
      return;
    }
    final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
    final firmwareFile = zipFilePath ?? '${(await getApplicationDocumentsDirectory()).path}/firmware.zip';
    if (!fileInAssets && !await File(firmwareFile).exists()) {
      Logger.debug('Firmware file not found: $firmwareFile');
      return;
    }

    setState(() {
      isInstalling = true;
    });
    final handoff = FirmwareDfuConnectionHandoff(
      releaseUpdater: _releaseLegacyDfu,
      resumeDeviceConnection: deviceProvider.resumeConnectionAfterDFU,
    );
    _activeDfuHandoff = handoff;

    try {
      await deviceProvider.prepareDFU();
      await Future.delayed(const Duration(seconds: 2));
      final dfu = NordicDfu();
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
          Logger.debug('deviceAddress: $deviceAddress, percent: $percent');
          if (!mounted) return;
          setState(() {
            installProgress = percent.toInt();
          });
        },
        onError: (deviceAddress, error, errorType, message) {
          Logger.debug('deviceAddress: $deviceAddress, error: $error, errorType: $errorType, message: $message');
          unawaited(_completeDfu(handoff, successful: false, error: message));
        },
        onDfuAborted: (deviceAddress) {
          Logger.debug('deviceAddress: $deviceAddress, onDfuAborted');
          unawaited(_completeDfu(handoff, successful: false));
        },
        onDeviceConnecting: (deviceAddress) => Logger.debug('deviceAddress: $deviceAddress, onDeviceConnecting'),
        onDeviceConnected: (deviceAddress) => Logger.debug('deviceAddress: $deviceAddress, onDeviceConnected'),
        onDfuProcessStarting: (deviceAddress) => Logger.debug('deviceAddress: $deviceAddress, onDfuProcessStarting'),
        onDfuProcessStarted: (deviceAddress) => Logger.debug('deviceAddress: $deviceAddress, onDfuProcessStarted'),
        onEnablingDfuMode: (deviceAddress) => Logger.debug('deviceAddress: $deviceAddress, onEnablingDfuMode'),
        onFirmwareValidating: (deviceAddress) => Logger.debug('address: $deviceAddress, onFirmwareValidating'),
        onDfuCompleted: (deviceAddress) {
          Logger.debug('deviceAddress: $deviceAddress, onDfuCompleted');
          unawaited(_completeDfu(handoff, successful: true));
        },
      );
    } catch (e) {
      await _completeDfu(handoff, successful: false, error: e);
      rethrow;
    }
  }

  Future getLatestVersion({
    required String deviceModelNumber,
    required String firmwareRevision,
    required String hardwareRevision,
    required String manufacturerName,
  }) async {
    latestFirmwareDetails = await getLatestFirmwareVersion(
      deviceModelNumber: deviceModelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
    );
    if (latestFirmwareDetails['ota_update_steps'] != null) {
      otaUpdateSteps = List<String>.from(latestFirmwareDetails['ota_update_steps']);
    }
    if (latestFirmwareDetails['is_legacy_secure_dfu'] != null) {
      isLegacySecureDFU = latestFirmwareDetails['is_legacy_secure_dfu'];
    }
  }

  Future getStableVersion({required String deviceModelNumber}) async {
    latestFirmwareDetails = await getStableFirmwareVersion(deviceModelNumber: deviceModelNumber);
    if (latestFirmwareDetails['ota_update_steps'] != null) {
      otaUpdateSteps = List<String>.from(latestFirmwareDetails['ota_update_steps']);
    }
    if (latestFirmwareDetails['is_legacy_secure_dfu'] != null) {
      isLegacySecureDFU = latestFirmwareDetails['is_legacy_secure_dfu'];
    }
  }

  Future<(String, bool, String)> shouldUpdateFirmware({required String currentFirmware}) async {
    return DeviceUtils.shouldUpdateFirmware(
      currentFirmware: currentFirmware,
      latestFirmwareDetails: latestFirmwareDetails,
    );
  }

  Future downloadFirmware() async {
    final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
    final zipUrl = latestFirmwareDetails['zip_url'];
    if (zipUrl == null) {
      Logger.debug('Error: zip_url is null in latestFirmwareDetails');
      setState(() {
        isDownloading = false;
      });
      // Reset firmware update state on error
      deviceProvider.resetFirmwareUpdateState();
      return;
    }

    String dir = (await getApplicationDocumentsDirectory()).path;

    setState(() {
      isDownloading = true;
      isDownloaded = false;
      downloadProgress = 0;
    });

    try {
      final r = await makeRawApiCall(method: 'GET', url: zipUrl);
      final completer = Completer<void>();
      final int? totalBytes = r.contentLength;

      List<List<int>> chunks = [];
      int downloaded = 0;

      r.stream.listen(
        (List<int> chunk) {
          chunks.add(chunk);
          downloaded += chunk.length;
          if (totalBytes != null && totalBytes > 0) {
            Logger.debug('downloadPercentage: ${downloaded / totalBytes * 100}');
            setState(() {
              downloadProgress = (downloaded / totalBytes * 100).toInt();
            });
          }
        },
        onDone: () async {
          try {
            Logger.debug('downloadPercentage: 100');
            File file = File('$dir/firmware.zip');
            final Uint8List bytes = Uint8List(downloaded);
            int offset = 0;
            for (List<int> chunk in chunks) {
              bytes.setRange(offset, offset + chunk.length, chunk);
              offset += chunk.length;
            }
            await file.writeAsBytes(bytes);
            setState(() {
              isDownloading = false;
              isDownloaded = true;
              downloadProgress = 100;
            });
            completer.complete();
          } catch (e) {
            completer.completeError(e);
          }
        },
        onError: (error) {
          Logger.debug('Download error: $error');
          setState(() {
            isDownloading = false;
          });
          deviceProvider.resetFirmwareUpdateState();
          completer.completeError(error);
        },
      );

      await completer.future;
    } catch (e) {
      Logger.debug('Download error: $e');
      if (mounted) {
        setState(() {
          isDownloading = false;
        });
      }
      deviceProvider.resetFirmwareUpdateState();
    }
  }
}
