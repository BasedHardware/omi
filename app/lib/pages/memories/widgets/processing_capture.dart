import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/memories/widgets/capture.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/utils/enums.dart';
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
          constraints: BoxConstraints(maxHeight: provider.hasTranscripts ? 350 : 90),
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

  _getMemoryHeader(BuildContext context) {
    // Connected device
    var connectedDevice = context.read<DeviceProvider>().connectedDevice;
    var connectedDeviceText = "";
    if (connectedDevice != null) {
      var deviceName = connectedDevice?.name ?? SharedPreferencesUtil().deviceName;
      var deviceShortId = "${connectedDevice?.getShortId() ?? SharedPreferencesUtil().btDeviceStruct.getShortId()}";
      connectedDeviceText = '$deviceName ($deviceShortId)';
    }

    // Recording
    var captureProvider = context.read<CaptureProvider>();
    var stateText = ((captureProvider.audioStorage?.frames ?? []).length > 0 ||
                captureProvider.recordingState == RecordingState.record) &&
            (connectedDevice != null)
        ? "Listening"
        : "";

    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Container(
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
            child: connectedDevice != null
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
                        connectedDeviceText,
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
          const SizedBox(
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

Widget getMemoryCaptureWidget({ServerProcessingMemory? memory}) {
  return MemoryCaptureWidget(memory: memory);
}
