import 'dart:io'; // Added for Platform check

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversations/widgets/capture.dart';
import 'package:omi/pages/conversation_capturing/page.dart';
import 'package:omi/pages/processing_conversations/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:provider/provider.dart';

class ConversationCaptureWidget extends StatefulWidget {
  const ConversationCaptureWidget({super.key});

  @override
  State<ConversationCaptureWidget> createState() => _ConversationCaptureWidgetState();
}

class _ConversationCaptureWidgetState extends State<ConversationCaptureWidget> {
  @override
  Widget build(BuildContext context) {
    return Consumer3<CaptureProvider, DeviceProvider, ConnectivityProvider>(
        builder: (context, provider, deviceProvider, connectivityProvider, child) {
      var topConvoId = (provider.conversationProvider?.conversations ?? []).isNotEmpty
          ? provider.conversationProvider!.conversations.first.id
          : null;

      var header = _getConversationHeader(context);
      if (header == null) {
        return const SizedBox.shrink();
      }

      // Check if we have local images to show notification
      bool hasLocalImages = provider.allImages.isNotEmpty;

      return GestureDetector(
        onTap: () async {
          // Allow navigation if we have segments OR local images
          if (provider.segments.isEmpty && !hasLocalImages) return;
          routeToPage(context, ConversationCapturingPage(topConversationId: topConvoId));
        },
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 16),
          width: double.maxFinite,
          decoration: BoxDecoration(
            color: Colors.grey.shade900,
            borderRadius: BorderRadius.circular(16.0),
            // Add a subtle border if images are available
            border: hasLocalImages 
                ? Border.all(color: Colors.blue.withOpacity(0.3), width: 1)
                : null,
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                header,
                // Show notification for local images
                hasLocalImages
                    ? Column(
                        children: [
                          const SizedBox(height: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                            decoration: BoxDecoration(
                              color: Colors.blue.withOpacity(0.2),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Row(
                              children: [
                                const Icon(Icons.camera_alt, color: Colors.blue, size: 16),
                                const SizedBox(width: 8),
                                Text(
                                  '${provider.allImages.length} live image${provider.allImages.length == 1 ? '' : 's'} received',
                                  style: const TextStyle(color: Colors.blue, fontSize: 12),
                                ),
                                const Spacer(),
                                const Text(
                                  'Tap to view →',
                                  style: TextStyle(color: Colors.blue, fontSize: 12, fontWeight: FontWeight.bold),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 8),
                        ],
                      )
                    : const SizedBox.shrink(),
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

    if (Platform.isMacOS) {
      if (recordingState == RecordingState.systemAudioRecord) {
        await provider.stopSystemAudioRecording();
        // MixpanelManager().track("System Audio Recording Stopped");
      } else if (recordingState == RecordingState.initialising) {
        debugPrint('initialising, have to wait');
      } else {
        await provider.streamSystemAudioRecording();
        // MixpanelManager().track("System Audio Recording Started");
      }
    } else {
      // Existing phone mic logic
      if (recordingState == RecordingState.record) {
        await provider.stopStreamRecording();
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
  }

  Widget? _getConversationHeader(BuildContext context) {
    var captureProvider = context.read<CaptureProvider>();
    var connectivityProvider = context.read<ConnectivityProvider>();
    var deviceProvider = context.read<DeviceProvider>();

    bool internetConnectionStateOk = connectivityProvider.isConnected;
    bool deviceServiceStateOk = captureProvider.recordingDeviceServiceReady;
    bool transcriptServiceStateOk = captureProvider.transcriptServiceReady;
    bool isHavingTranscript = captureProvider.segments.isNotEmpty;
    
    // Use real-time device state from DeviceProvider instead of cached SharedPreferencesUtil
    final connectedDevice = deviceProvider.connectedDevice;
    bool isHavingRecordingDevice = captureProvider.havingRecordingDevice;
    bool isHavingOmiDevice = connectedDevice != null && connectedDevice.type == DeviceType.omi;

    bool isUsingPhoneMic = captureProvider.recordingState == RecordingState.record ||
        captureProvider.recordingState == RecordingState.initialising ||
        captureProvider.recordingState == RecordingState.pause;

    // Left section logic
    Widget? left;
    
    // Show phone mic button if no Omi device is connected OR if actively using phone mic
    if (!isHavingOmiDevice || isUsingPhoneMic) {
      left = Center(
        child: getPhoneMicRecordingButton(
          context,
          () => _toggleRecording(context, captureProvider),
          captureProvider.recordingState,
        ),
      );
    } else if (isHavingOmiDevice && !deviceServiceStateOk) {
      // Omi device connected but not ready
      left = Row(
        children: [
          const Icon(Icons.record_voice_over),
          const SizedBox(width: 12),
          Flexible(
            child: Container(
              decoration: BoxDecoration(
                color: Colors.grey.shade800,
                borderRadius: BorderRadius.circular(16),
              ),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              child: Text(
                'Waiting for device...',
                style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),
        ],
      );
    } else {
      // Omi device connected and ready
      left = Row(
        children: [
          const Icon(Icons.record_voice_over),
          const SizedBox(width: 12),
          Flexible(
            child: Container(
              decoration: BoxDecoration(
                color: Colors.grey.shade800,
                borderRadius: BorderRadius.circular(16),
              ),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              child: Text(
                isHavingTranscript 
                    ? 'In progress...' 
                    : captureProvider.allImages.isNotEmpty
                        ? 'Images ready, say something...'
                        : 'Say something...',
                style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),
        ],
      );
    }

    // Right section logic
    Widget? statusIndicator;
    var stateText = "";
    
    if (isUsingPhoneMic) {
      // Phone mic is actively recording
      if (transcriptServiceStateOk) {
      var lastEvent = captureProvider.transcriptionServiceStatuses.lastOrNull;
      if (lastEvent?.status == "ready") {
        stateText = "Listening";
        statusIndicator = const RecordingStatusIndicator();
        } else {
          stateText = "Connecting";
        }
      } else if (!internetConnectionStateOk) {
        stateText = "Waiting for network";
      } else {
        stateText = "Connecting";
      }
    } else if (isHavingRecordingDevice) {
      // Device is recording
      if (transcriptServiceStateOk) {
        var lastEvent = captureProvider.transcriptionServiceStatuses.lastOrNull;
        if (lastEvent?.status == "ready") {
          stateText = "Capturing";
          statusIndicator = const RecordingStatusIndicator();
      } else {
        bool transcriptionDiagnosticEnabled = SharedPreferencesUtil().transcriptionDiagnosticEnabled;
        stateText = transcriptionDiagnosticEnabled ? (lastEvent?.statusText ?? "") : "Connecting";
      }
    } else if (!internetConnectionStateOk) {
      stateText = "Waiting for network";
      } else {
      stateText = "Connecting";
      }
    }

    return Padding(
      padding: const EdgeInsets.only(left: 0, right: 12),
      child: Row(
        children: [
          Expanded(
            flex: 3,
            child: left ?? const SizedBox.shrink(),
          ),
          if (stateText.isNotEmpty || statusIndicator != null)
            Expanded(
              flex: 2,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  Flexible(
                    child: Text(
                      stateText,
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                      maxLines: 1,
                      textAlign: TextAlign.end,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (statusIndicator != null) ...[
                    const SizedBox(width: 8),
                    SizedBox(
                      width: 16,
                      height: 16,
                      child: statusIndicator,
                    )
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class RecordingStatusIndicator extends StatefulWidget {
  const RecordingStatusIndicator({super.key});

  @override
  State<RecordingStatusIndicator> createState() => _RecordingStatusIndicatorState();
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


getPhoneMicRecordingButton(BuildContext context, VoidCallback toggleRecordingCb, RecordingState currentActualState) {
  if (SharedPreferencesUtil().btDevice.id.isNotEmpty && !Platform.isMacOS) {
    // If a BT device is configured and we are NOT on macOS, don't show this button.
    // On macOS, this button might be repurposed for system audio.
    return const SizedBox.shrink();
  }
  // If on macOS, AND a BT device is connected, this button should still be hidden
  // as the primary interaction should be via the BT device, not system audio as a fallback to phone mic.
  // This button is primarily for when NO BT device is the target.
  final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
  if (Platform.isMacOS &&
      deviceProvider.connectedDevice != null &&
      SharedPreferencesUtil().btDevice.id == deviceProvider.connectedDevice!.id) {
    return const SizedBox.shrink();
  }

  final bool isMac = Platform.isMacOS;
  String text;
  Widget icon;
  bool isLoading = currentActualState == RecordingState.initialising;

  if (isMac) {
    if (isLoading) {
      text = 'Initialising System Audio';
      icon = const SizedBox(
        height: 8,
        width: 8,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          color: Colors.white,
        ),
      );
    } else if (currentActualState == RecordingState.systemAudioRecord) {
      text = 'Stop Recording';
      icon = const Icon(Icons.stop, color: Colors.red, size: 12);
    } else {
      text = 'Start Recording';
      icon = const Icon(Icons.mic, size: 18);
    }
  } else {
    // Phone Mic
    if (isLoading) {
      text = 'Initialising Recorder';
      icon = const SizedBox(
        height: 8,
        width: 8,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          color: Colors.white,
        ),
      );
    } else if (currentActualState == RecordingState.record) {
      text = 'Stop Recording';
      icon = const Icon(Icons.stop, color: Colors.red, size: 12);
    } else {
      text = 'Try With Phone Mic';
      icon = const Icon(Icons.mic, size: 18);
    }
  }


  return MaterialButton(
    onPressed: isLoading ? null : toggleRecordingCb,
    child: Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        icon,
        const SizedBox(width: 4),
        Text(
          text,
          style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white, fontWeight: FontWeight.w500),
        ),
        const SizedBox(width: 4),
      ],
    ),
  );
}

Widget getProcessingConversationsWidget(List<ServerConversation> conversations) {
  // FIXME, this has to be a single one always, and also a conversation obj
  if (conversations.isEmpty) {
    return const SliverToBoxAdapter(child: SizedBox.shrink());
  }
  return SliverList(
    delegate: SliverChildBuilderDelegate(
      (context, index) {
        var pm = conversations[index];
        return Padding(
          padding: const EdgeInsets.fromLTRB(0, 20, 0, 0),
          child: ProcessingConversationWidget(conversation: pm),
        );
      },
      childCount: conversations.length,
    ),
  );
}

// PROCESSING CONVERSATION

class ProcessingConversationWidget extends StatefulWidget {
  final ServerConversation conversation;

  const ProcessingConversationWidget({
    super.key,
    required this.conversation,
  });

  @override
  State<ProcessingConversationWidget> createState() => _ProcessingConversationWidgetState();
}

class _ProcessingConversationWidgetState extends State<ProcessingConversationWidget> {
  @override
  Widget build(BuildContext context) {
    return Consumer3<CaptureProvider, DeviceProvider, ConnectivityProvider>(
        builder: (context, provider, deviceProvider, connectivityProvider, child) {
      return GestureDetector(
          onTap: () async {
            if (widget.conversation.transcriptSegments.isEmpty) return;
            routeToPage(
                context,
                ProcessingConversationPage(
                  conversation: widget.conversation,
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
                  _getConversationHeader(context),
                  widget.conversation.transcriptSegments.isNotEmpty
                      ? Column(
                          children: [
                            const SizedBox(height: 8),
                            getLiteTranscriptWidget(
                              widget.conversation.transcriptSegments,
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

  _getConversationHeader(BuildContext context) {
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
