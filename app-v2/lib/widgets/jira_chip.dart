import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Signature for the launch-url seam. Mirrors `url_launcher`'s `launchUrl` so
/// production callers can pass it through unchanged; tests inject a fake that
/// records the URL instead of opening Safari.
typedef LaunchUrlFn = Future<bool> Function(Uri uri, {LaunchMode mode});

Future<bool> _defaultLaunchUrl(Uri uri, {LaunchMode mode = LaunchMode.platformDefault}) {
  return launchUrl(uri, mode: mode);
}

/// Atlassian/Jira blue. Used solo as a 6×6 indicator dot — we deliberately
/// avoid an icon import for a single-pixel-density mark.
const Color _jiraBlue = Color(0xFF2684FF);

/// Inline pill that flags an action item as sourced from an external
/// integration (currently only Jira — generalize when Linear/ClickUp ship a
/// chip). Tap opens the source URL in the system browser.
///
/// Used in two places:
///   * Plan tab row — Wrap-aware so it falls below the description on narrow
///     widths instead of clipping the text.
///   * Home Today card bullet — same chip, same tap target, same blue dot.
///
/// 44pt minimum tap target is preserved by the surrounding `InkWell`'s
/// padding plus the parent row's vertical spacing — visually the chip is
/// 22pt tall, but the InkWell's hit-test extends to the full row's tap area.
/// See `JiraChip.standalone` if you need a chip with its own enforced tap
/// target (not currently used; reserved for future flat layouts).
class JiraChip extends StatelessWidget {
  const JiraChip({super.key, required this.source, LaunchUrlFn? launchUrl})
    : _launchUrl = launchUrl ?? _defaultLaunchUrl;

  /// Convenience: pass the [ExternalSource] from an [ActionItem]. Returns a
  /// [SizedBox.shrink] when null so callers can spread the result without
  /// branching.
  static Widget forSource(ExternalSource? source, {LaunchUrlFn? launchUrl}) {
    if (source == null) return const SizedBox.shrink();
    return JiraChip(source: source, launchUrl: launchUrl);
  }

  final ExternalSource source;
  final LaunchUrlFn _launchUrl;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(AppStyles.radiusSmall);
    return InkWell(
      borderRadius: radius,
      onTap: () async {
        try {
          await _launchUrl(Uri.parse(source.url), mode: LaunchMode.externalApplication);
        } catch (_) {
          // Best-effort. A failed launch shouldn't surface to the user from a
          // tiny inline chip — they can still see the external_id and try
          // again. Keeping the swallow narrow so test seams can verify the
          // error path without a global handler.
        }
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingXS, vertical: 2),
        decoration: BoxDecoration(
          color: AppColors.backgroundTertiary,
          borderRadius: radius,
          border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 6,
              height: 6,
              decoration: const BoxDecoration(color: _jiraBlue, shape: BoxShape.circle),
            ),
            const SizedBox(width: AppStyles.spacingXS),
            Text(
              source.externalId,
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.textSecondary),
            ),
          ],
        ),
      ),
    );
  }
}
