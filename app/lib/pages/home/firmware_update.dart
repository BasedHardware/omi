import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/pages/home/firmware_mixin.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:intercom_flutter/intercom_flutter.dart';

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
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      setState(() {
        isLoading = true;
      });
      await getLatestVersion(deviceName: widget.device!.name);
      var (a, b) = await shouldUpdateFirmware(
          currentFirmware: widget.device!.info!.firmwareRevision, deviceName: widget.device!.name);
      if (mounted) {
        setState(() {
          shouldUpdate = b;
          updateMessage = a;
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
                                const Text(
                                  'Please restart the Friend device to complete the update',
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
                                  'Current Version: ${widget.device!.info!.firmwareRevision}',
                                  style: const TextStyle(color: Colors.white, fontSize: 16),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                  'Latest Version Available: ${latestFirmwareDetails['version']}',
                                  style: const TextStyle(color: Colors.white, fontSize: 16),
                                ),
                                const SizedBox(height: 16),
                                if (updateMessage == '0')
                                  TextButton(
                                    onPressed: () async {
                                      await Intercom.instance
                                          .displayArticle('9918118-updating-the-firmware-on-your-friend-device');
                                    },
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
                                          onPressed: () async {
                                            await downloadFirmware();
                                            await startDfu(widget.device!);
                                          },
                                          child: const Text(
                                            "Download Firmware",
                                            style: TextStyle(color: Colors.white, fontSize: 16),
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
