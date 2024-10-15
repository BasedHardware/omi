import 'package:flutter/material.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:provider/provider.dart';

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
        canPop: !provider.sdCardIsDownloading,
        onPopInvoked: (didPop) {
          // show dialog when downloading
        },
        child: Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            backgroundColor: Theme.of(context).colorScheme.primary,
            automaticallyImplyLeading: true,
            title: const Text('SD Card'),
            centerTitle: true,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_ios_new),
              onPressed: () {
                Navigator.pop(context);
              },
            ),
            elevation: 0,
          ),
          body: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                height: MediaQuery.sizeOf(context).height * 0.44,
                child: SdCardTransferProgress(
                  displayPercentage: provider.totalStorageFileBytes == 0
                      ? '0.0'
                      : (provider.totalBytesReceived / provider.totalStorageFileBytes * 100).toStringAsFixed(2),
                  progress: provider.sdCardSecondsReceived /
                      (provider.sdCardSecondsTotal == 0 ? 1 : provider.sdCardSecondsTotal),
                ),
              ),
              provider.sdCardIsDownloading
                  ? const SizedBox.shrink()
                  : ElevatedButton(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.white,
                      ),
                      onPressed: () {
                        // setState(() {
                        //   displayText =
                        //       'about $sdCardSecondsRemaining seconds remaining, about $percentageRemaining% there';
                        // });
                        if (!provider.sdCardIsDownloading) {
                          provider.sendStorage(deviceProvider.connectedDevice!.id);
                          provider.setSdCardIsDownloading(true);
                        }
                      },
                      child: const Text('Start Importing Memories'),
                    ),
              provider.sdCardDownloadDone
                  ? const Text('Done! Check back later for your memories.')
                  : Container(
                      width: double.maxFinite,
                      padding: const EdgeInsets.all(16.0),
                      margin: const EdgeInsets.all(16.0),
                      decoration: BoxDecoration(
                        color: Colors.grey.shade900,
                        borderRadius: BorderRadius.circular(16.0),
                      ),
                      child: const Text(
                        'This download may take a while. Exiting this while the download is in progress will halt all progress and some memories may be lost.\n\nPlease ensure that you have good internet connection.',
                        textAlign: TextAlign.center,
                      ),
                    ),
              const SizedBox(height: 20),
            ],
          ),
        ),
      );
    });
  }
}
