import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/widgets/confirmation_dialog.dart';

import 'package:provider/provider.dart';

class ConversationCapturingPage extends StatefulWidget {
  final String? topConversationId;

  const ConversationCapturingPage({
    super.key,
    this.topConversationId,
  });

  @override
  State<ConversationCapturingPage> createState() => _ConversationCapturingPageState();
}

class _ConversationCapturingPageState extends State<ConversationCapturingPage> with TickerProviderStateMixin {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  TabController? _controller;
  late bool showSummarizeConfirmation;
  late AnimationController _animationController;
  bool _isMuted = false;

  @override
  void initState() {
    _controller = TabController(length: 2, vsync: this, initialIndex: 0);
    _controller!.addListener(() => setState(() {}));
    showSummarizeConfirmation = SharedPreferencesUtil().showSummarizeConfirmation;
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    )..repeat(reverse: true);
    super.initState();
  }

  Future<void> _toggleMute(CaptureProvider provider) async {
    if (_isMuted) {
      // Unmute - resume recording
      HapticFeedback.mediumImpact();
      setState(() {
        _isMuted = false;
      });

      if (PlatformService.isDesktop) {
        // Desktop - system audio
        await provider.resumeSystemAudioRecording();
      } else if (provider.havingRecordingDevice) {
        // Device recording (Omi device)
        await provider.resumeDeviceRecording();
      } else {
        // Phone mic
        await provider.streamRecording();
        MixpanelManager().phoneMicRecordingStarted();
      }
    } else {
      // Mute - pause recording with interesting haptic
      HapticFeedback.heavyImpact();
      await Future.delayed(const Duration(milliseconds: 80));
      HapticFeedback.lightImpact();
      setState(() {
        _isMuted = true;
      });

      if (PlatformService.isDesktop) {
        // Desktop - system audio
        await provider.pauseSystemAudioRecording();
      } else if (provider.havingRecordingDevice) {
        // Device recording (Omi device)
        await provider.pauseDeviceRecording();
      } else {
        // Phone mic
        await provider.stopStreamRecording();
        MixpanelManager().phoneMicRecordingStopped();
      }
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    _animationController.dispose();
    super.dispose();
  }

  int convertDateTimeToSeconds(DateTime dateTime) {
    DateTime now = DateTime.now();
    Duration difference = now.difference(dateTime);

    return difference.inSeconds;
  }

  String convertToHHMMSS(int seconds) {
    int hours = seconds ~/ 3600;
    int minutes = (seconds % 3600) ~/ 60;
    int remainingSeconds = seconds % 60;

    String twoDigits(int n) => n.toString().padLeft(2, '0');

    return '${twoDigits(hours)}:${twoDigits(minutes)}:${twoDigits(remainingSeconds)}';
  }

  Future<void> _stopConversation(CaptureProvider provider) async {
    if (provider.segments.isNotEmpty || provider.photos.isNotEmpty) {
      // Helper function to stop recording and process conversation
      Future<void> stopRecordingAndProcess() async {
        // Stop any active recording (phone mic or system audio)
        if (provider.recordingState == RecordingState.record) {
          await provider.stopStreamRecording();
        } else if (provider.recordingState == RecordingState.systemAudioRecord) {
          await provider.stopSystemAudioRecording();
        }
        // Then process the conversation
        provider.forceProcessingCurrentConversation();
      }

      if (!showSummarizeConfirmation) {
        await stopRecordingAndProcess();
        Navigator.of(context).pop();
        return;
      }
      showDialog(
        context: context,
        builder: (context) {
          return StatefulBuilder(
            builder: (context, setState) {
              final timeoutDuration = SharedPreferencesUtil().conversationSilenceDuration;
              String timeoutText;
              if (timeoutDuration == -1) {
                timeoutText = "Conversation will only end manually.";
              } else {
                final minutes = timeoutDuration ~/ 60;
                timeoutText =
                    "Conversation is summarized after $minutes minute${minutes == 1 ? '' : 's'} of no speech.";
              }

              return ConfirmationDialog(
                title: "Finished Conversation?",
                description:
                    "Are you sure you want to stop recording and summarize the conversation now?\n\nHints: $timeoutText",
                checkboxValue: !showSummarizeConfirmation,
                checkboxText: "Don't ask me again",
                onCheckboxChanged: (value) {
                  setState(() {
                    showSummarizeConfirmation = !value;
                  });
                },
                onCancel: () {
                  Navigator.of(context).pop();
                },
                onConfirm: () async {
                  SharedPreferencesUtil().showSummarizeConfirmation = showSummarizeConfirmation;
                  await stopRecordingAndProcess();
                  Navigator.of(context).pop();
                  Navigator.of(context).pop();
                },
              );
            },
          );
        },
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(
      builder: (context, provider, deviceProvider, child) {
        return PopScope(
          canPop: true,
          child: Scaffold(
            key: scaffoldKey,
            backgroundColor: Theme.of(context).colorScheme.primary,
            appBar: AppBar(
              automaticallyImplyLeading: false,
              backgroundColor: Theme.of(context).colorScheme.primary,
              title: Row(
                mainAxisSize: MainAxisSize.max,
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  IconButton(
                    onPressed: () {
                      Navigator.pop(context);
                      return;
                    },
                    icon: const Icon(Icons.arrow_back_rounded, size: 24.0),
                  ),
                  const SizedBox(width: 4),
                  Text(provider.photos.isNotEmpty ? "📸" : (_isMuted ? "🔇" : "🎙️")),
                  const SizedBox(width: 4),
                  Expanded(child: Text(_isMuted ? "Muted" : "Listening")),
                ],
              ),
            ),
            body: Column(
              children: [
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 0),
                    child: TabBarView(
                      controller: _controller,
                      physics: const NeverScrollableScrollPhysics(),
                      children: [
                        // Transcripts, photos
                        provider.segments.isEmpty && provider.photos.isEmpty
                            ? const Center(
                                child: Padding(
                                  padding: EdgeInsets.only(top: 50.0),
                                  child: Text("Waiting for transcript or photos..."),
                                ),
                              )
                            : getTranscriptWidget(
                                false,
                                provider.segments,
                                provider.photos,
                                deviceProvider.connectedDevice,
                                bottomMargin: 150,
                                suggestions: provider.suggestionsBySegmentId,
                                taggingSegmentIds: provider.taggingSegmentIds,
                                onAcceptSuggestion: (suggestion) {
                                  provider.assignSpeakerToConversation(suggestion.speakerId, suggestion.personId,
                                      suggestion.personName, [suggestion.segmentId]);
                                },
                                editSegment: (segmentId, speakerId) {
                                  final connectivityProvider =
                                      Provider.of<ConnectivityProvider>(context, listen: false);
                                  if (!connectivityProvider.isConnected) {
                                    ConnectivityProvider.showNoInternetDialog(context);
                                    return;
                                  }
                                  showModalBottomSheet(
                                      context: context,
                                      isScrollControlled: true,
                                      backgroundColor: Colors.black,
                                      shape: const RoundedRectangleBorder(
                                        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                                      ),
                                      builder: (context) {
                                        final suggestion = provider.suggestionsBySegmentId.values.firstWhere(
                                            (s) => s.speakerId == speakerId,
                                            orElse: () => SpeakerLabelSuggestionEvent.empty());
                                        return NameSpeakerBottomSheet(
                                          speakerId: speakerId,
                                          segmentId: segmentId,
                                          segments: provider.segments,
                                          suggestion: suggestion,
                                          onSpeakerAssigned: (speakerId, personId, personName, segmentIds) async {
                                            await provider.assignSpeakerToConversation(
                                                speakerId, personId, personName, segmentIds);
                                          },
                                        );
                                      });
                                },
                              ),
                        // Summary Tab
                        Center(
                          child: Padding(
                            padding:
                                const EdgeInsets.symmetric(horizontal: 32.0).copyWith(bottom: 50.0), // Adjust padding
                            child: Text(
                              provider.segments.isEmpty && provider.photos.isEmpty
                                  ? "No summary yet"
                                  : _getTimeoutDisplayText(),
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: provider.segments.isEmpty ? 16 : 22),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
            floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
            floatingActionButton: (provider.segments.isNotEmpty || provider.photos.isNotEmpty)
                ? Row(
                    mainAxisSize: MainAxisSize.min,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      // Process Now button
                      GestureDetector(
                        onTap: () => _stopConversation(provider),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                          decoration: BoxDecoration(
                            color: const Color(0xFFFFB800),
                            borderRadius: BorderRadius.circular(28),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.25),
                                spreadRadius: 2,
                                blurRadius: 8,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              FaIcon(
                                FontAwesomeIcons.stop,
                                color: Colors.black,
                                size: 16.0,
                              ),
                              SizedBox(width: 10),
                              Text(
                                'Process Now',
                                style: TextStyle(
                                  color: Colors.black,
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      // Mute button
                      GestureDetector(
                        onTap: () => _toggleMute(provider),
                        child: Container(
                          width: 52,
                          height: 52,
                          decoration: BoxDecoration(
                            color: _isMuted ? Colors.red : const Color(0xFF35343B),
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.25),
                                spreadRadius: 2,
                                blurRadius: 8,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: const Icon(
                            Icons.mic_off,
                            color: Colors.white,
                            size: 24,
                          ),
                        ),
                      ),
                    ],
                  )
                : null,
          ),
        );
      },
    );
  }

  String _getTimeoutDisplayText() {
    final timeoutDuration = SharedPreferencesUtil().conversationSilenceDuration;
    if (timeoutDuration == -1) {
      return "Conversation will only end manually 🤫";
    } else {
      final minutes = timeoutDuration ~/ 60;
      return "Conversation is summarized after $minutes minute${minutes == 1 ? '' : 's'} of no speech 🤫";
    }
  }
}

String transcriptElapsedTime(String timepstamp) {
  timepstamp = timepstamp.split(' - ')[1];
  return timepstamp;
}
