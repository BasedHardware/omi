/*import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/widgets/device_widget.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

import '../../utils/ble/communication.dart';

var storageMode = false;

class StorageManager extends StatefulWidget {
  // TODO: retrieve this from here instead of params
  final BTDeviceStruct? device;
  final int filesInStorage;

  const StorageManager({super.key, required this.device, required this.filesInStorage});

  @override
  State<StorageManager> createState() => _ConnectedDeviceState();
}

class _ConnectedDeviceState extends State<StorageManager> {
  @override
  void initState() {
    super.initState();
  }

  void _toggleStorageMode() {
    setState(() {
      storageMode = !storageMode;
      print("Storage mode: $storageMode");
    });
  }

  @override
  Widget build(BuildContext context) {
    var deviceId = widget.device?.id ?? SharedPreferencesUtil().deviceId;
    var deviceConnected = widget.device != null;

    return FutureBuilder<void>(
      future: Future.delayed(Duration(seconds: 1)),
      builder: (BuildContext context, AsyncSnapshot<void> snapshot) {
        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            title: Text(deviceConnected ? 'Files in Storage' : 'Device Unpaired'),
            backgroundColor: Theme.of(context).colorScheme.primary,
            actions: [
              deviceConnected
                  ? IconButton(
                onPressed: () {
                },
                icon: const Icon(Icons.settings),
              )
                  : const SizedBox.shrink(),
            ],
          ),
          body: Column(
            children: [
              const SizedBox(height: 32),
              const DeviceAnimationWidget(),
              Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisAlignment: MainAxisAlignment.start,
                children: [
                  widget.device != null
                      ? Container(
                      decoration: BoxDecoration(
                        color: Colors.transparent,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Column(
                        children: [
                          Text(
                            'Current mode: ${storageMode ? "Storage" : "Normal"}',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 16.0,
                              fontWeight: FontWeight.w500,
                              height: 1.5,
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 12),
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.insert_drive_file,
                                color: widget.filesInStorage > 15
                                    ? Colors.red
                                    : widget.filesInStorage > 5
                                    ? Colors.yellow.shade700
                                    : const Color.fromARGB(255, 0, 255, 8),
                                size: 24, // Size of the icon
                              ),
                              const SizedBox(width: 8.0),
                              Text(
                                '${widget.filesInStorage.toString()} files pending',
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          )
                        ],
                      ))
                      : const SizedBox.shrink()
                ],
              ),
              const SizedBox(height: 32),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
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
                    _toggleStorageMode();
                    await setStorageMode(deviceId, storageMode ? 2 : 1);
                    Navigator.of(context).pop();
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text('Your Friend is ${storageMode? "reading files" : "in normal mode"}'),
                    ));
                  },
                  child: Text(
                    storageMode ? "Normal mode" : "Storage mode",
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class StorageInfo {
}*/


import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/widgets/device_widget.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';

import '../../utils/ble/communication.dart';

var storageMode = false;

class StorageManager extends StatefulWidget {
  final BTDeviceStruct? device;
  final int filesInStorage;

  const StorageManager({super.key, required this.device, required this.filesInStorage});

  @override
  State<StorageManager> createState() => _StorageManagerState();
}

class _StorageManagerState extends State<StorageManager> {
  void _toggleStorageMode() {
    setState(() {
      storageMode = !storageMode;
    });
  }

  @override
  Widget build(BuildContext context) {
    var deviceId = widget.device?.id ?? SharedPreferencesUtil().deviceId;
    var deviceConnected = widget.device != null;

    return FutureBuilder<void>(
      future: Future.delayed(Duration(seconds: 1)),
      builder: (BuildContext context, AsyncSnapshot<void> snapshot) {
        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            title: Text(deviceConnected ? 'Files in Storage' : 'Device Unpaired'),
            backgroundColor: Theme.of(context).colorScheme.primary,
            actions: [
              deviceConnected
                  ? IconButton(
                onPressed: () {},
                icon: const Icon(Icons.settings),
              )
                  : const SizedBox.shrink(),
            ],
          ),
          body: Column(
            children: [
              const SizedBox(height: 32),
              const DeviceAnimationWidget(),
              Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                mainAxisAlignment: MainAxisAlignment.start,
                children: [
                  widget.device != null
                      ? Container(
                      decoration: BoxDecoration(
                        color: Colors.transparent,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Column(
                        children: [
                          Text(
                            'Current mode: ${storageMode ? "Storage" : "Normal"}',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 16.0,
                              fontWeight: FontWeight.w500,
                              height: 1.5,
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 12),
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.insert_drive_file,
                                color: widget.filesInStorage > 15
                                    ? Colors.red
                                    : widget.filesInStorage > 5
                                    ? Colors.yellow.shade700
                                    : const Color.fromARGB(255, 0, 255, 8),
                                size: 24,
                              ),
                              const SizedBox(width: 8.0),
                              Text(
                                '${widget.filesInStorage.toString()} files pending',
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          )
                        ],
                      ))
                      : const SizedBox.shrink()
                ],
              ),
              const SizedBox(height: 32),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
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
                    _toggleStorageMode();
                    await setStorageMode(deviceId, storageMode ? 2 : 1);
                    Navigator.of(context).pop();
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(
                          'Your Friend is ${storageMode ? "reading files" : "in normal mode"}'),
                    ));
                  },
                  child: Text(
                    storageMode ? "Normal mode" : "Storage mode",
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}