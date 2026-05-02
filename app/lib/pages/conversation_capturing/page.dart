import 'dart:convert';
import 'dart:io';

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
import 'package:omi/providers/ambient_capture_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/widgets/photo_viewer_page.dart';

class ConversationCapturingPage extends StatefulWidget {
  final String? topConversationId;

  const ConversationCapturingPage({super.key, this.topConversationId});

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
    _animationController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000))
      ..repeat(reverse: true);
    super.initState();
  }

  bool _isAmbientRecording(AmbientCaptureProvider ambientProvider) {
    return Platform.isAndroid && ambientProvider.running;
  }

  Future<void> _toggleMute(CaptureProvider provider, AmbientCaptureProvider ambientProvider) async {
    if (_isMuted) {
      // Unmute - resume recording
      HapticFeedback.mediumImpact();
      setState(() {
        _isMuted = false;
      });

      if (_isAmbientRecording(ambientProvider)) {
        await ambientProvider.resume();
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

      if (_isAmbientRecording(ambientProvider)) {
        await ambientProvider.pause();
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

  Future<void> _stopActiveRecording(CaptureProvider provider, AmbientCaptureProvider ambientProvider) async {
    if (_isAmbientRecording(ambientProvider)) {
      await ambientProvider.stop();
    } else if (provider.recordingState == RecordingState.record) {
      await provider.stopStreamRecording();
    }
  }

  Future<void> _finishConversation(CaptureProvider provider, AmbientCaptureProvider ambientProvider) async {
    await _stopActiveRecording(provider, ambientProvider);
    provider.forceProcessingCurrentConversation();
  }

  Future<void> _handleBack(CaptureProvider provider, AmbientCaptureProvider ambientProvider) async {
    final isRecording = _isAmbientRecording(ambientProvider) || provider.recordingState == RecordingState.record;
    if (!isRecording) {
      Navigator.pop(context);
      return;
    }

    await showDialog(
      context: context,
      builder: (context) {
        return ConfirmationDialog(
          title: context.l10n.recordingActive,
          description: "${context.l10n.capturingAudioAndGeneratingTranscript}\n\n${context.l10n.syncingBackground}",
          cancelText: context.l10n.cancel,
          confirmText: context.l10n.stopRecording,
          onCancel: () => Navigator.of(context).pop(),
          onConfirm: () async {
            await _finishConversation(provider, ambientProvider);
            if (!context.mounted) return;
            Navigator.of(context).pop();
            Navigator.of(context).pop();
          },
        );
      },
    );
  }

  Future<void> _stopConversation(CaptureProvider provider, AmbientCaptureProvider ambientProvider) async {
    final isRecording = _isAmbientRecording(ambientProvider) || provider.recordingState == RecordingState.record;
    if (isRecording && provider.segments.isEmpty && provider.photos.isEmpty) {
      await _finishConversation(provider, ambientProvider);
      if (mounted) Navigator.of(context).pop();
      return;
    }

    if (provider.segments.isNotEmpty || provider.photos.isNotEmpty) {
      // Helper function to stop recording and process conversation
      Future<void> stopRecordingAndProcess() async {
        await _finishConversation(provider, ambientProvider);
      }

      if (!showSummarizeConfirmation) {
        await stopRecordingAndProcess();
        if (!mounted) return;
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
                  if (!mounted || !context.mounted) return;
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
        final ambientProvider = context.watch<AmbientCaptureProvider>();
        final isAmbientRecording = _isAmbientRecording(ambientProvider);
        final isRecording = isAmbientRecording || provider.recordingState == RecordingState.record;
        final hasCapturedContent = provider.segments.isNotEmpty || provider.photos.isNotEmpty;
        return PopScope(
          canPop: false,
          onPopInvokedWithResult: (didPop, result) {
            if (didPop) return;
            _handleBack(provider, ambientProvider);
          },
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
                    onPressed: () => _handleBack(provider, ambientProvider),
                    icon: const Icon(Icons.arrow_back_rounded, size: 24.0),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    provider.photos.isNotEmpty
                        ? "📸"
                        : _isMuted
                            ? "🔇"
                            : "🎙️",
                  ),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      provider.photos.isNotEmpty
                          ? 'Capturing'
                          : (_isMuted ? context.l10n.muted : context.l10n.listening),
                    ),
                  ),
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
                        // Transcripts, photos + inline WAL safety indicator
                        Column(
                          children: [
                            Expanded(
                              child: !hasCapturedContent
                                  ? Center(
                                      child: Padding(
                                        padding: const EdgeInsets.symmetric(horizontal: 32.0),
                                        child: Column(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            Icon(
                                              isRecording ? Icons.graphic_eq_rounded : Icons.mic_none_rounded,
                                              color: Colors.white70,
                                              size: 40,
                                            ),
                                            const SizedBox(height: 16),
                                            Text(
                                              isRecording
                                                  ? context.l10n.capturingAudioAndGeneratingTranscript
                                                  : context.l10n.waitingForTranscriptOrPhotos,
                                              textAlign: TextAlign.center,
                                              style: const TextStyle(
                                                color: Colors.white,
                                                fontSize: 16,
                                                fontWeight: FontWeight.w600,
                                              ),
                                            ),
                                            if (isRecording) ...[
                                              const SizedBox(height: 8),
                                              Text(
                                                context.l10n.syncingBackground,
                                                textAlign: TextAlign.center,
                                                style: TextStyle(color: Colors.grey.shade400, fontSize: 13),
                                              ),
                                            ],
                                          ],
                                        ),
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
                                            provider.assignSpeakerToConversation(
                                              suggestion.speakerId,
                                              suggestion.personId,
                                              suggestion.personName,
                                              [suggestion.segmentId],
                                            );
                                          },
                                          editSegment: (segmentId, speakerId) {
                                            final connectivityProvider = Provider.of<ConnectivityProvider>(
                                              context,
                                              listen: false,
                                            );
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
                                                  orElse: () => SpeakerLabelSuggestionEvent.empty(),
                                                );
                                                return NameSpeakerBottomSheet(
                                                  speakerId: speakerId,
                                                  segmentId: segmentId,
                                                  segments: provider.segments,
                                                  suggestion: suggestion,
                                                  onSpeakerAssigned:
                                                      (speakerId, personId, personName, segmentIds) async {
                                                    await provider.assignSpeakerToConversation(
                                                      speakerId,
                                                      personId,
                                                      personName,
                                                      segmentIds,
                                                    );
                                                  },
                                                );
                                              },
                                            );
                                          },
                                        ),
                            ),
                            _buildUnsyncedWalIndicator(provider.unsyncedSessionWals, provider.inFlightAudioSeconds),
                          ],
                        ),
                        // Summary Tab
                        Center(
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 32.0,
                            ).copyWith(bottom: 50.0), // Adjust padding
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
            floatingActionButton: (isRecording || hasCapturedContent)
                ? Row(
                    mainAxisSize: MainAxisSize.min,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      // Process Now button
                      GestureDetector(
                        onTap: () => _stopConversation(provider, ambientProvider),
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
                              const FaIcon(FontAwesomeIcons.stop, color: Colors.black, size: 16.0),
                              const SizedBox(width: 10),
                              Text(
                                hasCapturedContent ? context.l10n.processNow : context.l10n.stopRecording,
                                style: const TextStyle(color: Colors.black, fontSize: 16, fontWeight: FontWeight.w600),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      // Mute button
                      if (isRecording)
                        GestureDetector(
                          onTap: () => _toggleMute(provider, ambientProvider),
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
                            child: Icon(_isMuted ? Icons.mic : Icons.mic_off, color: Colors.white, size: 24),
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
              constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.7),
              decoration: BoxDecoration(
                color: const Color(0xFF1A3D2E),
                borderRadius: BorderRadius.circular(18),
                boxShadow: [
                  BoxShadow(color: Colors.black.withValues(alpha: 0.15), blurRadius: 4, offset: const Offset(0, 1)),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Grid of photos in this group
                  ClipRRect(
                    borderRadius: const BorderRadius.only(topLeft: Radius.circular(18), topRight: Radius.circular(18)),
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
            .map(
              (photo) => Expanded(
                child: GestureDetector(
                  onTap: () => _openPhotoViewer(allPhotos, allPhotos.indexOf(photo)),
                  child: AspectRatio(
                    aspectRatio: 1,
                    child: Image.memory(base64Decode(photo.base64), fit: BoxFit.cover, gaplessPlayback: true),
                  ),
                ),
              ),
            )
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
              .map(
                (photo) => Expanded(
                  child: GestureDetector(
                    onTap: () => _openPhotoViewer(allPhotos, allPhotos.indexOf(photo)),
                    child: AspectRatio(
                      aspectRatio: 1,
                      child: Image.memory(base64Decode(photo.base64), fit: BoxFit.cover, gaplessPlayback: true),
                    ),
                  ),
                ),
              )
              .toList(),
        ),
        if (secondRow.isNotEmpty)
          Row(
            children: [
              ...secondRow.map(
                (photo) => Expanded(
                  child: GestureDetector(
                    onTap: () => _openPhotoViewer(allPhotos, allPhotos.indexOf(photo)),
                    child: AspectRatio(
                      aspectRatio: 1,
                      child: Image.memory(base64Decode(photo.base64), fit: BoxFit.cover, gaplessPlayback: true),
                    ),
                  ),
                ),
              ),
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
        builder: (context) => PhotoViewerPage(photos: allPhotos, initialIndex: index >= 0 ? index : 0),
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
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
      builder: (context) {
        final suggestion = provider.suggestionsBySegmentId.values.firstWhere(
          (s) => s.speakerId == segment.speakerId,
          orElse: () => SpeakerLabelSuggestionEvent.empty(),
        );
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
                constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.75),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: isUser ? const Color(0xFF8B5CF6).withValues(alpha: 0.8) : const Color(0xFF2A2A32),
                  borderRadius: BorderRadius.circular(18),
                  boxShadow: [
                    BoxShadow(color: Colors.black.withValues(alpha: 0.15), blurRadius: 4, offset: const Offset(0, 1)),
                  ],
                ),
                child: Text(
                  segment.text,
                  style: TextStyle(color: isUser ? Colors.white : Colors.grey.shade100, fontSize: 15, height: 1.4),
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

  Widget _buildUnsyncedWalIndicator(List<Wal> unsyncedWals, int inFlightSeconds) {
    final totalSeconds = unsyncedWals.fold<int>(0, (sum, w) => sum + w.seconds) + inFlightSeconds;
    if (totalSeconds <= 5) return const SizedBox.shrink();
    final minutes = totalSeconds ~/ 60;
    final seconds = totalSeconds % 60;
    final label = minutes > 0 ? '${minutes}m ${seconds}s' : '${seconds}s';
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            color: const Color(0xFF1A1A24),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFF2E2E3E), width: 0.5),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 7,
                height: 7,
                decoration: const BoxDecoration(color: Color(0xFF4CAF50), shape: BoxShape.circle),
              ),
              const SizedBox(width: 8),
              Text(
                context.l10n.audioSavedLocally(label),
                style: const TextStyle(color: Color(0xFFE0E0E8), fontSize: 12.5, fontWeight: FontWeight.w500),
              ),
              if (inFlightSeconds > 0) ...[
                const SizedBox(width: 8),
                const SizedBox(
                  width: 12,
                  height: 12,
                  child: CircularProgressIndicator(strokeWidth: 1.5, color: Color(0xFF6C6C80)),
                ),
              ],
            ],
          ),
        ),
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
