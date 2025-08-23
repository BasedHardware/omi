import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/speech_profile/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/photos_grid.dart';
import 'package:omi/widgets/transcript.dart';
import 'package:omi/widgets/recording_waveform.dart';
import 'package:provider/provider.dart';
import 'package:tuple/tuple.dart';

class SpeechProfileCardWidget extends StatelessWidget {
  const SpeechProfileCardWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<HomeProvider>(
      builder: (context, provider, child) {
        if (provider.isLoading) return const SizedBox();
        return provider.hasSpeakerProfile
            ? const SizedBox()
            : Consumer<DeviceProvider>(builder: (context, device, child) {
                if (device.pairedDevice == null || !device.isConnected || device.pairedDevice?.firmwareRevision == '1.0.2') {
                  return const SizedBox();
                }
                return Stack(
                  children: [
                    GestureDetector(
                      onTap: () async {
                        MixpanelManager().pageOpened('Speech Profile Memories');
                        bool hasSpeakerProfile = SharedPreferencesUtil().hasSpeakerProfile;
                        await routeToPage(context, const SpeechProfilePage());
                        if (hasSpeakerProfile != SharedPreferencesUtil().hasSpeakerProfile) {
                          if (context.mounted) {
                            context.read<CaptureProvider>().onRecordProfileSettingChanged();
                          }
                        }
                      },
                      child: Container(
                        decoration: BoxDecoration(
                          color: const Color(0xFF1F1F25),
                          borderRadius: const BorderRadius.all(Radius.circular(12)),
                        ),
                        margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                        padding: const EdgeInsets.all(16),
                        child: const Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(
                              child: Row(
                                children: [
                                  Icon(Icons.multitrack_audio),
                                  SizedBox(width: 16),
                                  Text(
                                    'Teach Omi your voice',
                                    style: TextStyle(color: Colors.white, fontSize: 16),
                                  ),
                                ],
                              ),
                            ),
                            Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
                          ],
                        ),
                      ),
                    ),
                    const Positioned(
                      top: 6,
                      right: 24,
                      child: Icon(Icons.fiber_manual_record, color: Colors.red, size: 16.0),
                    ),
                  ],
                );
              });
      },
    );
  }
}

class UpdateFirmwareCardWidget extends StatelessWidget {
  const UpdateFirmwareCardWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceProvider>(
      builder: (context, provider, child) {
        return (!provider.havingNewFirmware)
            ? const SizedBox()
            : Stack(
                children: [
                  GestureDetector(
                    onTap: () {
                      MixpanelManager().pageOpened('Update Firmware Memories');
                      routeToPage(context, FirmwareUpdate(device: provider.pairedDevice));
                    },
                    child: Container(
                      decoration: BoxDecoration(
                        color: const Color(0xFF1F1F25),
                        borderRadius: const BorderRadius.all(Radius.circular(12)),
                      ),
                      margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                      padding: const EdgeInsets.all(16),
                      child: const Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: Row(
                              children: [
                                Icon(Icons.upload),
                                SizedBox(width: 16),
                                Text(
                                  'Update omi firmware',
                                  style: TextStyle(color: Colors.white, fontSize: 16),
                                ),
                              ],
                            ),
                          ),
                          Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
                        ],
                      ),
                    ),
                  ),
                ],
              );
      },
    );
  }
}

class PhotosPreviewWidget extends StatelessWidget {
  final List<ConversationPhoto> photos;
  const PhotosPreviewWidget({super.key, required this.photos});

  @override
  Widget build(BuildContext context) {
    // Show the last 3 photos, newest first.
    final displayPhotos = photos.length > 3 ? photos.sublist(photos.length - 3) : photos;
    return SizedBox(
      height: 80,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        children: displayPhotos.reversed.map((photo) {
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 2.0),
            child: AspectRatio(
              aspectRatio: 800 / 600,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(8.0),
                child: Image.memory(
                  base64Decode(photo.base64),
                  fit: BoxFit.cover,
                  gaplessPlayback: true, // Avoids flicker when image updates
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

getTranscriptWidget(
  bool conversationCreating,
  List<TranscriptSegment> segments,
  List<ConversationPhoto> photos,
  BtDevice? btDevice, {
  bool horizontalMargin = true,
  bool topMargin = true,
  bool canDisplaySeconds = true,
  bool isConversationDetail = false,
  double bottomMargin = 100.0,
  Function(String, int)? editSegment,
  Map<String, SpeakerLabelSuggestionEvent> suggestions = const {},
  List<String> taggingSegmentIds = const [],
  Function(SpeakerLabelSuggestionEvent)? onAcceptSuggestion,
  String searchQuery = '',
  int currentResultIndex = -1,
}) {
  if (conversationCreating) {
    return const Padding(
      padding: EdgeInsets.only(top: 80),
      child: Center(child: CircularProgressIndicator(color: Colors.white)),
    );
  }

  final bool showPhotos = photos.isNotEmpty;
  final bool showTranscript = segments.isNotEmpty;

  Widget buildPhotos() {
    return PhotosGridComponent(
      photos: photos,
    );
  }

  Widget buildTranscriptSegments() {
    return TranscriptWidget(
      segments: segments,
      horizontalMargin: horizontalMargin,
      topMargin: topMargin,
      canDisplaySeconds: canDisplaySeconds,
      isConversationDetail: isConversationDetail,
      bottomMargin: bottomMargin,
      editSegment: editSegment,
      suggestions: suggestions,
      taggingSegmentIds: taggingSegmentIds,
      onAcceptSuggestion: onAcceptSuggestion,
      searchQuery: searchQuery,
      currentResultIndex: currentResultIndex,
    );
  }

  if (showPhotos && showTranscript) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(
          height: 250,
          child: buildPhotos(),
        ),
        Expanded(
          child: buildTranscriptSegments(),
        ),
      ],
    );
  }

  if (showPhotos) {
    return buildPhotos();
  }

  if (showTranscript) {
    return buildTranscriptSegments();
  }
  return const SizedBox.shrink();
}

getLiteTranscriptWidget(
  List<TranscriptSegment> segments,
  List<ConversationPhoto> photos,
  BtDevice? btDevice,
) {
  return Column(
    children: [
      if (photos.isNotEmpty) PhotosPreviewWidget(photos: photos),
      if (photos.isNotEmpty && segments.isNotEmpty) const SizedBox(height: 8),
      if (segments.isNotEmpty)
        LiteTranscriptWidget(
          segments: segments,
        ),
    ],
  );
}

getPhoneMicRecordingButton(VoidCallback recordingToggled, RecordingState state) {
  if (SharedPreferencesUtil().btDevice.id.isNotEmpty) return const SizedBox.shrink();
  return Visibility(
    visible: true,
    child: Padding(
      padding: const EdgeInsets.only(bottom: 128),
      child: Align(
        alignment: Alignment.bottomCenter,
        child: MaterialButton(
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            // side: BorderSide(color: state == RecordState.record ? Colors.red : Colors.white),
          ),
          onPressed: state == RecordingState.initialising ? null : recordingToggled,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
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
                    : (state == RecordingState.record ? const Icon(Icons.stop, color: Colors.red, size: 24) : const Icon(Icons.mic)),
                const SizedBox(width: 8),
                Text(
                  state == RecordingState.initialising ? 'Initialising Recorder' : (state == RecordingState.record ? 'Pause Recording' : 'Continue Recording'),
                  style: const TextStyle(fontSize: 14),
                ),
                const SizedBox(width: 4),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}
