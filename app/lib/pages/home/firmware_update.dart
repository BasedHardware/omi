import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'firmware_update_dialog.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/firmware_mixin.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:provider/provider.dart';

class FirmwareUpdate extends StatefulWidget {
  final BtDevice? device;

  const FirmwareUpdate({super.key, this.device});

  @override
  State<FirmwareUpdate> createState() => _FirmwareUpdateState();
}

class _FirmwareUpdateState extends State<FirmwareUpdate> with FirmwareMixin {
  bool shouldUpdate = false;
  String updateMessage = '';
  bool isLoading = false;

  // Store reference to provider for safe disposal
  DeviceProvider? _deviceProvider;

  @override
  void initState() {
    var device = widget.device!;

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      setState(() {
        isLoading = true;
      });

      await getLatestVersion(
        deviceModelNumber: device.modelNumber,
        firmwareRevision: device.firmwareRevision,
        hardwareRevision: device.hardwareRevision,
        manufacturerName: device.manufacturerName,
      );
      var result = await shouldUpdateFirmware(currentFirmware: widget.device!.firmwareRevision);
      if (mounted) {
        setState(() {
          shouldUpdate = result.$2;
          updateMessage = result.$1;
          isLoading = false;
        });
      }
    });
    super.initState();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Save reference to provider for safe access in dispose
    _deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
  }

  @override
  void dispose() {
    // Defer the reset to after the frame completes to avoid calling
    // notifyListeners() while the widget tree is locked
    final provider = _deviceProvider;
    if (provider != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        provider.resetFirmwareUpdateState();
      });
    }
    super.dispose();
  }

  Future<void> _selectLocalFirmwareFile() async {
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['zip'],
      );

      if (result != null) {
        String filePath = result.files.single.path!;
        await startDfu(widget.device!, zipFilePath: filePath);
      }
    } catch (e) {
      debugPrint('Error selecting firmware file: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error selecting firmware file: $e')),
        );
      }
    }
  }

  Widget _buildProgressSection() {
    return Card(
      color: Colors.black.withOpacity(0.2),
      elevation: 2.0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: Colors.white.withOpacity(0.1)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              isDownloading ? 'Downloading Firmware' : 'Installing Firmware',
              style: const TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w600,
                color: Colors.white,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '${isDownloading ? downloadProgress : installProgress}%',
              style: const TextStyle(
                fontSize: 36,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
            const SizedBox(height: 16),
            Stack(
              children: [
                Container(
                  height: 8,
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
                LayoutBuilder(builder: (context, constraints) {
                  return AnimatedContainer(
                    duration: const Duration(milliseconds: 300),
                    height: 8,
                    width: constraints.maxWidth * ((isInstalling ? installProgress : downloadProgress) / 100),
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          Colors.purpleAccent.shade100,
                          Colors.deepPurple.shade300,
                        ],
                      ),
                      borderRadius: BorderRadius.circular(4),
                    ),
                  );
                }),
              ],
            ),
            const SizedBox(height: 24),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.yellow.withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.yellow.withOpacity(0.3)),
              ),
              child: const Row(
                children: [
                  Icon(Icons.warning_rounded, color: Colors.yellow, size: 24),
                  SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Please do not close the app or turn off the device.\nIt could result in a corrupted device.',
                      style: TextStyle(
                        color: Colors.yellow,
                        fontSize: 14,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSuccessSection() {
    return Card(
      color: Colors.black.withOpacity(0.2),
      elevation: 2.0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: Colors.white.withOpacity(0.1)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.check_circle_outline_rounded,
              color: Colors.green,
              size: 64,
            ),
            const SizedBox(height: 16),
            const Text(
              'Firmware Updated Successfully',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              'Please restart your ${widget.device?.name ?? "Omi device"} to complete the update',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 16,
                color: Colors.white.withOpacity(0.8),
              ),
            ),
            const SizedBox(height: 24),
            Container(
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [
                    Color.fromARGB(127, 208, 208, 208),
                    Color.fromARGB(127, 188, 99, 121),
                    Color.fromARGB(127, 86, 101, 182),
                    Color.fromARGB(127, 126, 190, 236),
                  ],
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Container(
                margin: const EdgeInsets.all(2),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primary,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: TextButton(
                  style: TextButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                  ),
                  onPressed: () async {
                    // Reset firmware update state before navigating
                    final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
                    deviceProvider.resetFirmwareUpdateState();
                    routeToPage(context, const HomePageWrapper(), replace: true);
                  },
                  child: const Text(
                    "Done",
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUpdateSection() {
    dynamic changelogData = latestFirmwareDetails['changelog'];
    bool hasChangelog = changelogData != null && changelogData is List && (List<String>.from(changelogData)).isNotEmpty;

    return Card(
      color: Colors.black.withOpacity(0.2),
      elevation: 2.0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: Colors.white.withOpacity(0.1)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Column(
                  children: [
                    Text(
                      'Current Version',
                      style: TextStyle(
                        fontSize: 14,
                        color: Colors.white.withOpacity(0.6),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Icon(Icons.memory, size: 20, color: Colors.deepPurple.shade100),
                        const SizedBox(width: 8),
                        Text(
                          widget.device!.firmwareRevision,
                          style: const TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
                if (latestFirmwareDetails['version'] != null) ...[
                  Icon(Icons.arrow_forward_ios_rounded, size: 20, color: Colors.white.withOpacity(0.4)),
                  Column(
                    children: [
                      Text(
                        'Latest Version',
                        style: TextStyle(
                          fontSize: 14,
                          color: Colors.white.withOpacity(0.6),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Icon(Icons.system_update_alt_rounded, size: 20, color: Colors.purpleAccent.shade100),
                          const SizedBox(width: 8),
                          Text(
                            '${latestFirmwareDetails['version']}',
                            style: const TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ],
              ],
            ),
            const SizedBox(height: 24),
            if (hasChangelog) ...[
              Theme(
                data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  iconColor: Colors.white.withOpacity(0.6),
                  collapsedIconColor: Colors.white.withOpacity(0.6),
                  tilePadding: EdgeInsets.zero,
                  title: Text(
                    'View Changelog',
                    style: TextStyle(
                      color: Colors.deepPurple.shade50,
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 8.0, bottom: 16.0, left: 16.0, right: 16.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          ...(List<String>.from(changelogData)).map((change) => Padding(
                                padding: const EdgeInsets.only(bottom: 6.0),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Padding(
                                      padding: const EdgeInsets.only(right: 10.0, top: 5.0),
                                      child:
                                          Icon(Icons.fiber_manual_record, size: 8, color: Colors.deepPurple.shade100),
                                    ),
                                    Expanded(
                                      child: Text(
                                        change,
                                        style:
                                            TextStyle(color: Colors.white.withOpacity(0.8), fontSize: 14, height: 1.3),
                                      ),
                                    ),
                                  ],
                                ),
                              )),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
            ],
            if (updateMessage != '0') ...[
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.05),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.white.withOpacity(0.1))),
                child: Row(
                  children: [
                    Icon(Icons.info_outline_rounded, color: Colors.purpleAccent.shade100, size: 20),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        updateMessage,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          height: 1.4,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
            ],
            if (updateMessage == '0') ...[
              TextButton.icon(
                onPressed: () async {
                  await IntercomManager.instance.displayFirmwareUpdateArticle();
                },
                icon: Icon(Icons.help_outline, color: Colors.white.withOpacity(0.8)),
                label: Text(
                  'Open Update Guide',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.8),
                    fontSize: 15,
                    decoration: TextDecoration.underline,
                  ),
                ),
              ),
              const SizedBox(height: 16),
            ],
            if (shouldUpdate) ...[
              const SizedBox(height: 16),
              Container(
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [
                      Color.fromARGB(127, 208, 208, 208),
                      Color.fromARGB(127, 188, 99, 121),
                      Color.fromARGB(127, 86, 101, 182),
                      Color.fromARGB(127, 126, 190, 236),
                    ],
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Container(
                  margin: const EdgeInsets.all(2),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.primary,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: TextButton(
                    style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                    onPressed: () async {
                      // Set firmware update in progress when starting update
                      final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
                      deviceProvider.setFirmwareUpdateInProgress(true);

                      if (otaUpdateSteps.isEmpty) {
                        await downloadFirmware();
                        await startDfu(widget.device!);
                      } else {
                        showDialog(
                          context: context,
                          builder: (context) => FirmwareUpdateDialog(
                            steps: otaUpdateSteps,
                            onUpdateStart: () async {
                              await downloadFirmware();
                              await startDfu(widget.device!);
                            },
                          ),
                        );
                      }
                    },
                    child: Text(
                      otaUpdateSteps.isEmpty ? "Start Update" : "Update",
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !isDownloading && !isInstalling,
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          title: const Text(
            'Firmware Update',
            style: TextStyle(fontWeight: FontWeight.w600),
          ),
          backgroundColor: Colors.transparent,
          elevation: 0,
        ),
        body: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: isLoading
                  ? Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const CircularProgressIndicator(color: Colors.white),
                        const SizedBox(height: 16),
                        Text(
                          'Checking for updates...',
                          style: TextStyle(color: Colors.white.withOpacity(0.8)),
                        ),
                      ],
                    )
                  : isDownloading || isInstalling
                      ? _buildProgressSection()
                      : isInstalled
                          ? _buildSuccessSection()
                          : _buildUpdateSection(),
            ),
          ),
        ),
      ),
    );
  }
}
