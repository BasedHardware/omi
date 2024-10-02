import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/home/firmware_mixin.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:intercom_flutter/intercom_flutter.dart';
import 'package:friend_private/services/translation_service.dart';

class FirmwareUpdate extends StatefulWidget {
  final DeviceInfo deviceInfo;
  final BTDeviceStruct? device;

  const FirmwareUpdate({super.key, required this.deviceInfo, this.device});

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
          currentFirmware: widget.deviceInfo.firmwareRevision, deviceName: widget.device!.name);
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
          title:  Text(TranslationService.translate( 'Firmware Update')),
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
                                  ? TranslationService.translate( 'Downloading Firmware $downloadProgress%')
                                  : TranslationService.translate( 'Installing Firmware $installProgress%')),
                              const SizedBox(height: 10),
                              LinearProgressIndicator(
                                value: (isInstalling ? installProgress : downloadProgress) / 100,
                                valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
                                backgroundColor: Colors.grey[800],
                              ),
                              const SizedBox(height: 18),
                               Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                crossAxisAlignment: CrossAxisAlignment.center,
                                children: [
                                  const Icon(Icons.warning, color: Colors.yellow),
                                  const SizedBox(width: 10),
                                  Text(
                                    TranslationService.translate( 'Please do not close the app or turn off the device.\nIt could result in a corrupted device.'),
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(color: Colors.white),
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
                                 Text(TranslationService.translate( 'Firmware Updated Successfully')),
                                const SizedBox(height: 10),
                                 Text(
                                  TranslationService.translate( 'Please restart the Friend device to complete the update'),
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
                                    child:  Text(
                                      TranslationService.translate( "Finalize"),
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
                                    '${TranslationService.translate( 'Current Version:')} ${widget.deviceInfo.firmwareRevision}',
                                  style: const TextStyle(color: Colors.white, fontSize: 16),
                                ),
                                const SizedBox(height: 8),
                                Text(
                                    '${TranslationService.translate( 'Latest Version Available:')} ${latestFirmwareDetails['version']}',
                                  style: const TextStyle(color: Colors.white, fontSize: 16),
                                ),
                                const SizedBox(height: 16),
                                if (updateMessage == '0')
                                  TextButton(
                                    onPressed: () async {
                                      await Intercom.instance
                                          .displayArticle('9918118-updating-the-firmware-on-your-friend-device');
                                    },
                                    child:  Text(
                                      TranslationService.translate( 'Open Update Guide'),
                                      style: const TextStyle(
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
                                          child:  Text(
                                            TranslationService.translate( "Download Firmware"),
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
