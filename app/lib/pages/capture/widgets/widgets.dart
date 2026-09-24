import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/home/omiglass_ota_update.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/conversation_photo_image.dart';
import 'package:omi/widgets/photos_grid.dart';
import 'package:omi/widgets/transcript.dart';

class SpeechProfileCardWidget extends StatelessWidget {
  const SpeechProfileCardWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<HomeProvider>(
      builder: (context, provider, child) {
        if (provider.isLoading) return const SizedBox();
        return provider.hasSpeakerProfile
            ? const SizedBox()
            : Consumer<DeviceProvider>(
                builder: (context, device, child) {
                  if (device.pairedDevice == null ||
                      !device.isConnected ||
                      device.pairedDevice?.firmwareRevision == '1.0.2') {
                    return const SizedBox();
                  }
                  return _CardRow(
                    icon: Icons.multitrack_audio,
                    label: context.l10n.teachOmiYourVoice,
                    // A dot marks a setup step still to do.
                    badge: true,
                    onTap: () async {
                      PlatformManager.instance.analytics.pageOpened('Speech Profile Memories');
                      bool hasSpeakerProfile = SharedPreferencesUtil().hasSpeakerProfile;
                      await openVoiceProfile(context);
                      final newHasSpeakerProfile = SharedPreferencesUtil().hasSpeakerProfile;
                      if (hasSpeakerProfile != newHasSpeakerProfile) {
                        if (!context.mounted) return;
                        await context.read<CaptureProvider>().onRecordProfileSettingChanged();
                        if (!context.mounted) return;
                        context.read<HomeProvider>().setSpeakerProfile(newHasSpeakerProfile);
                      }
                    },
                  );
                },
              );
      },
    );
  }
}

/// A tappable card row on the capture surfaces: icon, label, chevron; announced as a button.
class _CardRow extends StatelessWidget {
  const _CardRow({required this.icon, required this.label, required this.onTap, this.badge = false});

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool badge;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, 0),
      child: Semantics(
        button: true,
        label: label,
        excludeSemantics: true,
        child: Material(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.xlAll,
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.all(OmiSpacing.md),
              child: Row(
                children: [
                  Icon(icon, color: OmiColors.textPrimary),
                  const SizedBox(width: OmiSpacing.md),
                  Expanded(child: Text(label, style: OmiType.callout)),
                  if (badge) ...[
                    const Icon(Icons.fiber_manual_record, color: OmiColors.danger, size: 10),
                    const SizedBox(width: OmiSpacing.xs),
                  ],
                  const Icon(Icons.arrow_forward_ios, color: OmiColors.textPrimary, size: 16),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class UpdateFirmwareCardWidget extends StatelessWidget {
  const UpdateFirmwareCardWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceProvider>(
      builder: (context, provider, child) {
        if (!provider.havingNewFirmware) return const SizedBox();

        final isOmiGlass = provider.pairedDevice?.type == DeviceType.openglass ||
            (provider.pairedDevice?.name.toLowerCase().contains('glass') ?? false);

        return _CardRow(
          icon: Icons.upload,
          label: isOmiGlass ? context.l10n.updateOmiGlassFirmware : context.l10n.updateOmiFirmware,
          onTap: () {
            PlatformManager.instance.analytics.pageOpened('Update Firmware Memories');
            if (isOmiGlass) {
              routeToPage(
                context,
                OmiGlassOtaUpdate(
                  device: provider.pairedDevice,
                  latestFirmwareDetails: provider.latestOmiGlassFirmwareDetails,
                ),
              );
            } else {
              routeToPage(context, FirmwareUpdate(device: provider.pairedDevice));
            }
          },
        );
      },
    );
  }
}

class PhotosPreviewWidget extends StatelessWidget {
  final List<ConversationPhoto> photos;
  final String? conversationId;
  const PhotosPreviewWidget({super.key, required this.photos, this.conversationId});

  @override
  Widget build(BuildContext context) {
    // Show the last 3 photos, newest first.
    final displayPhotos = photos.length > 3 ? photos.sublist(photos.length - 3) : photos;
    final resolvedConversationId = conversationId ?? context.read<CaptureProvider>().topConversationId;
    return SizedBox(
      height: 80,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        children: displayPhotos.reversed.map((photo) {
          return Flexible(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2.0),
              child: AspectRatio(
                aspectRatio: 800 / 600,
                child: ClipRRect(
                  borderRadius: OmiRadius.smAll,
                  child: ConversationPhotoImage(
                    photo: photo,
                    conversationId: resolvedConversationId,
                    fit: BoxFit.cover,
                  ),
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
  List<String> taggingSegmentIds = const [],
  String searchQuery = '',
  int currentResultIndex = -1,
  VoidCallback? onTapWhenSearchEmpty,
  Function(TranscriptSegment)? onSegmentTap,
  Function(int)? onEditSegmentText,
  Key? transcriptKey,
  bool followLatest = false,
  String? conversationId,
  TranscriptScrollState? scrollState,
  double jumpToLatestButtonBottom = 16,
  int contentVersion = 0,
  String layoutIdentity = 'transcript',
  List<Widget> leadingItems = const [],
  List<String> leadingItemIds = const [],
  TranscriptSegmentBuilder? segmentBuilder,
}) {
  if (conversationCreating) {
    return const Padding(padding: EdgeInsets.only(top: 80), child: Center(child: OmiSpinner()));
  }

  final bool showPhotos = photos.isNotEmpty;
  final bool showTranscript = segments.isNotEmpty;

  Widget buildPhotos() {
    return PhotosGridComponent(photos: photos, conversationId: conversationId);
  }

  Widget buildTranscriptSegments() {
    return TranscriptWidget(
      key: transcriptKey,
      segments: segments,
      horizontalMargin: horizontalMargin,
      topMargin: topMargin,
      canDisplaySeconds: canDisplaySeconds,
      isConversationDetail: isConversationDetail,
      bottomMargin: bottomMargin,
      editSegment: editSegment,
      taggingSegmentIds: taggingSegmentIds,
      searchQuery: searchQuery,
      currentResultIndex: currentResultIndex,
      onTapWhenSearchEmpty: onTapWhenSearchEmpty,
      onSegmentTap: onSegmentTap,
      onEditSegmentText: onEditSegmentText,
      followLatest: followLatest,
      scrollState: scrollState,
      jumpToLatestButtonBottom: jumpToLatestButtonBottom,
      contentVersion: contentVersion,
      layoutIdentity: layoutIdentity,
      leadingItems: leadingItems,
      leadingItemIds: leadingItemIds,
      segmentBuilder: segmentBuilder,
    );
  }

  if (showPhotos && showTranscript) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(height: 250, child: buildPhotos()),
        Expanded(child: buildTranscriptSegments()),
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

getLiteTranscriptWidget(List<TranscriptSegment> segments, List<ConversationPhoto> photos, BtDevice? btDevice) {
  return Column(
    children: [
      if (photos.isNotEmpty) PhotosPreviewWidget(photos: photos),
      if (photos.isNotEmpty && segments.isNotEmpty) const SizedBox(height: 8),
      if (segments.isNotEmpty) LiteTranscriptWidget(segments: segments),
    ],
  );
}
