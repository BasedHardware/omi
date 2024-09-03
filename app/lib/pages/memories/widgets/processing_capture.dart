import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/capture/connect.dart';
import 'package:friend_private/pages/home/device.dart';
import 'package:friend_private/pages/memories/widgets/capture.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

class MemoryCaptureWidget extends StatefulWidget {
  final ServerProcessingMemory? memory;

  const MemoryCaptureWidget({
    super.key,
    required this.memory,
  });

  @override
  State<MemoryCaptureWidget> createState() => _MemoryCaptureWidgetState();
}

class _MemoryCaptureWidgetState extends State<MemoryCaptureWidget> {
  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(builder: (context, provider, deviceProvider, child) {
      return GestureDetector(
        child: Container(
          constraints: BoxConstraints(maxHeight: provider.hasTranscripts ? 350 : 100),
          margin: const EdgeInsets.only(top: 12, left: 8, right: 8),
          width: double.maxFinite,
          decoration: const BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.all(Radius.circular(16)),
            border: GradientBoxBorder(
              gradient: LinearGradient(colors: [
                Color.fromARGB(127, 208, 208, 208),
                Color.fromARGB(127, 188, 99, 121),
                Color.fromARGB(127, 86, 101, 182),
                Color.fromARGB(127, 126, 190, 236)
              ]),
              width: 1,
            ),
            shape: BoxShape.rectangle,
          ),
          child: Padding(
            padding: const EdgeInsetsDirectional.all(16),
            child: Column(
              mainAxisSize: MainAxisSize.max,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _getMemoryHeader(context),
                const SizedBox(height: 16),
                const Expanded(
                  child: CustomScrollView(
                    slivers: [
                      SliverToBoxAdapter(child: SizedBox(height: 32)),
                      SliverToBoxAdapter(
                        child: CaptureWidget(),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    });
  }

  _recordingToggled(BuildContext context, CaptureProvider provider) async {
    var recordingState = provider.recordingState;
    if (recordingState == RecordingState.record) {
      if (Platform.isAndroid) {
        provider.stopStreamRecordingOnAndroid();
      } else {
        provider.stopStreamRecording();
      }
      provider.updateRecordingState(RecordingState.stop);
      context.read<CaptureProvider>().cancelMemoryCreationTimer();
      await context.read<CaptureProvider>().createMemory();
    } else if (recordingState == RecordingState.initialising) {
      debugPrint('initialising, have to wait');
    } else {
      showDialog(
        context: context,
        builder: (c) => getDialog(
          context,
          () => Navigator.pop(context),
          () async {
            provider.updateRecordingState(RecordingState.initialising);
            provider.closeWebSocket();
            await provider.initiateWebsocket(BleAudioCodec.pcm16, 16000);
            if (Platform.isAndroid) {
              await provider.streamRecordingOnAndroid();
            } else {
              await provider.startStreamRecording();
            }
            Navigator.pop(context);
          },
          'Limited Capabilities',
          'Recording with your phone microphone has a few limitations, including but not limited to: speaker profiles, background reliability.',
          okButtonText: 'Ok, I understand',
        ),
      );
    }
  }

  _getMemoryHeader(BuildContext context) {
    // Connected device
    var deviceProvider = context.read<DeviceProvider>();
    var deviceText = "";
    if (deviceProvider.connectedDevice != null) {
      var deviceName = deviceProvider.connectedDevice?.name ?? SharedPreferencesUtil().deviceName;
      var deviceShortId =
          deviceProvider.connectedDevice?.getShortId() ?? SharedPreferencesUtil().btDeviceStruct.getShortId();
      deviceText = '$deviceName ($deviceShortId)';
    }

    // Recording
    var captureProvider = context.read<CaptureProvider>();
    var stateText = ((captureProvider.audioStorage?.frames ?? []).isNotEmpty ||
                captureProvider.recordingState == RecordingState.record) &&
            (deviceProvider.connectedDevice != null)
        ? "Listening"
        : "";

    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          GestureDetector(
            onTap: () async {
              if (SharedPreferencesUtil().btDeviceStruct.id.isEmpty) {
                routeToPage(context, const ConnectDevicePage());
                MixpanelManager().connectFriendClicked();
              } else {
                await routeToPage(context,
                    ConnectedDevice(device: deviceProvider.connectedDevice, batteryLevel: deviceProvider.batteryLevel));
              }
            },
            child: Container(
              decoration: const BoxDecoration(
                color: Colors.black,
                borderRadius: BorderRadius.all(Radius.circular(16)),
                border: GradientBoxBorder(
                  gradient: LinearGradient(colors: [
                    Color.fromARGB(127, 208, 208, 208),
                    Color.fromARGB(127, 188, 99, 121),
                    Color.fromARGB(127, 86, 101, 182),
                    Color.fromARGB(127, 126, 190, 236)
                  ]),
                  width: 1,
                ),
                shape: BoxShape.rectangle,
              ),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              child: deviceProvider.connectedDevice != null
                  ? Row(
                      children: [
                        Image.asset(
                          "assets/images/recording_green_circle_icon.png",
                          width: 10,
                          height: 10,
                        ),
                        const SizedBox(
                          width: 4,
                        ),
                        Text(
                          deviceText,
                          style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
                          maxLines: 1,
                        )
                      ],
                    )
                  : context.read<DeviceProvider>().isConnecting
                      ? Text(
                          "Connecting",
                          style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
                        )
                      : Text(
                          "No device found",
                          style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
                        ),
            ),
          ),
          // mic
          deviceProvider.connectedDevice == null && !deviceProvider.isConnecting
              ? Row(
                  children: [
                    getPhoneMicRecordingButton(
                        context, () => _recordingToggled(context, captureProvider), captureProvider.recordingState),
                  ],
                )
              : const SizedBox(
                  width: 16,
                ),
          Expanded(
            child: Text(
              stateText,
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
              maxLines: 1,
              textAlign: TextAlign.end,
            ),
          )
        ],
      ),
    );
  }
}

getPhoneMicRecordingButton(BuildContext context, recordingToggled, RecordingState state) {
  if (SharedPreferencesUtil().btDeviceStruct.id.isNotEmpty) return const SizedBox.shrink();
  return MaterialButton(
    onPressed: state == RecordingState.initialising ? null : recordingToggled,
    child: Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.start,
      children: [
        state == RecordingState.initialising
            ? const SizedBox(
                height: 8,
                width: 8,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: Colors.white,
                ),
              )
            : (state == RecordingState.record
                ? const Icon(Icons.stop, color: Colors.red, size: 12)
                : const Icon(Icons.mic, size: 18)),
        const SizedBox(width: 4),
        Text(
          state == RecordingState.initialising
              ? 'Initialising Recorder'
              : (state == RecordingState.record ? 'Stop Recording' : 'Try With Phone Mic'),
          style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
        ),
        const SizedBox(width: 4),
      ],
    ),
  );
}

Widget getMemoryCaptureWidget({ServerProcessingMemory? memory}) {
  return MemoryCaptureWidget(memory: memory);
}
