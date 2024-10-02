import 'package:flutter/material.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/services/translation_service.dart';

class SdCardCapturePage extends StatefulWidget {
  const SdCardCapturePage({super.key});

  @override
  State<SdCardCapturePage> createState() => _SdCardCapturePageState();
}

class _SdCardCapturePageState extends State<SdCardCapturePage> {
  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(builder: (context, provider, deviceProvider, child) {
      String sdCardSecondsRemaining = (provider.sdCardSecondsTotal - provider.sdCardSecondsReceived).toStringAsFixed(2);
      String percentageRemaining = provider.totalStorageFileBytes == 0
          ? '0.0'
          : (provider.totalBytesReceived / provider.totalStorageFileBytes * 100).toStringAsFixed(2);

      String displayText = TranslationService.translate( 'about')+' $sdCardSecondsRemaining '+TranslationService.translate('seconds remaining')+'\n$percentageRemaining%';
      if (provider.sdCardDownloadDone) {
        displayText = TranslationService.translate( 'Done! Check back later for your memories.');
      }

      return Scaffold(
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
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              LinearProgressIndicator(
                value: provider.sdCardSecondsReceived / (provider.sdCardSecondsTotal == 0 ? 1 : provider.sdCardSecondsTotal),
                backgroundColor: Colors.grey,
                color: Colors.green,
                minHeight: 10,
              ),
              const SizedBox(height: 20),
              Center(
                child: Text(displayText),
              ),
              const SizedBox(height: 20),
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.white,
                ),
                onPressed: () {
                  setState(() {
                    displayText = TranslationService.translate( 'about')+' $sdCardSecondsRemaining '+TranslationService.translate('seconds remaining')+'\n$percentageRemaining%';
                  });
                  if (!provider.sdCardIsDownloading) {
                    provider.sendStorage(deviceProvider.connectedDevice!.id);
                    provider.setSdCardIsDownloading(true);
                  }
                },
                child: Text(TranslationService.translate( 'Click to starting Importing Memories')),
              ),
              const SizedBox(height: 20),
               Text(
                TranslationService.translate( 'This download may take a while. Exiting this while the download is in progress will halt all progress and some memories may be lost.')),
              const SizedBox(height: 20),
               Text(TranslationService.translate( 'Please ensure that you have good internet connection.')),
            ],
          ),
        ),
      );
    });
  }
}
