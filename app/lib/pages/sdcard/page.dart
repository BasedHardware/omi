import 'dart:io';

import 'package:flutter/material.dart';
import 'package:upgrader/upgrader.dart';
import 'package:provider/provider.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/utils/other/temp.dart';
class SdCardCapturePage extends StatefulWidget {

  const SdCardCapturePage({
    super.key
  });

  @override
  State<SdCardCapturePage> createState() => _SdCardCapturePageState();

}

class _SdCardCapturePageState extends State<SdCardCapturePage> {
  late String _displayText;
  @override 
  void initState() {
    _displayText = 'hello there';
    super.initState();
  }

  @override
  Widget build(BuildContext context) {

    return Consumer2<CaptureProvider, DeviceProvider>(builder: (context, provider, deviceProvider, child) {

    var connectedDevice = deviceProvider.connectedDevice;
    var totalStorageBytes = provider.totalStorageFileBytes ?? 1; // Avoid division by zero
    var totalReceivedBytes = provider.totalBytesReceived ?? 1;

    var storageBytes = provider.timeToSend ?? 1;
    var totalTimeSent = provider.timeAlreadySent ?? 1;
    var totalTimeRemaining = storageBytes - totalTimeSent;
    String totalTimeRemainingString = totalTimeRemaining.toStringAsFixed(2);
    String percentRemaining = (totalReceivedBytes / totalStorageBytes * 100).toStringAsFixed(2);
    _displayText =  'about ' + totalTimeRemainingString + ' seconds remaining\n' + percentRemaining + '% there';
    if (provider.isDone) {
      _displayText = 'Done! Check back later for your memories.';
    }
    // if(provider.sendNotification) {
    //   provider.sendNotification = false;
    // }

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
            value: totalTimeSent / storageBytes,
            backgroundColor: Colors.grey,
            color: Colors.green,
            minHeight: 10,
          ),
          const SizedBox(height: 20),
          Center(
            child: Text(_displayText ?? 'Default Text'),
          ),
          const SizedBox(height: 20),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.white,
            ),
            onPressed: () {
              setState(() {
                 _displayText = 'about' + totalTimeRemainingString + ' seconds remaining, about ' + percentRemaining + '% there';               
              });
              // if (provider.totalStorageFileBytes == 0) {
              // }
              if (!provider.sdCardIsDownloading) {
                provider.sendStorage(deviceProvider.connectedDevice!.id);
                provider.setSdCardIsDownloading(true);
              }
            },
            child: const Text('Click to starting Importing Memories'),
          ),
          const SizedBox(height: 20),
          const Text('This download may take a while. Exiting this while the download is in progress will halt all progress and some memories may be lost.'),
          const SizedBox(height: 20),
          const Text('Please ensure that you have good internet connection.'),
        ],
      ),
    ),
    );

    });
  }

}