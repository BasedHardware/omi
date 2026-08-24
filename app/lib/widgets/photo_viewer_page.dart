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
                  return PhotoViewGalleryPageOptions.customChild(
                    child: ConversationPhotoImage(
                      key: ValueKey('conversation-photo-${photo.id}'),
                      photo: photo,
                      conversationId: widget.conversationId,
                      fit: BoxFit.contain,
                    ),
                    minScale: PhotoViewComputedScale.contained,
                    maxScale: PhotoViewComputedScale.covered * 4,
                    heroAttributes: PhotoViewHeroAttributes(tag: photo.id),
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

typedef ConversationPhotoStorageFetcher = Future<Uint8List?> Function(String conversationId, String photoId);

/// Caches a photo's storage request for the lifetime of the owning surface.
///
/// Inline photos are deliberately decoded before consulting the storage
/// fetcher, so legacy inline data never causes a network request. Null and
/// failed requests are cached as completed misses as well: a deleted, pruned,
/// or temporarily unreachable photo must not leave the UI retrying forever on
/// every rebuild.
class ConversationPhotoBytesCache {
  final ConversationPhotoStorageFetcher _fetchStorageImage;
  final Map<String, Future<Uint8List?>> _storageRequests = {};

  ConversationPhotoBytesCache({ConversationPhotoStorageFetcher? fetchStorageImage})
      : _fetchStorageImage = fetchStorageImage ?? getConversationPhotoImage;

  Future<Uint8List?> load(ConversationPhoto photo, String? conversationId) {
    if (photo.base64.isNotEmpty) {
      return Future.value(_decodeInlinePhoto(photo.base64));
    }
    final normalizedConversationId = conversationId?.trim() ?? '';
    final storageId = photo.storageId?.trim() ?? '';
    if (normalizedConversationId.isEmpty || storageId.isEmpty) {
      return Future.value(null);
    }

    final cacheKey = '$normalizedConversationId\u0000${photo.id}';
    return _storageRequests.putIfAbsent(cacheKey, () => _fetchStorageImageSafely(normalizedConversationId, photo.id));
  }

  Future<Uint8List?> _fetchStorageImageSafely(String conversationId, String photoId) async {
    try {
      return await _fetchStorageImage(conversationId, photoId);
    } catch (_) {
      return null;
    }
  }
}

Uint8List? _decodeInlinePhoto(String value) {
  try {
    return base64Decode(value);
  } on FormatException {
    return null;
  }
}

final ConversationPhotoBytesCache _defaultConversationPhotoBytesCache = ConversationPhotoBytesCache();

Future<Uint8List?> loadConversationPhotoBytes(ConversationPhoto photo, String? conversationId) async {
  return _defaultConversationPhotoBytesCache.load(photo, conversationId);
}

class ConversationPhotoImage extends StatefulWidget {
  final ConversationPhoto photo;
  final String? conversationId;
  final BoxFit fit;
  final Color? color;
  final BlendMode? colorBlendMode;
  final ConversationPhotoBytesCache? cache;

  const ConversationPhotoImage({
    super.key,
    required this.photo,
    this.conversationId,
    this.fit = BoxFit.cover,
    this.color,
    this.colorBlendMode,
    this.cache,
  });

  @override
  State<ConversationPhotoImage> createState() => _ConversationPhotoImageState();
}

class _ConversationPhotoImageState extends State<ConversationPhotoImage> {
  late Future<Uint8List?> _bytesFuture;

  ConversationPhotoBytesCache get _cache => widget.cache ?? _defaultConversationPhotoBytesCache;

  @override
  void initState() {
    super.initState();
    _bytesFuture = _cache.load(widget.photo, widget.conversationId);
  }

  @override
  void didUpdateWidget(covariant ConversationPhotoImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    final photoChanged = oldWidget.photo.id != widget.photo.id ||
        oldWidget.photo.base64 != widget.photo.base64 ||
        oldWidget.photo.storageId != widget.photo.storageId ||
        oldWidget.conversationId != widget.conversationId ||
        oldWidget.cache != widget.cache;
    if (photoChanged) {
      _bytesFuture = _cache.load(widget.photo, widget.conversationId);
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Uint8List?>(
      future: _bytesFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting || snapshot.connectionState == ConnectionState.active) {
          return const Center(child: CircularProgressIndicator());
        }
        final bytes = snapshot.data;
        if (bytes == null || bytes.isEmpty) {
          return Semantics(
            container: true,
            excludeSemantics: true,
            label: context.l10n.syncStatusFileUnavailable,
            child: ColoredBox(
              color: Colors.black12,
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.image_not_supported_outlined),
                    const SizedBox(height: 8),
                    Text(context.l10n.syncStatusFileUnavailable),
                  ],
                ),
              ),
            ),
          );
        }
        return Image.memory(
          bytes,
          fit: widget.fit,
          gaplessPlayback: true,
          color: widget.color,
          colorBlendMode: widget.colorBlendMode,
        );
      },
    );
  }
}
