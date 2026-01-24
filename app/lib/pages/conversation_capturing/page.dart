import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/widgets/confirmation_dialog.dart';

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
                timeoutText = context.l10n.conversationEndsManually;
              } else {
                final minutes = timeoutDuration ~/ 60;
                timeoutText =
                    context.l10n.conversationSummarizedAfterMinutes(minutes, minutes == 1 ? '' : 's');
              }

              return ConfirmationDialog(
                title: context.l10n.finishedConversation,
                description:
                    "${context.l10n.stopRecordingConfirmation}\n\n${context.l10n.hints(timeoutText)}",
                checkboxValue: !showSummarizeConfirmation,
                checkboxText: context.l10n.dontAskAgain,
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
              backgroundColor: Theme.of(context).colorScheme.surface,
              elevation: 0,
              centerTitle: false,
              toolbarHeight: 60,
              title: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 36,
                        height: 36,
                        decoration: const BoxDecoration(
                          color: Color(0xFF1F1F25),
                          shape: BoxShape.circle,
                        ),
                        child: IconButton(
                          padding: EdgeInsets.zero,
                          onPressed: () {
                            Navigator.pop(context);
                          },
                          icon: const Icon(
                            Icons.arrow_back_rounded,
                            size: 20,
                            color: Colors.white70,
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      const Text(
                        "Live Transcription",
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                  if (provider.segments.isNotEmpty || provider.photos.isNotEmpty)
                    GestureDetector(
                      onTap: () => _stopConversation(provider),
                      child: Container(
                        height: 36,
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        decoration: BoxDecoration(
                          color: Colors.red,
                          borderRadius: BorderRadius.circular(18),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: const [
                            Icon(Icons.stop_circle, color: Colors.white, size: 16),
                            SizedBox(width: 6),
                            Text(
                              'Stop',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 15,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
            ),
            body: provider.segments.isEmpty && provider.photos.isEmpty
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
          ),
        );
      },
    );
  }

  String _getTimeoutDisplayText(BuildContext context) {
    final timeoutDuration = SharedPreferencesUtil().conversationSilenceDuration;
    if (timeoutDuration == -1) {
      return "${context.l10n.conversationEndsManually} 🤫";
    } else {
      final minutes = timeoutDuration ~/ 60;
      return "${context.l10n.conversationSummarizedAfterMinutes(minutes, minutes == 1 ? '' : 's')} 🤫";
    }
  }
}

String transcriptElapsedTime(String timepstamp) {
  timepstamp = timepstamp.split(' - ')[1];
  return timepstamp;
}
