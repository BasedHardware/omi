import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/widgets/conversation_photo_image.dart';
import 'package:omi/widgets/media_viewer_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class PhotosGridComponent extends StatelessWidget {
  final List<ConversationPhoto> photos;
  final String? conversationId;
  const PhotosGridComponent({super.key, required this.photos, this.conversationId});

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      padding: EdgeInsets.zero,
      scrollDirection: Axis.vertical,
      itemCount: photos.length,
      itemBuilder: (context, idx) {
        final photo = photos[idx];
        final isProcessing = !photo.discarded && photo.description == null;

        return Semantics(
          key: ValueKey(photo.id),
          button: true,
          image: true,
          label: photo.description ?? context.l10n.photos,
          excludeSemantics: true,
          child: GestureDetector(
            onTap: () =>
                MediaViewerPage.open(context, items: mediaItemsForPhotos(photos, conversationId), initialIndex: idx),
            child: Hero(
              tag: photo.id,
              child: ClipRRect(
                borderRadius: OmiRadius.smAll,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    ConversationPhotoImage(
                      photo: photo,
                      conversationId: conversationId,
                      fit: BoxFit.cover,
                      color: photo.discarded ? OmiColors.surface3 : null,
                      colorBlendMode: photo.discarded ? BlendMode.saturation : null,
                    ),
                    if (photo.discarded)
                      Container(
                        color: Colors.black.withValues(alpha: 0.5),
                        child: const Icon(Icons.visibility_off_outlined, color: Colors.white70, size: 28),
                      ),
                    if (isProcessing)
                      Container(
                        color: Colors.black.withValues(alpha: 0.5),
                        child: const Center(child: OmiSpinner(size: OmiSpinnerSize.small)),
                      ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        crossAxisSpacing: 8,
        mainAxisSpacing: 8,
        childAspectRatio: 800 / 600,
      ),
    );
  }
}

/// Viewer items for a conversation's photos (inline base64 or lazily loaded from storage).
List<MediaViewerItem> mediaItemsForPhotos(List<ConversationPhoto> photos, String? conversationId) {
  return photos.map((photo) {
    final hasInlineBytes = photo.base64.isNotEmpty;
    return MediaViewerItem(
      base64: hasInlineBytes ? photo.base64 : null,
      bytesLoader: hasInlineBytes ? null : () => loadConversationPhotoBytes(photo, conversationId),
      mimeType: photo.contentType,
      heroTag: photo.id,
      showCaptionStrip: true,
      caption: photo.description,
      discarded: photo.discarded,
    );
  }).toList();
}
