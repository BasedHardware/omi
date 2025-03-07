import 'package:flutter/material.dart';
import 'firmware_update_dialog.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/pages/home/firmware_mixin.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/utils/analytics/intercom.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:gradient_borders/gradient_borders.dart';

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
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !isDownloading && !isInstalling,
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          title: const Text('Firmware Update'),
          backgroundColor: Theme.of(context).colorScheme.primary,
        ),
        body: Center(
          child: isLoading
              ? const CircularProgressIndicator(
                  color: Colors.white,
                )
              : Padding(
                  padding: const EdgeInsets.fromLTRB(14.0, 0, 14, 14),
                  child: isDownloading || isInstalling
                      ? Padding(
                          padding: const EdgeInsets.only(left: 10, right: 10, bottom: 60),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(isDownloading
                                  ? 'Downloading Firmware $downloadProgress%'
                                  : 'Installing Firmware $installProgress%'),
                              const SizedBox(height: 10),
                              LinearProgressIndicator(
                                value: (isInstalling ? installProgress : downloadProgress) / 100,
                                valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
                                backgroundColor: Colors.grey[800],
                              ),
                              const SizedBox(height: 18),
                              const Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                crossAxisAlignment: CrossAxisAlignment.center,
                                children: [
                                  Icon(Icons.warning, color: Colors.yellow),
                                  SizedBox(width: 10),
                                  Text(
                                    'Please do not close the app or turn off the device.\nIt could result in a corrupted device.',
                                    textAlign: TextAlign.center,
                                    style: TextStyle(color: Colors.white),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        )
                      : isInstalled
                          ? Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const Text('Firmware Updated Successfully'),
                                const SizedBox(height: 10),
                                Text(
                                  'Please restart your ${widget.device?.name ?? "Omi device"} to complete the update',
                                  textAlign: TextAlign.center,
                                ),
                                const SizedBox(height: 20),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                                  decoration: BoxDecoration(
                                    border: const GradientBoxBorder(
                                      gradient: LinearGradient(colors: [
                                        Color.fromARGB(127, 208, 208, 208),
                                        Color.fromARGB(127, 188, 99, 121),
                                        Color.fromARGB(127, 86, 101, 182),
                                        Color.fromARGB(127, 126, 190, 236)
                                      ]),
                                      width: 2,
                                    ),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: TextButton(
                                    style: TextButton.styleFrom(
                                      minimumSize: Size.zero,
                                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                    ),
                                    onPressed: () async {
                                      routeToPage(context, const HomePageWrapper(), replace: true);
                                    },
                                    child: const Text(
                                      "Finalize",
                                      style: TextStyle(color: Colors.white, fontSize: 16),
                                    ),
                                  ),
                                )
                              ],
                            )
                          : Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Text(
                                  'Current Version: ${widget.device!.firmwareRevision}',
                                  style: const TextStyle(color: Colors.white, fontSize: 16),
                                ),
                                const SizedBox(height: 8),
                                if (latestFirmwareDetails['version'] != null) ...[
                                  Text(
                                    'Latest Version Available: ${latestFirmwareDetails['version']}',
                                    style: const TextStyle(color: Colors.white, fontSize: 16),
                                  ),
                                  const SizedBox(height: 16),
                                ],
                                if (updateMessage == '0')
                                  TextButton(
                                    onPressed: () async {
                                      await IntercomManager.instance.displayFirmwareUpdateArticle();
                                    },
                                    style: TextButton.styleFrom(
                                      minimumSize: Size.zero,
                                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                    ),
                                    child: const Text(
                                      'Open Update Guide',
                                      style: TextStyle(
                                        color: Colors.white,
                                        fontSize: 16,
                                        decoration: TextDecoration.underline,
                                      ),
                                    ),
                                  ),
                                if (updateMessage != '0')
                                  Text(
                                    updateMessage,
                                    style: const TextStyle(color: Colors.white),
                                    textAlign: TextAlign.center,
                                  ),
                                const SizedBox(height: 20),
                                shouldUpdate
                                    ? Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                                        decoration: BoxDecoration(
                                          border: const GradientBoxBorder(
                                            gradient: LinearGradient(colors: [
                                              Color.fromARGB(127, 208, 208, 208),
                                              Color.fromARGB(127, 188, 99, 121),
                                              Color.fromARGB(127, 86, 101, 182),
                                              Color.fromARGB(127, 126, 190, 236)
                                            ]),
                                            width: 2,
                                          ),
                                          borderRadius: BorderRadius.circular(12),
                                        ),
                                        child: TextButton(
                                          style: TextButton.styleFrom(
                                            minimumSize: Size.zero,
                                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                          ),
                                          onPressed: () async {
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
                                            style: const TextStyle(color: Colors.white, fontSize: 16),
                                          ),
                                        ),
                                      )
                                    : const SizedBox.shrink(),
                              ],
                            ),
                ),
        ),
      ),
    );
  }
}
