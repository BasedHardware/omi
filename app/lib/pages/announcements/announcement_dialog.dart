import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/models/announcement.dart';
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
      builder: (context) => AnnouncementDialog(announcement: announcement),
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
                      OmiSpacing.xl, imageUrl != null ? OmiSpacing.xl : 0, OmiSpacing.xl, OmiSpacing.lg),
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
                            _openAction(content.cta!.action);
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

  Future<void> _openAction(String action) async {
    final uri = Uri.tryParse(action);
    if (uri == null) {
      debugPrint('Invalid URL: $action');
      return;
    }
    try {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (e) {
      debugPrint('Failed to open URL: $e');
    }
  }
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
        child: const Center(child: OmiSpinner(color: OmiColors.textSecondary)),
      ),
      errorWidget: (context, url, error) => Container(
        height: 180,
        color: OmiColors.surface2,
        child: const Icon(Icons.campaign_outlined, color: OmiColors.textTertiary, size: 48),
      ),
    );
  }
}
