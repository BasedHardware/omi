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
import 'package:omi/utils/analytics/firmware_update_telemetry.dart';
import 'package:omi/utils/firmware_update_build_policy.dart';
import 'package:omi/utils/firmware_install_verification.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/manifest/manifest.dart';

/// Why an Omi firmware update stopped, so the page can say what happened and what to do.
enum FirmwareUpdateFailure {
  /// The firmware file could not be downloaded (network).
  download,

  /// The device did not accept the update (connection lost, device rejected it).
  install,
  notInstalled,
  noReconnect,
}

mixin FirmwareMixin<T extends StatefulWidget> on State<T> {
  FirmwareUpdateBuildPolicy get firmwareUpdatePolicy => FirmwareUpdateBuildPolicy.current;

  Map latestFirmwareDetails = {};
  bool isDownloading = false;
  bool isDownloaded = false;
  int downloadProgress = 0;
  bool isInstalling = false;
  bool isInstalled = false;
  bool isVerifying = false;
  String? observedFirmwareVersion;
  int installProgress = 0;
  bool isLegacySecureDFU = true;
  List<String> otaUpdateSteps = [];

  /// Set when the last attempt failed; cleared when a new attempt starts. The page shows a failed
  /// state with the cause, Try Again and Contact Support instead of silently resetting.
  FirmwareUpdateFailure? updateFailure;

  void _fail(FirmwareUpdateFailure failure) {
    if (!mounted) return;
    setState(() {
      isDownloading = false;
      isInstalling = false;
      isVerifying = false;
      updateFailure = failure;
    });
    Provider.of<DeviceProvider>(context, listen: false).resetFirmwareUpdateState();
  }

  /// Clears a previous failure before retrying.
  void clearFirmwareFailure() {
    if (updateFailure == null) return;
    setState(() => updateFailure = null);
  }

  late final mcumgr.FirmwareUpdateManagerFactory? managerFactory =
      firmwareUpdatePolicy.allowsOmiFirmwareUpdate ? mcumgr.FirmwareUpdateManagerFactory() : null;
  mcumgr.FirmwareUpdateManager? _mcuUpdateManager;
  FirmwareUpdateTelemetry? _firmwareTelemetry;

  void _startFirmwareTelemetry(BtDevice device, String protocol) {
    final current = Provider.of<DeviceProvider>(context, listen: false).pairedDevice;
    _firmwareTelemetry = FirmwareUpdateTelemetry.start(
      device: current?.id == device.id ? current! : device,
      protocol: protocol,
    );
  }

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
    final manager = _mcuUpdateManager;
    _mcuUpdateManager = null;
    if (manager == null) return;
    try {
      await manager.kill();
    } catch (e) {
      Logger.debug('Error killing update manager: $e');
    }
  }

  Future<void> startMCUDfu(BtDevice btDevice, {bool fileInAssets = false, String? zipFilePath}) async {
    if (!firmwareUpdatePolicy.allowsOmiFirmwareUpdate) {
      Logger.debug('MCU firmware updates are unavailable in the Ray-Ban DAT build');
      return;
    }
    _startFirmwareTelemetry(btDevice, 'mcumgr');
    setState(() {
      isInstalling = true;
      isInstalled = false;
      isVerifying = false;
      observedFirmwareVersion = null;
      updateFailure = null;
    });
    await Provider.of<DeviceProvider>(context, listen: false).prepareDFU();
    await Future.delayed(const Duration(seconds: 2));

    String firmwareFile = zipFilePath ?? '${(await getApplicationDocumentsDirectory()).path}/firmware.zip';
    final file = File(firmwareFile);
    if (!await file.exists()) {
      _firmwareTelemetry?.failed(failureClass: 'firmware_file_missing');
      Logger.debug('Firmware file not found: $firmwareFile');
      _fail(FirmwareUpdateFailure.download);
      return;
    }
    final Uint8List bytes;
    try {
      bytes = await file.readAsBytes();
    } catch (e) {
      _firmwareTelemetry?.failed(failureClass: 'firmware_file_missing');
      _fail(FirmwareUpdateFailure.download);
      return;
    }
    const configuration = mcumgr.FirmwareUpgradeConfiguration(
      estimatedSwapTime: Duration(seconds: 0),
      eraseAppSettings: true,
      pipelineDepth: 1,
    );

    await killMcuUpdateManager();
    final mcumgr.FirmwareUpdateManager updateManager;
    final List<mcumgr.Image> images;
    try {
      updateManager = await managerFactory!.getUpdateManager(btDevice.id);
      _mcuUpdateManager = updateManager;
      // A corrupt download (e.g. a captive-portal page saved as the zip) throws here; it must end in
      // the failed state, not an installing spinner with back blocked.
      images = await processZipFile(bytes);
    } catch (e) {
      _firmwareTelemetry?.failed(failureClass: 'native_dfu_error');
      Logger.debug('update preparation failed: $e');
      _fail(FirmwareUpdateFailure.install);
      return;
    }

    final updateStream = updateManager.setup();

    // The stream reports every stage (validate, upload, test, reset, confirm) and ends in success;
    // a failure arrives as a stream error, and a cancel closes the stream without success.
    var transportFinished = false;
    var lastState = mcumgr.FirmwareUpgradeState.none;
    String failureClass() => lastState == mcumgr.FirmwareUpgradeState.upload
        ? 'upload_error'
        : lastState == mcumgr.FirmwareUpgradeState.test || lastState == mcumgr.FirmwareUpgradeState.reset
            ? 'mark_error'
            : 'native_dfu_error';
    updateStream.listen(
      (state) {
        if (transportFinished) return;
        lastState = state;
        Logger.debug('update state: $state');
        if (state == mcumgr.FirmwareUpgradeState.test || state == mcumgr.FirmwareUpgradeState.reset) {
          _firmwareTelemetry?.uploadFinished();
        }
        // Entering confirm means the test mark and reset stages have completed.
        if (state == mcumgr.FirmwareUpgradeState.confirm) _firmwareTelemetry?.installRequested();
        if (state != mcumgr.FirmwareUpgradeState.success) return;
        transportFinished = true;
        _firmwareTelemetry?.uploadFinished();
        _firmwareTelemetry?.installRequested();
        unawaited(_verifyInstallation(btDevice));
      },
      onError: (Object error) {
        if (transportFinished) return;
        transportFinished = true;
        _firmwareTelemetry?.failed(failureClass: failureClass());
        Logger.debug('update error: $error');
        _fail(FirmwareUpdateFailure.install);
      },
      onDone: () {
        if (transportFinished || !isInstalling) return;
        transportFinished = true;
        _firmwareTelemetry?.failed(failureClass: 'native_dfu_error');
        _fail(FirmwareUpdateFailure.install);
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

    try {
      await updateManager.update(images, configuration: configuration);
    } catch (e) {
      if (transportFinished) return;
      transportFinished = true;
      _firmwareTelemetry?.failed(failureClass: failureClass());
      Logger.debug('update start failed: $e');
      _fail(FirmwareUpdateFailure.install);
    }
  }

  Future<void> startLegacyDfu(BtDevice btDevice, {bool fileInAssets = false, String? zipFilePath}) async {
    if (!firmwareUpdatePolicy.allowsOmiFirmwareUpdate) {
      Logger.debug('Legacy firmware updates are unavailable in the Ray-Ban DAT build');
      return;
    }
    _startFirmwareTelemetry(btDevice, 'nordic_dfu');
    setState(() {
      isInstalling = true;
      isInstalled = false;
      isVerifying = false;
      observedFirmwareVersion = null;
      updateFailure = null;
    });
    await Provider.of<DeviceProvider>(context, listen: false).prepareDFU();
    await Future.delayed(const Duration(seconds: 2));
    String firmwareFile = zipFilePath ?? '${(await getApplicationDocumentsDirectory()).path}/firmware.zip';
    if (!fileInAssets && !await File(firmwareFile).exists()) {
      _firmwareTelemetry?.failed(failureClass: 'firmware_file_missing');
      _fail(FirmwareUpdateFailure.download);
      return;
    }
    NordicDfu dfu = NordicDfu();
    var dfuFinished = false;
    try {
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
        androidSpecialParameter:
            const AndroidSpecialParameter(packetReceiptNotificationsEnabled: true, rebootTime: 1000),
        onProgressChanged: (deviceAddress, percent, speed, avgSpeed, currentPart, partsTotal) {
          if (percent >= 100 && currentPart == partsTotal) _firmwareTelemetry?.uploadFinished();
          Logger.debug('deviceAddress: $deviceAddress, percent: $percent');
          if (!mounted) return;
          setState(() {
            installProgress = percent.toInt();
          });
        },
        onError: (deviceAddress, error, errorType, message) {
          if (dfuFinished) return;
          dfuFinished = true;
          _firmwareTelemetry?.failed(failureClass: 'native_dfu_error');
          Logger.debug('deviceAddress: $deviceAddress, error: $error, errorType: $errorType, message: $message');
          _fail(FirmwareUpdateFailure.install);
        },
        onDeviceConnecting: (deviceAddress) => Logger.debug('deviceAddress: $deviceAddress, onDeviceConnecting'),
        onDeviceConnected: (deviceAddress) => Logger.debug('deviceAddress: $deviceAddress, onDeviceConnected'),
        onDfuProcessStarting: (deviceAddress) => Logger.debug('deviceAddress: $deviceAddress, onDfuProcessStarting'),
        onDfuProcessStarted: (deviceAddress) => Logger.debug('deviceAddress: $deviceAddress, onDfuProcessStarted'),
        onEnablingDfuMode: (deviceAddress) => Logger.debug('deviceAddress: $deviceAddress, onEnablingDfuMode'),
        onFirmwareValidating: (deviceAddress) => Logger.debug('address: $deviceAddress, onFirmwareValidating'),
        onDfuCompleted: (deviceAddress) {
          if (dfuFinished) return;
          dfuFinished = true;
          _firmwareTelemetry?.uploadFinished();
          // Nordic exposes the activate/reset completion as one callback.
          _firmwareTelemetry?.installRequested();
          unawaited(_verifyInstallation(btDevice));
        },
      );
    } catch (e) {
      if (dfuFinished) return;
      _firmwareTelemetry?.failed(failureClass: 'native_dfu_error');
      Logger.debug('Legacy DFU failed: $e');
      _fail(FirmwareUpdateFailure.install);
    }
  }

  Future<void> _verifyInstallation(BtDevice device) async {
    final attempt = _firmwareTelemetry;
    if (attempt == null || !mounted || isVerifying) return;
    final provider = Provider.of<DeviceProvider>(context, listen: false);
    setState(() => isVerifying = true);
    // Subscribe before resuming the existing native reconnect path. The stream
    // contains fresh DIS reads only, never the persisted pre-update revision.
    final verification = verifyFirmwareInstallation(
      observations: provider.firmwareRevisions,
      deviceId: device.id,
      fromVersion: attempt.fromVersion,
      targetVersion: latestFirmwareDetails['version']?.toString(),
    );
    // Killing the DFU owner must not extend the verification deadline.
    await killMcuUpdateManager().timeout(const Duration(seconds: 5), onTimeout: () {
      Logger.debug('DFU manager cleanup timed out; resuming reconnect verification');
    });
    provider.resetFirmwareUpdateState();
    final result = await verification;
    switch (result.outcome) {
      case FirmwareInstallOutcome.installed:
        attempt.completed(observedVersion: result.observedVersion!);
      case FirmwareInstallOutcome.notInstalled:
        attempt.failed(failureClass: 'not_installed');
      case FirmwareInstallOutcome.noReconnect:
        attempt.failed(failureClass: 'no_reconnect');
    }
    if (!mounted) return;
    setState(() {
      isVerifying = false;
      isInstalling = false;
      observedFirmwareVersion = result.observedVersion;
      isInstalled = result.outcome == FirmwareInstallOutcome.installed;
      updateFailure = switch (result.outcome) {
        FirmwareInstallOutcome.installed => null,
        FirmwareInstallOutcome.notInstalled => FirmwareUpdateFailure.notInstalled,
        FirmwareInstallOutcome.noReconnect => FirmwareUpdateFailure.noReconnect,
      };
    });
  }

  Future getLatestVersion({
    required String deviceModelNumber,
    required String firmwareRevision,
    required String hardwareRevision,
    required String manufacturerName,
    String? serialNumber,
  }) async {
    latestFirmwareDetails = await getLatestFirmwareVersion(
      deviceModelNumber: deviceModelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
      serialNumber: serialNumber,
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

  /// Downloads the firmware. Returns false (and sets [updateFailure]) when it could not.
  Future<bool> downloadFirmware() async {
    final zipUrl = latestFirmwareDetails['zip_url'];
    if (zipUrl == null) {
      Logger.debug('Error: zip_url is null in latestFirmwareDetails');
      _fail(FirmwareUpdateFailure.download);
      return false;
    }

    String dir = (await getApplicationDocumentsDirectory()).path;

    setState(() {
      isDownloading = true;
      isDownloaded = false;
      downloadProgress = 0;
      updateFailure = null;
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
          if (totalBytes != null && totalBytes > 0 && mounted) {
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
            if (mounted) {
              setState(() {
                isDownloading = false;
                isDownloaded = true;
                downloadProgress = 100;
              });
            }
            completer.complete();
          } catch (e) {
            completer.completeError(e);
          }
        },
        onError: (error) {
          Logger.debug('Download error: $error');
          completer.completeError(error);
        },
      );

      await completer.future;
      return true;
    } catch (e) {
      Logger.debug('Download error: $e');
      _fail(FirmwareUpdateFailure.download);
      return false;
    }
  }
}
