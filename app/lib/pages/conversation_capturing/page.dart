import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
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
import 'package:omi/widgets/photo_viewer_page.dart';

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
  final ScrollController _timelineScrollController = ScrollController();

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
    _timelineScrollController.dispose();
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
                timeoutText = context.l10n.conversationSummarizedAfterMinutes(minutes, minutes == 1 ? '' : 's');
              }

              return ConfirmationDialog(
                title: context.l10n.finishedConversation,
                description: "${context.l10n.stopRecordingConfirmation}\n\n${context.l10n.hints(timeoutText)}",
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
                  Expanded(
                      child: Text(provider.photos.isNotEmpty
                          ? 'Capturing'
                          : (_isMuted ? context.l10n.muted : context.l10n.listening))),
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
                            ? Center(
                                child: Padding(
                                  padding: const EdgeInsets.only(top: 50.0),
                                  child: Text(context.l10n.waitingForTranscriptOrPhotos),
                                ),
                              )
                            : provider.photos.isNotEmpty
                                ? _buildChronologicalTimeline(provider)
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
                                  ? context.l10n.noSummaryYet
                                  : _getTimeoutDisplayText(context),
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
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const FaIcon(
                                FontAwesomeIcons.stop,
                                color: Colors.black,
                                size: 16.0,
                              ),
                              const SizedBox(width: 10),
                              Text(
                                context.l10n.processNow,
                                style: const TextStyle(
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

  /// Builds a chronological timeline interleaving photo groups and transcript segments.
  Widget _buildChronologicalTimeline(CaptureProvider provider) {
    final photos = List<ConversationPhoto>.from(provider.photos)..sort((a, b) => a.createdAt.compareTo(b.createdAt));
    final segments = provider.segments;

    // Group consecutive photos taken within 30 seconds of each other
    final List<List<ConversationPhoto>> photoGroups = [];
    if (photos.isNotEmpty) {
      List<ConversationPhoto> currentGroup = [photos.first];
      for (int i = 1; i < photos.length; i++) {
        if (photos[i].createdAt.difference(photos[i - 1].createdAt).inSeconds <= 30) {
          currentGroup.add(photos[i]);
        } else {
          photoGroups.add(currentGroup);
          currentGroup = [photos[i]];
        }
      }
      photoGroups.add(currentGroup);
    }

    final totalItems = photoGroups.length + segments.length;

    // Auto-scroll to bottom after frame renders
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_timelineScrollController.hasClients) {
        _timelineScrollController.jumpTo(_timelineScrollController.position.maxScrollExtent);
      }
    });

    return ListView.builder(
      controller: _timelineScrollController,
      padding: const EdgeInsets.only(top: 16, bottom: 180),
      itemCount: totalItems,
      itemBuilder: (context, index) {
        // Show photo groups first, then transcript below
        if (index < photoGroups.length) {
          return _buildPhotoGroupTimelineItem(photoGroups[index], photos);
        }
        final segIndex = index - photoGroups.length;
        if (segIndex >= segments.length) return const SizedBox.shrink();
        return _buildTranscriptTimelineItem(segments[segIndex], provider);
      },
    );
  }

  Widget _buildPhotoGroupTimelineItem(List<ConversationPhoto> group, List<ConversationPhoto> allPhotos) {
    final firstPhoto = group.first;
    final timeStr =
        '${firstPhoto.createdAt.hour.toString().padLeft(2, '0')}:${firstPhoto.createdAt.minute.toString().padLeft(2, '0')}';
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          // Camera icon avatar
          Column(
            children: [
              const CircleAvatar(
                radius: 16,
                backgroundColor: Color(0xFF2A5D3E),
                child: Icon(Icons.camera_alt, size: 16, color: Colors.white70),
              ),
              const SizedBox(height: 2),
            ],
          ),
          const SizedBox(width: 8),
          // Photo group bubble
          Flexible(
            child: Container(
              constraints: BoxConstraints(
                maxWidth: MediaQuery.of(context).size.width * 0.7,
              ),
              decoration: BoxDecoration(
                color: const Color(0xFF1A3D2E),
                borderRadius: BorderRadius.circular(18),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.15),
                    blurRadius: 4,
                    offset: const Offset(0, 1),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Grid of photos in this group
                  ClipRRect(
                    borderRadius: const BorderRadius.only(
                      topLeft: Radius.circular(18),
                      topRight: Radius.circular(18),
                    ),
                    child: group.length == 1
                        ? GestureDetector(
                            onTap: () => _openPhotoViewer(allPhotos, allPhotos.indexOf(group.first)),
                            child: Image.memory(
                              base64Decode(group.first.base64),
                              fit: BoxFit.cover,
                              width: double.infinity,
                              gaplessPlayback: true,
                            ),
                          )
                        : _buildPhotoGrid(group, allPhotos),
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.camera_alt, size: 12, color: Colors.grey.shade500),
                        const SizedBox(width: 4),
                        Text(
                          group.length > 1 ? '$timeStr · ${group.length} photos' : timeStr,
                          style: TextStyle(color: Colors.grey.shade500, fontSize: 11),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPhotoGrid(List<ConversationPhoto> group, List<ConversationPhoto> allPhotos) {
    if (group.length == 2) {
      return Row(
        children: group
            .map((photo) => Expanded(
                  child: GestureDetector(
                    onTap: () => _openPhotoViewer(allPhotos, allPhotos.indexOf(photo)),
                    child: AspectRatio(
                      aspectRatio: 1,
                      child: Image.memory(
                        base64Decode(photo.base64),
                        fit: BoxFit.cover,
                        gaplessPlayback: true,
                      ),
                    ),
                  ),
                ))
            .toList(),
      );
    }
    // 3+ photos: show first two large, rest smaller below
    final firstRow = group.take(2).toList();
    final secondRow = group.skip(2).toList();
    return Column(
      children: [
        Row(
          children: firstRow
              .map((photo) => Expanded(
                    child: GestureDetector(
                      onTap: () => _openPhotoViewer(allPhotos, allPhotos.indexOf(photo)),
                      child: AspectRatio(
                        aspectRatio: 1,
                        child: Image.memory(
                          base64Decode(photo.base64),
                          fit: BoxFit.cover,
                          gaplessPlayback: true,
                        ),
                      ),
                    ),
                  ))
              .toList(),
        ),
        if (secondRow.isNotEmpty)
          Row(
            children: [
              ...secondRow.map((photo) => Expanded(
                    child: GestureDetector(
                      onTap: () => _openPhotoViewer(allPhotos, allPhotos.indexOf(photo)),
                      child: AspectRatio(
                        aspectRatio: 1,
                        child: Image.memory(
                          base64Decode(photo.base64),
                          fit: BoxFit.cover,
                          gaplessPlayback: true,
                        ),
                      ),
                    ),
                  )),
              // Fill remaining space if odd number
              if (secondRow.length < 2) const Expanded(child: SizedBox()),
            ],
          ),
      ],
    );
  }

  void _openPhotoViewer(List<ConversationPhoto> allPhotos, int index) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => PhotoViewerPage(
          photos: allPhotos,
          initialIndex: index >= 0 ? index : 0,
        ),
      ),
    );
  }

  void _editSegmentSpeaker(TranscriptSegment segment, CaptureProvider provider) {
    final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
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
        final suggestion = provider.suggestionsBySegmentId.values
            .firstWhere((s) => s.speakerId == segment.speakerId, orElse: () => SpeakerLabelSuggestionEvent.empty());
        return NameSpeakerBottomSheet(
          speakerId: segment.speakerId,
          segmentId: segment.id,
          segments: provider.segments,
          suggestion: suggestion,
          onSpeakerAssigned: (speakerId, personId, personName, segmentIds) async {
            await provider.assignSpeakerToConversation(speakerId, personId, personName, segmentIds);
          },
        );
      },
    );
  }

  Widget _buildTranscriptTimelineItem(TranscriptSegment segment, CaptureProvider provider) {
    final bool isUser = segment.isUser;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isUser) ...[
            GestureDetector(
              onTap: () => _editSegmentSpeaker(segment, provider),
              child: Column(
                children: [
                  CircleAvatar(
                    radius: 16,
                    backgroundColor: Colors.blueGrey.withValues(alpha: 0.3),
                    child: const Icon(Icons.person, size: 16, color: Colors.white70),
                  ),
                  const SizedBox(height: 2),
                ],
              ),
            ),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: GestureDetector(
              onTap: () => _editSegmentSpeaker(segment, provider),
              child: Container(
                constraints: BoxConstraints(
                  maxWidth: MediaQuery.of(context).size.width * 0.75,
                ),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: isUser ? const Color(0xFF8B5CF6).withValues(alpha: 0.8) : const Color(0xFF2A2A32),
                  borderRadius: BorderRadius.circular(18),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.15),
                      blurRadius: 4,
                      offset: const Offset(0, 1),
                    ),
                  ],
                ),
                child: Text(
                  segment.text,
                  style: TextStyle(
                    color: isUser ? Colors.white : Colors.grey.shade100,
                    fontSize: 15,
                    height: 1.4,
                  ),
                ),
              ),
            ),
          ),
          if (isUser) ...[
            const SizedBox(width: 8),
            GestureDetector(
              onTap: () => _editSegmentSpeaker(segment, provider),
              child: Column(
                children: [
                  CircleAvatar(
                    radius: 16,
                    backgroundColor: const Color(0xFF8B5CF6).withValues(alpha: 0.3),
                    child: const Icon(Icons.person, size: 16, color: Colors.white70),
                  ),
                  const SizedBox(height: 2),
                ],
              ),
            ),
          ],
        ],
      ),
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
