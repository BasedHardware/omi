import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/pages/memories/widgets/capture.dart';
import 'package:friend_private/pages/memory_capturing/page.dart';
import 'package:friend_private/pages/processing_memories/page.dart';
import 'package:friend_private/pages/sdcard/page.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
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
    return Consumer3<CaptureProvider, DeviceProvider, ConnectivityProvider>(
        builder: (context, provider, deviceProvider, connectivityProvider, child) {
      var topMemoryId =
          (provider.memoryProvider?.memories ?? []).isNotEmpty ? provider.memoryProvider!.memories.first.id : null;

      /// Friend V2 SD CARD functionality
      String totalsdCardSecondsRemainingString =
          (provider.sdCardSecondsTotal - provider.sdCardSecondsReceived).toStringAsFixed(2);

      if (provider.sdCardReady) {
        var banner = 'You have $totalsdCardSecondsRemainingString seconds of Storage Remaining. Click here to see';
        Future.delayed(Duration.zero, () {
          ScaffoldMessenger.of(context).hideCurrentMaterialBanner();
          ScaffoldMessenger.of(context).showMaterialBanner(
            MaterialBanner(
              content: Text(banner),
              backgroundColor: Colors.green,
              actions: [
                TextButton(
                  onPressed: () {
                    ScaffoldMessenger.of(context).hideCurrentMaterialBanner();
                    routeToPage(context, const SdCardCapturePage());
                  },
                  child: const Text('Click here'),
                ),
              ],
              onVisible: () => Future.delayed(const Duration(seconds: 15), () {
                ScaffoldMessenger.of(context).hideCurrentMaterialBanner();
              }),
            ),
          );
        });
        provider.setsdCardReady(false);
      }

      var header = _getMemoryHeader(context);
      if (header == null) {
        return const SizedBox.shrink();
      }

      return GestureDetector(
        onTap: () async {
          if (provider.segments.isEmpty) return;
          routeToPage(context, MemoryCapturingPage(topMemoryId: topMemoryId));
        },
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 16),
          width: double.maxFinite,
          decoration: BoxDecoration(
            color: Colors.grey.shade900,
            borderRadius: BorderRadius.circular(16.0),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                header,
                provider.segments.isNotEmpty
                    ? const Column(
                        children: [
                          SizedBox(height: 8),
                          LiteCaptureWidget(),
                          SizedBox(height: 8),
                        ],
                      )
                    : const SizedBox.shrink(),
              ],
            ),
          ),
        ),
      );
    });
  }

  _toggleRecording(BuildContext context, CaptureProvider provider) async {
    var recordingState = provider.recordingState;
    if (recordingState == RecordingState.record) {
      await provider.stopStreamRecording();
      context.read<CaptureProvider>().cancelMemoryCreationTimer();
      await context.read<CaptureProvider>().createMemory();
      MixpanelManager().phoneMicRecordingStopped();
    } else if (recordingState == RecordingState.initialising) {
      debugPrint('initialising, have to wait');
    } else {
      showDialog(
        context: context,
        builder: (c) => getDialog(
          context,
          () => Navigator.pop(context),
          () async {
            Navigator.pop(context);
            provider.updateRecordingState(RecordingState.initialising);
            await provider.changeAudioRecordProfile(BleAudioCodec.pcm16, 16000);
            await provider.streamRecording();
            MixpanelManager().phoneMicRecordingStarted();
          },
          'Limited Capabilities',
          'Recording with your phone microphone has a few limitations, including but not limited to: speaker profiles, background reliability.',
          okButtonText: 'Ok, I understand',
        ),
      );
    }
  }

  Widget? _getMemoryHeader(BuildContext context) {
    var provider = context.read<CaptureProvider>();
    var captureProvider = context.read<CaptureProvider>();
    var connectivityProvider = context.read<ConnectivityProvider>();

    bool internetConnectionStateOk = connectivityProvider.isConnected;
    bool deviceServiceStateOk = captureProvider.recordingDeviceServiceReady;
    bool transcriptServiceStateOk = captureProvider.transcriptServiceReady;
    bool isHavingCapturingMemory = provider.capturingProcessingMemory != null;
    bool isUsingPhoneMic = captureProvider.recordingState == RecordingState.record ||
        captureProvider.recordingState == RecordingState.initialising ||
        captureProvider.recordingState == RecordingState.pause;

    // Left
    Widget? left;
    if (isUsingPhoneMic || SharedPreferencesUtil().btDeviceStruct.id.isEmpty) {
      left = Center(
        child: getPhoneMicRecordingButton(
          context,
          () => _toggleRecording(context, captureProvider),
          captureProvider.recordingState,
        ),
      );
    } else if (deviceServiceStateOk && transcriptServiceStateOk) {
      left = Row(
        children: [
          const Text(
            '🎙️',
            style: TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600),
          ),
          const SizedBox(width: 12),
          Container(
            decoration: BoxDecoration(
              color: Colors.grey.shade800,
              borderRadius: BorderRadius.circular(16),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Text(
              captureProvider.segments.isNotEmpty ? 'In progress...' : 'Say something...',
              style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
              maxLines: 1,
            ),
          ),
        ],
      );
    } else if (isHavingCapturingMemory &&
        (!internetConnectionStateOk || !deviceServiceStateOk || !transcriptServiceStateOk)) {
      left = Row(
        children: [
          const Text(
            '🎙️',
            style: TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600),
          ),
          const SizedBox(width: 12),
          Container(
            decoration: BoxDecoration(
              color: Colors.grey.shade800,
              borderRadius: BorderRadius.circular(16),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Text(
              'Waiting for reconnect...',
              style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
              maxLines: 1,
            ),
          ),
        ],
      );
    }

    // Hide
    if (left == null) {
      return null;
    }

    // Right
    var stateText = "";
    if (deviceServiceStateOk && transcriptServiceStateOk) {
      stateText = "Listening";
    } else if (!internetConnectionStateOk) {
      stateText = "No connection";
    } else if (captureProvider.memoryCreating) {
      stateText = "Processing";
    }
    Widget right = stateText.isNotEmpty
        ? Expanded(
            child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              const SizedBox(
                width: 16,
                height: 16,
                child: RecordingStatusIndicator(),
              ),
              const SizedBox(width: 8),
              Text(
                stateText,
                style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                maxLines: 1,
                textAlign: TextAlign.end,
              )
            ],
          ))
        : const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(left: 0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          left,
          right,
        ],
      ),
    );
  }
}

class RecordingStatusIndicator extends StatefulWidget {
  const RecordingStatusIndicator({super.key});

  @override
  _RecordingStatusIndicatorState createState() => _RecordingStatusIndicatorState();
}

class _RecordingStatusIndicatorState extends State<RecordingStatusIndicator> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _opacityAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1000), // Blink every half second
      vsync: this,
    )..repeat(reverse: true);
    _opacityAnim = Tween<double>(begin: 1.0, end: 0.2).animate(_controller);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacityAnim,
      child: const Icon(Icons.fiber_manual_record, color: Colors.red, size: 16.0),
    );
  }
}

getPhoneMicRecordingButton(BuildContext context, toggleRecording, RecordingState state) {
  if (SharedPreferencesUtil().btDeviceStruct.id.isNotEmpty) return const SizedBox.shrink();
  return MaterialButton(
    onPressed: state == RecordingState.initialising ? null : toggleRecording,
    child: Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.start,
      crossAxisAlignment: CrossAxisAlignment.center,
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
          style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white, fontWeight: FontWeight.w600),
        ),
        const SizedBox(width: 4),
      ],
    ),
  );
}

Widget getMemoryCaptureWidget({ServerProcessingMemory? memory}) {
  return MemoryCaptureWidget(memory: memory);
}

Widget getProcessingMemoriesWidget(List<ServerProcessingMemory> memories) {
  if (memories.isEmpty) {
    return const SliverToBoxAdapter(child: SizedBox.shrink());
  }
  return SliverList(
    delegate: SliverChildBuilderDelegate(
      (context, index) {
        var pm = memories[index];
        if (pm.status == ServerProcessingMemoryStatus.processing) {
          return Padding(
            padding: const EdgeInsets.fromLTRB(0, 20, 0, 0),
            child: ProcessingMemoryWidget(memory: pm),
          );
        }
        if (pm.status == ServerProcessingMemoryStatus.done) {
          return const SizedBox.shrink();
        }

        return const SizedBox.shrink();
      },
      childCount: memories.length,
    ),
  );
}

// PROCESSING MEMORY

class ProcessingMemoryWidget extends StatefulWidget {
  final ServerProcessingMemory memory;

  const ProcessingMemoryWidget({
    super.key,
    required this.memory,
  });

  @override
  State<ProcessingMemoryWidget> createState() => _ProcessingMemoryWidgetState();
}

class _ProcessingMemoryWidgetState extends State<ProcessingMemoryWidget> {
  @override
  Widget build(BuildContext context) {
    return Consumer3<CaptureProvider, DeviceProvider, ConnectivityProvider>(
        builder: (context, provider, deviceProvider, connectivityProvider, child) {
      return GestureDetector(
          onTap: () async {
            if (widget.memory.transcriptSegments.isEmpty) return;
            routeToPage(
                context,
                ProcessingMemoryPage(
                  memory: widget.memory,
                ));
          },
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 16),
            width: double.maxFinite,
            decoration: BoxDecoration(
              color: Colors.grey.shade900,
              borderRadius: BorderRadius.circular(16.0),
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _getMemoryHeader(context),
                  widget.memory.transcriptSegments.isNotEmpty
                      ? Column(
                          children: [
                            const SizedBox(height: 8),
                            getLiteTranscriptWidget(
                              widget.memory.transcriptSegments,
                              [],
                              null,
                            ),
                            const SizedBox(height: 8),
                          ],
                        )
                      : const SizedBox.shrink(),
                ],
              ),
            ),
          ));
    });
  }

  _getMemoryHeader(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                ),
              ),
              const SizedBox(width: 20),
              Container(
                decoration: BoxDecoration(
                  color: Colors.grey.shade800,
                  borderRadius: BorderRadius.circular(16),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                child: Text(
                  'Processing',
                  style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
                  maxLines: 1,
                ),
              ),
            ],
          )
        ],
      ),
    );
  }
}
