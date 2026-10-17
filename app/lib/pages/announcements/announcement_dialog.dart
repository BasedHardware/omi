import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/models/announcement.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// How the reader left an announcement or feature screen.
enum AnnouncementOutcome {
  /// Tapped the call to action.
  cta,

  /// Closed it with the X or finished it ("Got It"): seen, do not show again.
  closed,

  /// Chose Not Now: postpone, show it again later.
  notNow,

  /// Left without answering (system back). Not an answer; show it again later.
  none;

  /// Whether this outcome is an explicit answer that marks the announcement seen
  /// (docs/ux-contract.md §14: never on a stray tap).
  bool get marksSeen => this == AnnouncementOutcome.cta || this == AnnouncementOutcome.closed;
}

/// A product announcement: optional image, title, body, optional call to action, Not Now and a
/// trailing close X. The scrim does not dismiss it, so a stray tap never counts as an answer.
class AnnouncementDialog extends StatelessWidget {
  final Announcement announcement;

  const AnnouncementDialog({super.key, required this.announcement});

  /// Shows the announcement and resolves with how the reader left it.
  static Future<AnnouncementOutcome> show(BuildContext context, Announcement announcement) async {
    final outcome = await showDialog<AnnouncementOutcome>(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.black87,
      builder: (context) => nativePresentationEnabled
          ? NativeAnnouncementDialog(announcement: announcement)
          : AnnouncementDialog(announcement: announcement),
    );
    return outcome ?? AnnouncementOutcome.none;
  }

  @override
  Widget build(BuildContext context) {
    final content = announcement.announcementContent;
    final imageUrl = content.imageUrl;

    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl, vertical: 40),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 360),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.xlAll,
          boxShadow: [
            BoxShadow(color: Colors.black.withValues(alpha: 0.4), blurRadius: 30, offset: const Offset(0, 10)),
          ],
        ),
        child: ClipRRect(
          borderRadius: OmiRadius.xlAll,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (imageUrl != null)
                  Stack(
                    children: [
                      _AnnouncementImage(url: imageUrl),
                      Positioned(
                        top: OmiSpacing.xxs,
                        right: OmiSpacing.xxs,
                        child: OmiCloseButton.circled(
                          fillColor: Colors.black.withValues(alpha: 0.5),
                          onPressed: () => Navigator.pop(context, AnnouncementOutcome.closed),
                        ),
                      ),
                    ],
                  )
                else
                  Align(
                    alignment: AlignmentDirectional.topEnd,
                    child: Padding(
                      padding: const EdgeInsets.only(top: OmiSpacing.xxs, right: OmiSpacing.xxs),
                      child: OmiCloseButton(
                        color: OmiColors.textSecondary,
                        onPressed: () => Navigator.pop(context, AnnouncementOutcome.closed),
                      ),
                    ),
                  ),
                Padding(
                  padding: EdgeInsets.fromLTRB(
                    OmiSpacing.xl,
                    imageUrl != null ? OmiSpacing.xl : 0,
                    OmiSpacing.xl,
                    OmiSpacing.lg,
                  ),
                  child: Column(
                    children: [
                      Semantics(
                        header: true,
                        child: Text(
                          content.title,
                          style: OmiType.title2.copyWith(fontWeight: FontWeight.bold, height: 1.2),
                          textAlign: TextAlign.center,
                        ),
                      ),
                      const SizedBox(height: OmiSpacing.md),
                      Text(
                        content.body,
                        style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.5),
                        textAlign: TextAlign.center,
                      ),
                      if (content.cta != null) ...[
                        const SizedBox(height: 28),
                        OmiButton(
                          label: content.cta!.text,
                          expand: true,
                          onPressed: () {
                            Navigator.pop(context, AnnouncementOutcome.cta);
                            _openAnnouncementAction(content.cta!.action);
                          },
                        ),
                      ],
                      const SizedBox(height: OmiSpacing.xs),
                      OmiButton.tertiary(
                        label: context.l10n.notNow,
                        onPressed: () => Navigator.pop(context, AnnouncementOutcome.notNow),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

Future<void> _openAnnouncementAction(String action) async {
  switch (AnnouncementAction.parse(action)) {
    case AnnouncementRoute(:final route):
      // An in-app destination opens inside the existing Home (ux-contract §1).
      await HomeNavigation.openRoute(route);
    case AnnouncementUrl(:final uri):
      try {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      } catch (e) {
        debugPrint('Failed to open URL: $e');
      }
    case null:
      debugPrint('Unsupported announcement action: $action');
  }
}

/// [text] as literal inline Markdown: the native renderer reads rich text blocks as Markdown, so
/// server-written copy escapes every punctuation mark that could start emphasis, code, a link, an
/// entity or HTML. A link the renderer still detects is discarded: the row's link whitelist is empty.
String nativeMarkdownLiteral(String text) =>
    text.replaceAllMapped(RegExp(r'[\\`*_\[\]<>~!&]'), (match) => '\\${match[0]}');

/// The native rich-text image block for a server image: HTTPS only, otherwise no block at all.
Map<String, Object>? nativeAnnouncementImageBlock(String? url) {
  // Only a URL already in its normalized spelling: Swift's stricter parser must accept exactly what
  // Dart checked, or one odd image would cost the whole native surface.
  if (url == null || !url.startsWith('https://') || Uri.tryParse(url)?.toString() != url) return null;
  if (nativeImageUri(url) == null) return null;
  return {'kind': 'image', 'text': '', 'uri': url, 'indent': 0, 'prefix': ''};
}

/// The announcement as one native surface in the same non-dismissible dialog route: the close X
/// (closed), the image, title and body, the call to action (cta, then the existing action owner)
/// and Not Now (notNow). System back still pops without an answer (none). A host that cannot draw
/// it keeps the complete [AnnouncementDialog].
class NativeAnnouncementDialog extends StatelessWidget {
  const NativeAnnouncementDialog({super.key, required this.announcement});

  final Announcement announcement;

  /// Answers once: a second command during the closing transition must not pop the route beneath.
  static void _answer(BuildContext context, AnnouncementOutcome outcome) {
    if (ModalRoute.of(context)?.isCurrent != true) return;
    Navigator.of(context).pop(outcome);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final content = announcement.announcementContent;
    final cta = content.cta;
    final image = nativeAnnouncementImageBlock(content.imageUrl);
    final height = MediaQuery.sizeOf(context).height;
    return IosNativeSurface(
      title: '',
      fallback: AnnouncementDialog(announcement: announcement),
      nativeWrapper: (view) => Dialog(
        backgroundColor: Colors.transparent,
        insetPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl, vertical: 40),
        clipBehavior: Clip.antiAlias,
        shape: const RoundedRectangleBorder(borderRadius: OmiRadius.xlAll),
        child: SizedBox(width: 360, height: height * 0.8, child: view),
      ),
      toolbar: [
        NativeRow('announcement_close', l10n.close,
            symbol: 'xmark', action: (_) => _answer(context, AnnouncementOutcome.closed)),
      ],
      sections: [
        NativeSection('announcement', [
          NativeRow('announcement_body', content.title, kind: 'rich_text', blocks: [
            if (image != null) image,
            {'kind': 'heading', 'text': nativeMarkdownLiteral(content.title), 'level': 1, 'indent': 0, 'prefix': ''},
            {'kind': 'text', 'text': nativeMarkdownLiteral(content.body), 'indent': 0, 'prefix': ''},
          ]),
        ]),
        NativeSection('announcement_actions', [
          if (cta != null)
            NativeRow('announcement_cta', cta.text, action: (_) {
              if (ModalRoute.of(context)?.isCurrent != true) return;
              Navigator.of(context).pop(AnnouncementOutcome.cta);
              _openAnnouncementAction(cta.action);
            }),
          NativeRow('announcement_not_now', l10n.notNow, action: (_) => _answer(context, AnnouncementOutcome.notNow)),
        ]),
      ],
    );
  }
}

/// Where an announcement's call to action leads. The backend writes `navigate:/memories` for an
/// in-app route and `url:https://…` for a web page (backend/models/announcement.py); a bare
/// `https://…` or `/route` is accepted too. Only http(s) URLs with a host are opened.
sealed class AnnouncementAction {
  const AnnouncementAction();

  static AnnouncementAction? parse(String action) {
    final value = action.trim();
    if (value.startsWith('navigate:')) {
      final route = value.substring('navigate:'.length).trim();
      return route.isEmpty ? null : AnnouncementRoute(route.startsWith('/') ? route : '/$route');
    }
    if (value.startsWith('/')) return AnnouncementRoute(value);
    final uri = Uri.tryParse(value.startsWith('url:') ? value.substring('url:'.length).trim() : value);
    // Web pages only: a server-written action must not reach tel:, file: or another app's scheme.
    if (uri == null || (uri.scheme != 'https' && uri.scheme != 'http') || uri.host.isEmpty) return null;
    return AnnouncementUrl(uri);
  }
}

class AnnouncementRoute extends AnnouncementAction {
  const AnnouncementRoute(this.route);
  final String route;
}

class AnnouncementUrl extends AnnouncementAction {
  const AnnouncementUrl(this.uri);
  final Uri uri;
}

class _AnnouncementImage extends StatelessWidget {
  const _AnnouncementImage({required this.url});

  final String url;

  @override
  Widget build(BuildContext context) {
    return CachedNetworkImage(
      imageUrl: url,
      width: double.infinity,
      height: 180,
      fit: BoxFit.cover,
      placeholder: (context, url) => Container(
        height: 180,
        color: OmiColors.surface2,
        child: Center(child: OmiSpinner(color: OmiColors.textSecondary)),
      ),
      errorWidget: (context, url, error) => Container(
        height: 180,
        color: OmiColors.surface2,
        child: Icon(Icons.campaign_outlined, color: OmiColors.textTertiary, size: 48),
      ),
    );
  }
}
