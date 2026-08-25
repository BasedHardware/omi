import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
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
  /// Image to render in the viewer.
  final ImageProvider imageProvider;

  /// Hero tag for cross-page transitions. Null disables the Hero wrapper for this page, matching
  /// the single-image call sites, which never had one.
  final Object? heroTag;

  /// In-memory bytes to share (base64 conversation photos). Exactly one of [shareBytes] /
  /// [shareUrl] must be set.
  final Uint8List? shareBytes;

  /// Network URL to download and share (app thumbnails). Exactly one of [shareBytes] / [shareUrl]
  /// must be set.
  final String? shareUrl;

  /// Whether the caption/processing/discarded strip below the image applies to this item. Only
  /// the conversation-photo gallery sets this; the single-image viewers never showed it.
  final bool showCaptionStrip;
  final String? caption;
  final bool discarded;

  const MediaViewerItem({
    required this.imageProvider,
    this.heroTag,
    this.shareBytes,
    this.shareUrl,
    this.showCaptionStrip = false,
    this.caption,
    this.discarded = false,
  }) : assert(
          shareBytes != null || shareUrl != null,
          'MediaViewerItem needs a share source',
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

  Future<void> _share() async {
    if (_isSharing) return;
    setState(() => _isSharing = true);
    final item = widget.items[_currentIndex];
    try {
      final XFile file;
      final dir = await getTemporaryDirectory();
      final stamp = DateTime.now().millisecondsSinceEpoch;
      if (item.shareBytes != null) {
        // Camera/glasses photos come down as JPEG.
        final path = '${dir.path}/omi_photo_$stamp.jpg';
        await File(path).writeAsBytes(item.shareBytes!);
        file = XFile(path, mimeType: 'image/jpeg');
      } else {
        final url = item.shareUrl!;
        final response = await http.get(Uri.parse(url));
        if (response.statusCode != 200) {
          throw Exception(
            'Failed to download image: HTTP ${response.statusCode}',
          );
        }
        final ext = p.extension(Uri.parse(url).path);
        final path = '${dir.path}/omi_image_$stamp${ext.isEmpty ? '.jpg' : ext}';
        await File(path).writeAsBytes(response.bodyBytes);
        file = XFile(path);
      }
      await SharePlus.instance.share(
        ShareParams(
          files: [file],
          sharePositionOrigin: shareSheetOrigin(_shareButtonKey),
        ),
      );
    } catch (e) {
      Logger.debug('Failed to share media: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.somethingWentWrong)),
        );
      }
    } finally {
      if (mounted) setState(() => _isSharing = false);
    }
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
          imageProvider: item.imageProvider,
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
