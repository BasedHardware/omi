import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/bt_device.dart';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';
import 'package:friend_private/widgets/scanning_animation.dart';
import 'package:friend_private/widgets/scanning_ui.dart';
import 'widgets/transcript.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:intl/intl.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';

class DevicePage extends StatefulWidget {
  final Function refreshMemories;
  final BTDeviceStruct? device;
  final int batteryLevel;
  final GlobalKey<TranscriptWidgetState> transcriptChildWidgetKey;

  const DevicePage({
    super.key,
    required this.device,
    required this.refreshMemories,
    required this.transcriptChildWidgetKey,
    required this.batteryLevel,
  });

  @override
  State<DevicePage> createState() => _DevicePageState();
}

class _DevicePageState extends State<DevicePage> {
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _checkMemorySchemaUpdated();
  }

  Future<void> _checkMemorySchemaUpdated() async {
    SharedPreferences prefs = await SharedPreferences.getInstance();
    bool isMemorySchemaUpdated = prefs.getBool('isMemorySchemaUpdated') ?? false;

    if (!isMemorySchemaUpdated) {
      debugPrint("Updating Memory Schema in Pinecone");
      await updateCreatedAtToEpoch();
      await prefs.setBool('isMemorySchemaUpdated', true);
    }

    setState(() {
      _isLoading = false;
    });
  }

  Future<void> updateCreatedAtToEpoch() async {
    List<MemoryRecord> memoryRecords = await MemoryStorage.getAllMemories();
    DateFormat dateFormat = DateFormat("yyyy-MM-dd HH:mm:ss.SSSSSS");

    for (MemoryRecord memoryRecord in memoryRecords) {
      DateTime dateTime = dateFormat.parse(memoryRecord.createdAt.toString());
      int timestamp = dateTime.millisecondsSinceEpoch ~/ 1000;
      updateCreatedAtInPinecone(memoryRecord.id, timestamp);
    }
  }

  @override
  Widget build(BuildContext context) {
    return _isLoading
        ? const Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                CircularProgressIndicator(),
                SizedBox(height: 16),
                Text(
                  'Updating Memory Schema, do not close',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          )
        : ListView(children: [
            ..._getConnectedDeviceWidgets(),
            TranscriptWidget(
              btDevice: widget.device,
              key: widget.transcriptChildWidgetKey,
              refreshMemories: widget.refreshMemories,
            ),
            const SizedBox(height: 16)
          ]);
  }

  _getConnectedDeviceWidgets() {
    if (widget.device == null) {
      return [
        const SizedBox(height: 64),
        const ScanningAnimation(),
        const ScanningUI(
          string1: 'Looking for Friend wearable',
          string2: 'Locating your Friend device. Keep it near your phone for pairing',
        ),
      ];
    }
    return [
      const SizedBox(height: 64),
      const Center(
          child: ScanningAnimation(
        sizeMultiplier: 0.4,
      )),
      const SizedBox(height: 16),
      const Center(
          child: Text(
        'Connected Device',
        style: TextStyle(
            fontFamily: 'SF Pro Display',
            color: Colors.white,
            fontSize: 29.0,
            letterSpacing: 0.0,
            fontWeight: FontWeight.w700,
            height: 1.2),
        textAlign: TextAlign.center,
      )),
      const SizedBox(height: 8),
      Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            '${widget.device?.name ?? 'Friend'} ~ ${widget.device?.id.split('-').last.substring(0, 6)}',
            style: const TextStyle(
              color: Color.fromARGB(255, 255, 255, 255),
              fontSize: 16.0,
              fontWeight: FontWeight.w500,
              height: 1.5,
            ),
            textAlign: TextAlign.center,
          ),
          widget.batteryLevel == -1 ? const SizedBox.shrink() : const SizedBox(width: 16.0),
          widget.batteryLevel == -1
              ? const SizedBox.shrink()
              : Container(
                  decoration: BoxDecoration(
                    color: Colors.transparent,
                    borderRadius: BorderRadius.circular(30),
                    border: Border.all(
                      color: Colors.white,
                      width: 1,
                    ),
                  ),
                  padding: const EdgeInsets.all(8.0),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '${widget.batteryLevel.toString()}%',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(width: 8.0),
                      Container(
                        width: 10,
                        height: 10,
                        decoration: BoxDecoration(
                          color: widget.batteryLevel > 75
                              ? const Color.fromARGB(255, 0, 255, 8)
                              : widget.batteryLevel > 20
                                  ? Colors.yellow.shade700
                                  : Colors.red,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ],
                  ),
                )
        ],
      ),
    ];
  }
}
