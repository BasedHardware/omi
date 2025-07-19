import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:nordic_dfu/nordic_dfu.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/http/api/device.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/manifest/manifest.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';
import 'package:http/http.dart' as http;
import 'package:mcumgr_flutter/mcumgr_flutter.dart' as mcumgr;
import 'package:flutter_archive/flutter_archive.dart';

mixin FirmwareMixin<T extends StatefulWidget> on State<T> {
  Map latestFirmwareDetails = {};
  bool isDownloading = false;
  bool isDownloaded = false;
  int downloadProgress = 1;
  bool isInstalling = false;
  bool isInstalled = false;
  int installProgress = 1;
  bool isLegacySecureDFU = true;
  List<String> otaUpdateSteps = [];
  final mcumgr.FirmwareUpdateManagerFactory? managerFactory = mcumgr.FirmwareUpdateManagerFactory();

  /// Process ZIP file and return firmware image list
  Future<List<mcumgr.Image>> processZipFile(Uint8List zipFileData) async {
    // Create temporary directory
    final prefix = 'firmware_${Uuid().v4()}';
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
      await ZipFile.extractToDirectory(
        zipFile: firmwareFile,
        destinationDir: destinationDir,
      );

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
        final image = mcumgr.Image(
          image: file.image,
          data: firmwareFileData,
        );
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

  Future<void> updateFirmware(BtDevice btDevice, {bool fileInAssets = false, String? zipFilePath}) async {
    if (btDevice.type == DeviceType.openglass) {
      return startOpenGlassOta(btDevice, zipFilePath);
    }
    
    if (isLegacySecureDFU) {
      return startLegacyDfu(btDevice, fileInAssets: fileInAssets);
    }
    return startMCUDfu(btDevice, fileInAssets: fileInAssets, zipFilePath: zipFilePath);
  }

  Future<void> startMCUDfu(BtDevice btDevice, {bool fileInAssets = false, String? zipFilePath}) async {
    setState(() {
      isInstalling = true;
    });
    await Provider.of<DeviceProvider>(context, listen: false).prepareDFU();
    await Future.delayed(const Duration(seconds: 2));

    String firmwareFile = zipFilePath ?? '${(await getApplicationDocumentsDirectory()).path}/firmware.zip';
    final bytes = await File(firmwareFile).readAsBytes();
    const configuration = mcumgr.FirmwareUpgradeConfiguration(
      estimatedSwapTime: Duration(seconds: 0),
      eraseAppSettings: true,
      pipelineDepth: 1,
    );
    final updateManager = await managerFactory!.getUpdateManager(btDevice.id);
    final images = await processZipFile(bytes);

    final updateStream = updateManager.setup();

    updateStream.listen((state) {
      if (state == mcumgr.FirmwareUpgradeState.success) {
        debugPrint('update success');
        setState(() {
          isInstalling = false;
          isInstalled = true;
        });
      } else {
        debugPrint('update state: $state');
      }
    });

    updateManager.progressStream.listen((progress) {
      debugPrint('progress: $progress');
      setState(() {
        installProgress = (progress.bytesSent / progress.imageSize * 100).round();
      });
    });

    updateManager.logger.logMessageStream
        .where((log) => log.level.rawValue > 1) // Filter debug messages
        .listen((log) {
      debugPrint('dfu log: ${log.message}');
    });

    await updateManager.update(
      images,
      configuration: configuration,
    );
  }

  Future<void> startLegacyDfu(BtDevice btDevice, {bool fileInAssets = false}) async {
    setState(() {
      isInstalling = true;
    });
    await Provider.of<DeviceProvider>(context, listen: false).prepareDFU();
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
      onError: (deviceAddress, error, errorType, message) {
        debugPrint('deviceAddress: $deviceAddress, error: $error, errorType: $errorType, message: $message');
        setState(() {
          isInstalling = false;
        });
        // Reset firmware update state on error
        final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
        deviceProvider.resetFirmwareUpdateState();
      },
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

  Future<void> startOpenGlassOta(BtDevice btDevice, String? zipFilePath) async {
    debugPrint('Starting OpenGlass OTA with file: $zipFilePath');
    setState(() {
      isInstalling = true;
      installProgress = 0;
    });

    // Check if firmware file exists and is valid
    final zipFile = File(zipFilePath!);
    if (!await zipFile.exists()) {
      setState(() {
        isInstalling = false;
      });
      throw Exception('Firmware file not found at $zipFilePath');
    }

    // Check file size to ensure it's not empty
    final fileSize = await zipFile.length();
    if (fileSize == 0) {
      setState(() {
        isInstalling = false;
      });
      throw Exception('Firmware file is empty');
    }

    try {
      // Extract the zip and locate the bin
      final tempDir = await getTemporaryDirectory();
      final extractDir = Directory('${tempDir.path}/glass_ota');
     await extractFirmware(zipFilePath, extractDir.path);
     final extractedFiles = await extractDir.list().toList();
      final binFile = extractedFiles.firstWhere(
        (file) => file.path.toLowerCase().endsWith('.bin'),
        orElse: () => throw Exception('No .bin file found in the ZIP archive'),
      );
      final binFilePath = binFile.path;

      // connect to device
      final deviceConnection = await ServiceManager.instance().device.ensureConnection(btDevice.id);
      if (deviceConnection == null) {
        throw Exception('Failed to connect to device');
      }
      
      // discover services and characteristics
      final services = await deviceConnection.bleDevice.discoverServices();
      const otaServiceUuid = '0000ffe5-0000-1000-8000-00805f9b34fb';
      const otaServiceShortUuid = 'ffe5';
      const dataCharacteristicUuid = '0000ffe9-0000-1000-8000-00805f9b34fb';
      const dataCharacteristicShortUuid = 'ffe9';
      const controlCharacteristicUuid = '0000ffe4-0000-1000-8000-00805f9b34fb';
      const controlCharacteristicShortUuid = 'ffe4';
      
      final otaService = services.firstWhere(
        (service) => service.uuid.toString().toLowerCase() == otaServiceShortUuid || 
                     service.uuid.toString().toLowerCase().contains(otaServiceUuid),
        orElse: () => throw Exception('OTA service not found on device'),
      );
      
      final dataCharacteristic = otaService.characteristics.firstWhere(
        (char) => char.uuid.toString().toLowerCase() == dataCharacteristicShortUuid || 
                  char.uuid.toString().toLowerCase().contains(dataCharacteristicUuid),
        orElse: () => throw Exception('OTA data characteristic not found'),
      );
      
      final controlCharacteristic = otaService.characteristics.firstWhere(
        (char) => char.uuid.toString().toLowerCase() == controlCharacteristicShortUuid || 
                  char.uuid.toString().toLowerCase().contains(controlCharacteristicUuid),
        orElse: () => throw Exception('OTA control characteristic not found'),
      );

      // send chunks of data to the device
      const chunkSize = 480;
      int sentBytes = 0;
      int chunkIndex = 0;
      
      // read the binary file once before the loop
      final binFileBytes = await File(binFilePath).readAsBytes();
      final fileSize = binFileBytes.length;
      
      try {

        // write and wait for device to initialize
        await controlCharacteristic.write([0x01], withoutResponse: false);
        await Future.delayed(const Duration(milliseconds: 1000));

        // send chunks 
        while (sentBytes < fileSize) {
          // check if device is still connected
          if (!deviceConnection.bleDevice.isConnected) {
            throw Exception('Device disconnected during OTA transfer');
          }
          
          // calculate chunk size, extract chunk from binary and send to device
          final remainingBytes = fileSize - sentBytes;
          final currentChunkSize = remainingBytes > chunkSize ? chunkSize : remainingBytes;
          final chunk = binFileBytes.sublist(sentBytes, sentBytes + currentChunkSize);
          
          // retry mechanism for chunk writing
          bool chunkSent = false;
          int retryCount = 0;
          const maxRetries = 3;
          
          while (!chunkSent && retryCount < maxRetries) {
            try {
              await dataCharacteristic.write(chunk, withoutResponse: false);
              chunkSent = true;
            } catch (e) {
              retryCount++;
              debugPrint('Chunk write failed (attempt $retryCount/$maxRetries): $e');
              
              if (retryCount < maxRetries) {
                await Future.delayed(Duration(milliseconds: 100 * retryCount));
                if (!deviceConnection.bleDevice.isConnected) {
                  throw Exception('Device disconnected during retry');
                }
              } else {
                throw Exception('Failed to send chunk after $maxRetries attempts: $e');
              }
            }
          }
          
          // update progress
          sentBytes += currentChunkSize;
          final progress = (sentBytes / fileSize * 100).round();
          debugPrint('Sent chunk $chunkIndex: $currentChunkSize bytes, total: $sentBytes/$fileSize ($progress%)');
          setState(() {
            installProgress = progress;
          });
          
          // small delay to prevent overwhelming the device
          await Future.delayed(const Duration(milliseconds: 10));
          chunkIndex++;
          debugPrint('Sent bytes: $sentBytes/$fileSize ($progress%)');
        }
        
        // send OTA end command (0x03)
        await controlCharacteristic.write([0x03], withoutResponse: false);
        debugPrint('Sent OTA end command');
        
        // wait for device to process the update
        await Future.delayed(const Duration(seconds: 2));

        // TODO: add more checks
        // 1. wait for device to connect
        // 2. check the device firmware version

        setState(() {
          isInstalling = false;
          isInstalled = true;
          installProgress = 100;
        });
        
        debugPrint('OTA update completed successfully');
      } catch (e) {
        if (e.toString().contains('Device is disconnected') && 
            installProgress >= 99) {
          
          setState(() {
            isInstalling = false;
            isInstalled = true;
            installProgress = 100;
          });
          
          return;
        }
        
        debugPrint('OTA update failed: $e');
        throw Exception('OTA update failed: $e');
      }
      
      // clean up extracted files
      await extractDir.delete(recursive: true);
      
      setState(() {
        isInstalling = false;
        isInstalled = true;
        installProgress = 100;
      });
      
      debugPrint('OTA update completed successfully');
    } catch (e) {
      setState(() {
        isInstalling = false;
      });
      debugPrint('OTA update failed: $e');
      throw Exception('OTA update failed: $e');
    }
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
    if (latestFirmwareDetails['is_legacy_secure_dfu'] != null) {
      isLegacySecureDFU = latestFirmwareDetails['is_legacy_secure_dfu'];
    }
  }

  Future<(String, bool, String)> shouldUpdateFirmware({required String currentFirmware}) async {
    return DeviceUtils.shouldUpdateFirmware(
        currentFirmware: currentFirmware, latestFirmwareDetails: latestFirmwareDetails);
  }

  Future downloadFirmware(String savePath) async {
    final zipUrl = latestFirmwareDetails['zip_url'];
    if (zipUrl == null) {
      debugPrint('Error: zip_url is null in latestFirmwareDetails');
      setState(() {
        isDownloading = false;
      });
      // Reset firmware update state on error
      final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
      deviceProvider.resetFirmwareUpdateState();
      return;
    }

    debugPrint('Downloading firmware from: $zipUrl');
    var httpClient = http.Client();
    var request = http.Request('GET', Uri.parse(zipUrl));
    var response = httpClient.send(request);
    
    // Delete existing file if it exists
    final existingFile = File(savePath);
    if (await existingFile.exists()) {
      await existingFile.delete();
      debugPrint('Deleted existing firmware file');
    }

    List<List<int>> chunks = [];
    int downloaded = 0;
    setState(() {
      isDownloading = true;
      isDownloaded = false;
    });

    final Completer<void> completer = Completer<void>();
    
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
        try {
          // Display percentage of completion
          debugPrint('downloadPercentage: ${downloaded / r.contentLength! * 100}');

          // Save the file
          File file = File(savePath);
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
          completer.complete();
        } catch (e) {
          setState(() {
            isDownloading = false;
            isDownloaded = false;
          });
          completer.completeError(e);
        }
      }, onError: (error) {
        setState(() {
          isDownloading = false;
          isDownloaded = false;
        });
        completer.completeError(error);
      });
    }, onError: (error) {
      debugPrint('Download error: $error');
      setState(() {
        isDownloading = false;
      });
      // Reset firmware update state on error
      final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
      deviceProvider.resetFirmwareUpdateState();
    });

    await completer.future;
  }

  Future<void> extractFirmware(String zipFilePath, String extractPath) async {
    debugPrint('Extracting firmware from: $zipFilePath to: $extractPath');
    
    // Ensure extract directory exists
    final extractDir = Directory(extractPath);
    if (!await extractDir.exists()) {
      await extractDir.create(recursive: true);
    }

    try {
      // Extract the ZIP file to a temporary location first
      final tempDir = await getTemporaryDirectory();
      final tempExtractDir = Directory('${tempDir.path}/temp_extract_${DateTime.now().millisecondsSinceEpoch}');
      await tempExtractDir.create();

      final zipFile = File(zipFilePath);
      await ZipFile.extractToDirectory(
        zipFile: zipFile,
        destinationDir: tempExtractDir,
      );

      // Now move all files from the temporary extraction to the target path
      // This flattens the directory structure
      await _flattenDirectory(tempExtractDir, extractDir);

      // Clean up temporary directory
      await tempExtractDir.delete(recursive: true);
      
      debugPrint('Firmware extraction completed successfully');
    } catch (e) {
      debugPrint('Error extracting firmware: $e');
      throw Exception('Failed to extract firmware: $e');
    }
  }

  // Helper function to flatten directory structure
  Future<void> _flattenDirectory(Directory sourceDir, Directory targetDir) async {
    await for (final entity in sourceDir.list(recursive: true)) {
      if (entity is File) {
        final fileName = entity.path.split('/').last;
        final targetFile = File('${targetDir.path}/$fileName');
        await entity.copy(targetFile.path);
        debugPrint('Extracted file: $fileName');
      }
    }
  }
}
