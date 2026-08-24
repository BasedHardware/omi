import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'package:photo_view/photo_view.dart';
import 'package:photo_view/photo_view_gallery.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/utils/l10n_extensions.dart';

class PhotoViewerPage extends StatefulWidget {
  final List<ConversationPhoto> photos;
  final int initialIndex;
  final String? conversationId;

  const PhotoViewerPage({super.key, required this.photos, required this.initialIndex, this.conversationId});

  @override
  State<PhotoViewerPage> createState() => _PhotoViewerPageState();
}

class _PhotoViewerPageState extends State<PhotoViewerPage> {
  late int currentIndex;
  late PageController pageController;

  @override
  void initState() {
    super.initState();
    currentIndex = widget.initialIndex;
    pageController = PageController(initialPage: widget.initialIndex);
  }

  void onPageChanged(int index) {
    setState(() {
      currentIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    final currentPhoto = widget.photos[currentIndex];
    final hasDescription = currentPhoto.description != null && currentPhoto.description!.isNotEmpty;
    final isProcessing = currentPhoto.description == null;

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: PhotoViewGallery.builder(
                itemCount: widget.photos.length,
                pageController: pageController,
                onPageChanged: onPageChanged,
                builder: (context, index) {
                  final photo = widget.photos[index];
                  return FutureBuilder<Uint8List?>(
                    future: loadConversationPhotoBytes(photo, widget.conversationId),
                    builder: (context, snapshot) {
                      final bytes = snapshot.data;
                      if (bytes == null || bytes.isEmpty) {
                        return const PhotoViewGalleryPageOptions.customChild(
                          child: Center(child: CircularProgressIndicator()),
                        );
                      }
                      return PhotoViewGalleryPageOptions(
                        imageProvider: MemoryImage(bytes),
                        minScale: PhotoViewComputedScale.contained,
                        maxScale: PhotoViewComputedScale.covered * 4,
                        heroAttributes: PhotoViewHeroAttributes(tag: photo.id),
                      );
                    },
                  );
                },
                scrollPhysics: const BouncingScrollPhysics(),
                backgroundDecoration: const BoxDecoration(color: Colors.black),
              ),
            ),
            if (currentPhoto.discarded)
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 24, 24, 48),
                child: Text(
                  context.l10n.photoDiscardedMessage,
                  style: const TextStyle(color: Colors.white70, fontSize: 16),
                  textAlign: TextAlign.center,
                ),
              )
            else if (isProcessing)
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 24, 24, 48),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white70),
                    ),
                    const SizedBox(width: 12),
                    Text(
                      context.l10n.analyzing,
                      style: const TextStyle(color: Colors.white70, fontSize: 16),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              )
            else if (hasDescription)
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 24, 24, 48),
                child: Text(
                  currentPhoto.description!,
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                  textAlign: TextAlign.center,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

Future<Uint8List?> loadConversationPhotoBytes(ConversationPhoto photo, String? conversationId) async {
  if (photo.base64.isNotEmpty) {
    try {
      return base64Decode(photo.base64);
    } on FormatException {
      return null;
    }
  }
  if (conversationId == null || conversationId.isEmpty || photo.storageId == null || photo.storageId!.isEmpty) {
    return null;
  }
  return getConversationPhotoImage(conversationId, photo.id);
}

class ConversationPhotoImage extends StatelessWidget {
  final ConversationPhoto photo;
  final String? conversationId;
  final BoxFit fit;
  final Color? color;
  final BlendMode? colorBlendMode;

  const ConversationPhotoImage({
    super.key,
    required this.photo,
    this.conversationId,
    this.fit = BoxFit.cover,
    this.color,
    this.colorBlendMode,
  });

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Uint8List?>(
      future: loadConversationPhotoBytes(photo, conversationId),
      builder: (context, snapshot) {
        final bytes = snapshot.data;
        if (bytes == null || bytes.isEmpty) {
          return const ColoredBox(
            color: Colors.black12,
            child: Center(child: Icon(Icons.image_outlined)),
          );
        }
        return Image.memory(bytes, fit: fit, gaplessPlayback: true, color: color, colorBlendMode: colorBlendMode);
      },
    );
  }
}
