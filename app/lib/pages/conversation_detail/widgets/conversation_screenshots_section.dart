import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart' show CustomSemanticsAction;
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/screen_frames.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/widgets/media_viewer_page.dart';

typedef ConversationScreenshotsFetch = Future<ApiResult<ConversationScreenshots>> Function(String conversationId);
typedef ConversationScreenshotDelete = Future<ApiResult<ConversationScreenshots>> Function(
    String conversationId, String frameId);
typedef ScreenshotBytesLoader = Future<Uint8List?> Function(String url);

/// "What was on screen": the meeting's approved screenshots as a horizontal strip in the summary,
/// the mobile twin of the Mac's `MeetingNoteScreenshotStrip` and web's `ConversationDetailPanel`.
///
/// Mobile has no header banner, so the banner frame leads the strip. The section is absent — not
/// an error card, not an empty state — when the set is empty, when the fetch fails, and when the
/// account's `meeting_note_screenshots_enabled` setting is off (the server answers that case with
/// an empty set). A meeting without screenshots is the normal case.
///
/// Signed URLs live 60 minutes. The set is re-fetched shortly before they expire while the note is
/// open, before opening the viewer on a stale set, and once when a thumbnail fails after its
/// expiry — never by retrying a dead URL.
class ConversationScreenshotsSection extends StatefulWidget {
  const ConversationScreenshotsSection({
    super.key,
    required this.conversationId,
    this.fetch,
    this.delete,
    this.loadBytes,
    this.now,
    this.gutter = OmiSpacing.md,
  });

  final String conversationId;

  /// Test seams; production leaves these null.
  final ConversationScreenshotsFetch? fetch;
  final ConversationScreenshotDelete? delete;
  final ScreenshotBytesLoader? loadBytes;
  final DateTime Function()? now;

  /// The page's side margin. The strip scrolls edge to edge; the heading and the first tile line
  /// up with the rest of the note by padding this much inside.
  final double gutter;

  static const tileWidth = 144.0;
  static const tileHeight = 90.0;

  /// Treat URLs as dead this long before the server's stated expiry: covers device clock skew and
  /// the time a full-size download takes.
  static const expiryMargin = Duration(minutes: 2);

  @override
  State<ConversationScreenshotsSection> createState() => _ConversationScreenshotsSectionState();
}

class _ConversationScreenshotsSectionState extends State<ConversationScreenshotsSection> {
  ConversationScreenshots? _set;
  Future<void>? _inflight;
  Timer? _refreshTimer;

  /// One error-driven refresh per fetched set, so a URL that fails for any reason other than
  /// expiry can never turn into a fetch loop.
  bool _errorRefreshSpent = false;

  /// Which answer may still be drawn. Bumped when a fetch starts and when a delete commits, so a
  /// response can only be adopted if nothing newer has started or landed since it was asked for —
  /// in particular a refresh that was in flight across a delete cannot resurrect the deleted tile,
  /// whichever of the two started first.
  int _generation = 0;

  DateTime _now() => (widget.now ?? DateTime.now)();

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _load() {
    return _inflight ??= _fetch().whenComplete(() => _inflight = null);
  }

  Future<void> _fetch() async {
    final generation = ++_generation;
    ApiResult<ConversationScreenshots> result;
    try {
      result = await (widget.fetch ?? getConversationScreenshots)(widget.conversationId);
    } catch (e) {
      // Typed failures arrive as ApiFailure; anything thrown is unexpected (an unconfigured
      // environment, a malformed row). This section is decoration on a note and must never take
      // the note down with it, so it is logged and treated like any other failure: nothing drawn.
      Logger.debug('Meeting screenshots fetch threw: ${e.runtimeType}');
      result = const ApiFailure(ApiProblem(ApiProblemKind.decode));
    }
    if (!mounted || generation != _generation) return;
    switch (result) {
      case ApiSuccess(:final data):
        _adopt(data);
      case ApiFailure():
        // A failed fetch leaves nothing trustworthy to draw: the previous set's URLs are either
        // about to die or already dead. Hide rather than show broken tiles or an error.
        _adopt(null);
    }
  }

  void _adopt(ConversationScreenshots? set) {
    _refreshTimer?.cancel();
    _refreshTimer = null;
    setState(() => _set = set);
    // A set that arrives already stale (a skewed clock, a slow response) gets no error-driven
    // refresh: its replacement would arrive the same way, and that is a loop.
    _errorRefreshSpent = _isStale;
    final expiresAt = set?.urlsExpireAt;
    if (expiresAt == null) return;
    final delay = expiresAt.subtract(ConversationScreenshotsSection.expiryMargin).difference(_now());
    // A set that arrives already inside the margin (a skewed clock) is not re-fetched on a timer —
    // that would loop. Opening a frame still re-fetches on demand.
    if (delay > Duration.zero) _refreshTimer = Timer(delay, () => unawaited(_load()));
  }

  bool get _isStale {
    final expiresAt = _set?.urlsExpireAt;
    if (expiresAt == null) return false;
    return !_now().isBefore(expiresAt.subtract(ConversationScreenshotsSection.expiryMargin));
  }

  Future<void> _ensureFresh() async {
    if (_isStale) await _load();
  }

  void _onThumbnailFailed() {
    if (_errorRefreshSpent || !_isStale) return;
    _errorRefreshSpent = true;
    // Reported from inside a build; the fetch itself is async, so this never re-enters build.
    unawaited(_load());
  }

  Future<Uint8List?> _contentBytes(String frameId) async {
    await _ensureFresh();
    final frame = _set?.frames.where((f) => f.id == frameId).firstOrNull;
    if (frame == null) return null;
    return (widget.loadBytes ?? _downloadBytes)(frame.contentUrl);
  }

  String _captionOf(BuildContext context, ConversationScreenshot frame) =>
      frame.caption.trim().isEmpty ? context.l10n.meetingScreenshotFallbackCaption : frame.caption.trim();

  Future<void> _open(ConversationScreenshot tapped) async {
    await _ensureFresh();
    if (!mounted) return;
    final frames = _set?.frames ?? const <ConversationScreenshot>[];
    final index = frames.indexWhere((f) => f.id == tapped.id);
    if (index < 0) return;
    await MediaViewerPage.open(
      context,
      initialIndex: index,
      items: [
        for (final frame in frames)
          MediaViewerItem(
            // Lazy and always against the freshest set: a page first shown after the URLs expired
            // re-fetches instead of rendering a broken image.
            bytesLoader: () => _contentBytes(frame.id),
            mimeType: 'image/jpeg',
            showCaptionStrip: true,
            caption: _captionOf(context, frame),
          ),
      ],
    );
  }

  Future<void> _showMenu(ConversationScreenshot frame) {
    return showOmiRowMenu(
      context,
      title: _captionOf(context, frame),
      actions: [
        OmiMenuAction(icon: Icons.open_in_full, label: context.l10n.open, onSelected: () => unawaited(_open(frame))),
        OmiMenuAction(
          icon: Icons.delete_outline,
          label: context.l10n.delete,
          isDestructive: true,
          onSelected: () => unawaited(_confirmDelete(frame)),
        ),
      ],
    );
  }

  Future<void> _confirmDelete(ConversationScreenshot frame) async {
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.deleteMeetingScreenshotTitle,
      message: context.l10n.deleteMeetingScreenshotMessage,
      confirmLabel: context.l10n.delete,
      destructive: true,
    );
    if (!confirmed || !mounted) return;
    final result = await (widget.delete ?? deleteConversationScreenshot)(widget.conversationId, frame.id);
    if (!mounted) return;
    switch (result) {
      case ApiSuccess(:final data):
        // The server's set, not a local prediction: it may have promoted another frame to banner.
        // Committing it fences off every fetch already in flight — each was asked before the
        // delete landed and would bring the frame back.
        _generation++;
        _adopt(data);
      case ApiFailure():
        OmiFeedback.error(context, context.l10n.somethingWentWrong);
    }
  }

  @override
  Widget build(BuildContext context) {
    final frames = _set?.frames ?? const <ConversationScreenshot>[];
    if (frames.isEmpty) return const SliverToBoxAdapter(child: SizedBox.shrink());
    // A horizontal list needs a fixed height; measure one caption line at the reader's text size
    // rather than guessing, so large text grows the strip instead of clipping it.
    final captionHeight = (TextPainter(
      text: TextSpan(text: 'Ag', style: DefaultTextStyle.of(context).style.merge(_ScreenshotTile.captionStyle)),
      textDirection: Directionality.of(context),
      textScaler: MediaQuery.textScalerOf(context),
      maxLines: 1,
    )..layout())
        .height;
    return SliverToBoxAdapter(
      child: Padding(
        key: const ValueKey('conversation_screenshots_section'),
        padding: const EdgeInsets.only(top: OmiSpacing.md, bottom: OmiSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Semantics(
              header: true,
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: widget.gutter),
                child: Row(
                  children: [
                    ExcludeSemantics(
                      child: Icon(Icons.photo_library_outlined, size: 18, color: OmiColors.textSecondary),
                    ),
                    const SizedBox(width: OmiSpacing.xs),
                    Flexible(
                      child: Text(
                        context.l10n.meetingScreenshotsTitle,
                        style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: OmiSpacing.sm),
            SizedBox(
              height: ConversationScreenshotsSection.tileHeight + OmiSpacing.xxs + captionHeight,
              // A builder, so only the tiles on screen are built and only their thumbnails fetched
              // and decoded.
              child: ListView.separated(
                key: const ValueKey('conversation_screenshots_strip'),
                scrollDirection: Axis.horizontal,
                // Edge to edge: the strip scrolls under the page's side margins, and the list's own
                // padding lines the first and last tile up with the note's text.
                padding: EdgeInsets.symmetric(horizontal: widget.gutter),
                itemCount: frames.length,
                separatorBuilder: (_, __) => const SizedBox(width: OmiSpacing.xs),
                itemBuilder: (context, index) {
                  final frame = frames[index];
                  return _ScreenshotTile(
                    key: ValueKey('conversation_screenshot_${frame.id}'),
                    frame: frame,
                    caption: _captionOf(context, frame),
                    onTap: () => unawaited(_open(frame)),
                    onLongPress: () => unawaited(_showMenu(frame)),
                    onDelete: () => unawaited(_confirmDelete(frame)),
                    onThumbnailFailed: _onThumbnailFailed,
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// How the viewer and share sheet fetch a full-size frame. The URL is pre-signed; it carries no
/// Omi credentials, so it goes out without the app's auth headers.
Future<Uint8List?> _downloadBytes(String url) async {
  const maxBytes = 32 * 1024 * 1024;
  try {
    final response = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 20));
    if (response.statusCode != 200 || response.bodyBytes.isEmpty || response.bodyBytes.length > maxBytes) {
      return null;
    }
    return response.bodyBytes;
  } on Exception {
    return null;
  }
}

/// The image provider a tile draws, decoded at the tile's pixel size rather than the frame's.
ImageProvider screenshotThumbnailProvider(String url, double devicePixelRatio) => ResizeImage(
      NetworkImage(url),
      width: (ConversationScreenshotsSection.tileWidth * devicePixelRatio).round(),
      policy: ResizeImagePolicy.fit,
    );

class _ScreenshotTile extends StatelessWidget {
  const _ScreenshotTile({
    super.key,
    required this.frame,
    required this.caption,
    required this.onTap,
    required this.onLongPress,
    required this.onDelete,
    required this.onThumbnailFailed,
  });

  final ConversationScreenshot frame;
  final String caption;
  final VoidCallback onTap;
  final VoidCallback onLongPress;
  final VoidCallback onDelete;
  final VoidCallback onThumbnailFailed;

  static TextStyle get captionStyle => OmiType.footnote.copyWith(color: OmiColors.textSecondary);

  IconData get _glyph => switch (frame.sourceBadge) {
        'code' => Icons.code,
        'browser' => Icons.public,
        'document' => Icons.description_outlined,
        'slides' => Icons.slideshow_outlined,
        'product' => Icons.apps_outlined,
        _ => Icons.image_outlined,
      };

  Widget _placeholder() => ColoredBox(
        color: OmiColors.surface2,
        child: Center(child: Icon(_glyph, size: 22, color: OmiColors.textTertiary)),
      );

  @override
  Widget build(BuildContext context) {
    final dpr = MediaQuery.devicePixelRatioOf(context);
    // The actions live here, on the node a screen reader lands on: double-tap opens, and the
    // rotor / actions menu offers Open and Delete directly. The gesture detector below is for
    // touch only, so it stays out of the semantics tree and the node carries one set of actions.
    return Semantics(
      button: true,
      label: caption,
      onTap: onTap,
      customSemanticsActions: {
        CustomSemanticsAction(label: context.l10n.open): onTap,
        CustomSemanticsAction(label: context.l10n.delete): onDelete,
      },
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        excludeFromSemantics: true,
        onTap: onTap,
        onLongPress: onLongPress,
        child: SizedBox(
          width: ConversationScreenshotsSection.tileWidth,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: ConversationScreenshotsSection.tileWidth,
                height: ConversationScreenshotsSection.tileHeight,
                foregroundDecoration: BoxDecoration(
                  borderRadius: OmiRadius.mdAll,
                  border: Border.all(color: OmiColors.border),
                ),
                child: ClipRRect(
                  borderRadius: OmiRadius.mdAll,
                  child: Image(
                    image: screenshotThumbnailProvider(frame.thumbnailUrl, dpr),
                    fit: BoxFit.cover,
                    gaplessPlayback: true,
                    excludeFromSemantics: true,
                    frameBuilder: (context, child, frameNumber, wasSynchronouslyLoaded) =>
                        wasSynchronouslyLoaded || frameNumber != null ? child : _placeholder(),
                    errorBuilder: (context, error, stackTrace) {
                      onThumbnailFailed();
                      return _placeholder();
                    },
                  ),
                ),
              ),
              const SizedBox(height: OmiSpacing.xxs),
              ExcludeSemantics(
                child: Text(
                  caption,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: captionStyle,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
