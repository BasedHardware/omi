import 'dart:convert';
import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:photo_view/photo_view.dart';
import 'package:photo_view/photo_view_gallery.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/share_sheet.dart';

/// Full-screen photo viewer that replaces `FullScreenImageViewer` (a single network image, e.g.
/// app store thumbnails) and `PhotoViewerPage` (a paged gallery of base64 conversation photos).
/// Both did the same job — black background, `PhotoView` zoom/pan, a way to close — and differed
/// only in image source and whether a caption strip sat under the image, so they are one widget
/// now, configured per call site via [MediaViewerItem].
///
/// The one thing neither had: a share action. On macOS the equivalent viewer is the OS's own
/// Quick Look panel, which gives share / save / open-with for free because it's the system's
/// viewer, not ours. Mobile has no such panel, so this AppBar carries an explicit share button
/// instead — the one capability the OS handed macOS that mobile has to be given by hand.
class MediaViewerItem {
  /// Base64 photo payload, for conversation/glasses photos. Deliberately the *encoded* string
  /// rather than an `ImageProvider`: building the provider eagerly means base64-decoding every
  /// photo in the gallery and holding all of them before the first frame renders, which the
  /// widget this replaced never did — `PhotoViewGallery.builder` only decoded pages it built.
  /// Exactly one of [base64] / [imageUrl] must be set.
  final String? base64;

  /// Network image URL, for app-store thumbnails. Exactly one of [base64] / [imageUrl] must be
  /// set.
  final String? imageUrl;

  /// Hero tag for cross-page transitions. Null disables the Hero wrapper for this page, matching
  /// the single-image call sites, which never had one.
  final Object? heroTag;

  /// Whether the caption/processing/discarded strip below the image applies to this item. Only
  /// the conversation-photo gallery sets this; the single-image viewers never showed it.
  final bool showCaptionStrip;
  final String? caption;
  final bool discarded;

  const MediaViewerItem({
    this.base64,
    this.imageUrl,
    this.heroTag,
    this.showCaptionStrip = false,
    this.caption,
    this.discarded = false,
  }) : assert(
          (base64 == null) != (imageUrl == null),
          'MediaViewerItem needs exactly one image source',
        );
}

class MediaViewerPage extends StatefulWidget {
  final List<MediaViewerItem> items;
  final int initialIndex;

  /// Opaque black for the single-image call sites, transparent for the gallery (matches what
  /// each viewer looked like before this merge).
  final Color appBarBackgroundColor;

  /// `PhotoViewComputedScale.covered * maxScaleMultiplier`. The single-image viewer used 2, the
  /// gallery used 4.
  final double maxScaleMultiplier;

  /// True for an explicit close `X` (single-image viewer); false lets the pushed route's default
  /// back arrow show instead (the gallery never overrode `leading`).
  final bool showCloseButton;

  /// The gallery viewer wrapped its body in a `SafeArea` (it has a caption strip that must clear
  /// the home indicator); the single-image viewer did not.
  final bool wrapBodyInSafeArea;

  const MediaViewerPage({
    super.key,
    required this.items,
    this.initialIndex = 0,
    this.appBarBackgroundColor = Colors.black,
    this.maxScaleMultiplier = 4,
    this.showCloseButton = false,
    this.wrapBodyInSafeArea = true,
  });

  @override
  State<MediaViewerPage> createState() => _MediaViewerPageState();
}

class _MediaViewerPageState extends State<MediaViewerPage> {
  late int _currentIndex;
  late final PageController _pageController;
  final GlobalKey _shareButtonKey = GlobalKey();
  bool _isSharing = false;

  /// Providers are built the first time a page is actually built and kept after that, so paging
  /// back and forth does not decode the same photo again while opening the route still decodes
  /// nothing.
  final Map<int, ImageProvider> _providers = {};

  ImageProvider _providerFor(int index) {
    return _providers.putIfAbsent(index, () {
      final item = widget.items[index];
      final encoded = item.base64;
      if (encoded != null) return MemoryImage(base64Decode(encoded));
      return CachedNetworkImageProvider(item.imageUrl!);
    });
  }

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
    _pageController = PageController(initialPage: widget.initialIndex);
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  void _onPageChanged(int index) => setState(() => _currentIndex = index);

  /// How long a thumbnail download may take before sharing gives up.
  ///
  /// `http.get` has no deadline of its own, so a server that accepts the connection and then says
  /// nothing leaves the share button spinning for the rest of the session with no way out.
  static const _downloadTimeout = Duration(seconds: 20);

  /// The most a shared image may weigh. `http.get` buffers the whole body in memory before
  /// anything is written, so an unbounded response is an unbounded allocation on a phone.
  static const _maxDownloadBytes = 32 * 1024 * 1024;

  Future<void> _share() async {
    if (_isSharing) return;
    setState(() => _isSharing = true);
    final item = widget.items[_currentIndex];
    File? scratch;
    try {
      final XFile file;
      final dir = await getTemporaryDirectory();
      final stamp = DateTime.now().millisecondsSinceEpoch;
      final encoded = item.base64;
      if (encoded != null) {
        // Camera/glasses photos come down as JPEG.
        scratch = File('${dir.path}/omi_photo_$stamp.jpg');
        await scratch.writeAsBytes(base64Decode(encoded));
        file = XFile(scratch.path, mimeType: 'image/jpeg');
      } else {
        final url = item.imageUrl!;
        final response = await http.get(Uri.parse(url)).timeout(_downloadTimeout);
        if (response.statusCode != 200) {
          throw Exception('Failed to download image: HTTP ${response.statusCode}');
        }
        if (response.bodyBytes.length > _maxDownloadBytes) {
          throw Exception('Image too large to share: ${response.bodyBytes.length} bytes');
        }
        // The server's own content type, not the URL's extension — a thumbnail served as PNG from
        // a path with no suffix would otherwise be handed to the share sheet labelled as JPEG.
        final mime = _imageMimeType(response.headers['content-type']) ?? 'image/jpeg';
        final ext = mime.split('/').last;
        scratch = File('${dir.path}/omi_image_$stamp.$ext');
        await scratch.writeAsBytes(response.bodyBytes);
        file = XFile(scratch.path, mimeType: mime);
      }
      await SharePlus.instance.share(
        ShareParams(files: [file], sharePositionOrigin: shareSheetOrigin(_shareButtonKey)),
      );
    } catch (e) {
      Logger.debug('Failed to share media: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.somethingWentWrong)),
        );
      }
    } finally {
      // The share sheet has copied what it needs by the time it returns, and every one of these is
      // a full-resolution photo. Left behind they accumulate one per share for as long as the OS
      // keeps the temp directory around.
      try {
        await scratch?.delete();
      } catch (_) {
        // A file the OS already reclaimed is the outcome we wanted anyway.
      }
      if (mounted) setState(() => _isSharing = false);
    }
  }

  /// Narrow a `Content-Type` header to an image type we are willing to name, or null when the
  /// server said something we should not repeat to the share sheet.
  static String? _imageMimeType(String? header) {
    if (header == null) return null;
    final value = header.split(';').first.trim().toLowerCase();
    const allowed = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/heic'};
    return allowed.contains(value) ? value : null;
  }

  Widget? _buildCaptionStrip(MediaViewerItem item) {
    if (!item.showCaptionStrip) return null;
    final hasCaption = item.caption != null && item.caption!.isNotEmpty;
    final isProcessing = item.caption == null;

    if (item.discarded) {
      return _captionText(
        context.l10n.photoDiscardedMessage,
        color: Colors.white70,
      );
    }
    if (isProcessing) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(24, 24, 24, 48),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: Colors.white70,
              ),
            ),
            const SizedBox(width: 12),
            Text(
              context.l10n.analyzing,
              style: const TextStyle(color: Colors.white70, fontSize: 16),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      );
    }
    if (hasCaption) {
      return _captionText(item.caption!, color: Colors.white);
    }
    return null;
  }

  Widget _captionText(String text, {required Color color}) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 24, 24, 48),
      child: Text(
        text,
        style: TextStyle(color: color, fontSize: 16),
        textAlign: TextAlign.center,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final currentItem = widget.items[_currentIndex];
    final captionStrip = _buildCaptionStrip(currentItem);

    final gallery = PhotoViewGallery.builder(
      itemCount: widget.items.length,
      pageController: _pageController,
      onPageChanged: _onPageChanged,
      scrollPhysics: const BouncingScrollPhysics(),
      backgroundDecoration: const BoxDecoration(color: Colors.black),
      builder: (context, index) {
        final item = widget.items[index];
        return PhotoViewGalleryPageOptions(
          imageProvider: _providerFor(index),
          minScale: PhotoViewComputedScale.contained,
          maxScale: PhotoViewComputedScale.covered * widget.maxScaleMultiplier,
          heroAttributes: item.heroTag != null ? PhotoViewHeroAttributes(tag: item.heroTag!) : null,
        );
      },
    );

    final body = Column(
      children: [
        Expanded(child: gallery),
        if (captionStrip != null) captionStrip,
      ],
    );

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: widget.appBarBackgroundColor,
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.white),
        leading: widget.showCloseButton
            ? IconButton(
                icon: const Icon(Icons.close),
                onPressed: () => Navigator.pop(context),
              )
            : null,
        actions: [
          IconButton(
            key: _shareButtonKey,
            icon: _isSharing
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Icon(Icons.ios_share),
            onPressed: _isSharing ? null : _share,
          ),
        ],
      ),
      body: widget.wrapBodyInSafeArea ? SafeArea(child: body) : body,
    );
  }
}
