import 'package:flutter/material.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

import 'about_sdcard_sync.dart';
import 'sdcard_transfer_progress.dart';

class SdCardCapturePage extends StatefulWidget {
  const SdCardCapturePage({super.key});

  @override
  State<SdCardCapturePage> createState() => _SdCardCapturePageState();
}

class _SdCardCapturePageState extends State<SdCardCapturePage> {
  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(builder: (context, provider, deviceProvider, child) {
      return PopScope(
        canPop: true,
        onPopInvoked: (didPop) {
          // show dialog when downloading
          // I don't think this is necessary, the only situation that will cause this to fail is if the user exits the app or restarts it
        },
        child: Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            backgroundColor: Theme.of(context).colorScheme.primary,
            automaticallyImplyLeading: true,
            title: const Text('SD Card Sync'),
            centerTitle: true,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_ios_new),
              onPressed: () {
                Navigator.pop(context);
              },
            ),
            elevation: 0,
            actions: [
              IconButton(
                icon: const Icon(Icons.help_outline),
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (context) => const AboutSdCardSync(),
                    ),
                  );
                },
              ),
            ],
          ),
          body: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                height: MediaQuery.sizeOf(context).height * 0.365,
                child: SdCardTransferProgress(
                  displayPercentage: provider.totalStorageFileBytes == 0
                      ? '0.0'
                      : ((provider.currentTotalBytesReceived) / provider.totalStorageFileBytes * 100)
                          .toStringAsFixed(2),
                  progress: provider.currentSdCardSecondsReceived /
                      (provider.sdCardSecondsTotal == 0 ? 1 : provider.sdCardSecondsTotal),
                  secondsRemaining:
                      (provider.sdCardSecondsTotal - provider.currentSdCardSecondsReceived).toStringAsFixed(2),
                ),
              ),
              provider.sdCardIsDownloading || provider.sdCardDownloadDone
                  ? const SizedBox.shrink()
                  : Container(
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
                      child: ElevatedButton(
                        onPressed: () {
                          if (!provider.sdCardIsDownloading) {
                            provider.sendStorage(deviceProvider.connectedDevice!.id);
                            provider.setSdCardIsDownloading(true);
                          }
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.transparent,
                          shadowColor: const Color.fromARGB(255, 17, 17, 17),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        child: Container(
                          width: 200,
                          height: 45,
                          alignment: Alignment.center,
                          child: const Text(
                            'Import Audio Files',
                            style: TextStyle(
                              fontWeight: FontWeight.w400,
                              fontSize: 16,
                              color: Color.fromARGB(255, 255, 255, 255),
                            ),
                          ),
                        ),
                      ),
                    ),
              const SizedBox(
                height: 20,
              ),
              Container(
                padding: const EdgeInsets.all(16.0),
                margin: const EdgeInsets.all(16.0),
                decoration: BoxDecoration(
                  color: Colors.grey.shade900,
                  borderRadius: BorderRadius.circular(16.0),
                ),
                child: provider.sdCardDownloadDone
                    ? const Text(
                        'Audio files have been imported successfully!\n\nMemories will appear once they have been created on the server. You can now continue with recording your conversations.',
                        textAlign: TextAlign.center)
                    : const Text(
                        'Importing audio files might take some time. Please keep the app open to avoid any interruptions and ensure you have a stable internet connection',
                        textAlign: TextAlign.center,
                      ),
              ),
              Container(
                padding: const EdgeInsets.all(16.0),
                margin: const EdgeInsets.only(left: 16.0, right: 16.0),
                decoration: BoxDecoration(
                  color: Colors.grey.shade900,
                  borderRadius: BorderRadius.circular(16.0),
                ),
                child: const ListTile(
                  leading: Icon(
                    Icons.warning,
                    color: Colors.yellow,
                  ),
                  title: Text('No conversation will be recorded until the import is complete'),
                ),
              ),
            ],
          ),
        ),
      );
    });
  }
}
