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
/// chip).
///
/// Two tap zones:
///   * The external-id portion ("PROJ-123") always opens the source URL in
///     Safari (the integration's web view is the truth-source for status).
///   * The project portion (the leading "PROJ" pill, only rendered when
///     [onProjectTap] is non-null AND `metadata.project_key` is present) is
///     a Plan-screen-only filter trigger. Tapping the project chip inside
///     Plan applies a transient "this project only" filter; everywhere else
///     we leave the project hidden inside the single-pill rendering.
///
/// Used in two places:
///   * Plan tab row — Wrap-aware so it falls below the description on narrow
///     widths instead of clipping the text.
///   * Home Today card bullet — same chip, same tap target, same blue dot.
///
/// 44pt minimum tap target is preserved by the surrounding `InkWell`'s
/// padding plus the parent row's vertical spacing — visually the chip is
/// 22pt tall, but the InkWell's hit-test extends to the full row's tap area.
class JiraChip extends StatelessWidget {
  const JiraChip({super.key, required this.source, LaunchUrlFn? launchUrl, this.onProjectTap})
    : _launchUrl = launchUrl ?? _defaultLaunchUrl;

  /// Convenience: pass the [ExternalSource] from an [ActionItem]. Returns a
  /// [SizedBox.shrink] when null so callers can spread the result without
  /// branching.
  static Widget forSource(ExternalSource? source, {LaunchUrlFn? launchUrl, VoidCallback? onProjectTap}) {
    if (source == null) return const SizedBox.shrink();
    return JiraChip(source: source, launchUrl: launchUrl, onProjectTap: onProjectTap);
  }

  final ExternalSource source;
  final LaunchUrlFn _launchUrl;

  /// Plan-screen filter hook. When non-null AND the source has a
  /// `project_key`, the chip splits into two pills (project + external-id);
  /// tapping the project pill calls this. When null (Home, default), the
  /// chip stays a single pill that opens the URL.
  final VoidCallback? onProjectTap;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(AppStyles.radiusSmall);
    final projectKey = source.jiraProjectKey;
    final showSplit = onProjectTap != null && projectKey != null && projectKey.isNotEmpty;
    if (showSplit) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _ProjectPill(projectKey: projectKey, onTap: onProjectTap!),
          const SizedBox(width: AppStyles.spacingXS),
          _IdPill(source: source, launchUrl: _launchUrl),
        ],
      );
    }
    return InkWell(
      borderRadius: radius,
      onTap: () => _openUrl(),
      child: _IdPillBody(externalId: source.externalId),
    );
  }

  Future<void> _openUrl() async {
    try {
      await _launchUrl(Uri.parse(source.url), mode: LaunchMode.externalApplication);
    } catch (_) {
      // Best-effort. A failed launch shouldn't surface to the user from a
      // tiny inline chip — they can still see the external_id and try
      // again. Keeping the swallow narrow so test seams can verify the
      // error path without a global handler.
    }
  }
}

/// Standalone external-id pill (used inside the split layout). Same visual
/// as the single-pill default, but factored out so the project-pill split
/// stays declarative.
class _IdPill extends StatelessWidget {
  const _IdPill({required this.source, required this.launchUrl});
  final ExternalSource source;
  final LaunchUrlFn launchUrl;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
      onTap: () async {
        try {
          await launchUrl(Uri.parse(source.url), mode: LaunchMode.externalApplication);
        } catch (_) {
          // See JiraChip._openUrl — failed launches are intentionally silent.
        }
      },
      child: _IdPillBody(externalId: source.externalId),
    );
  }
}

class _IdPillBody extends StatelessWidget {
  const _IdPillBody({required this.externalId});
  final String externalId;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingXS, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.backgroundTertiary,
        borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
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
            externalId,
            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.textSecondary),
          ),
        ],
      ),
    );
  }
}

/// Project-only pill, rendered when the chip is in split mode (Plan screen
/// with a project_key). Tapping calls back into the parent Plan to set the
/// "this project" filter.
class _ProjectPill extends StatelessWidget {
  const _ProjectPill({required this.projectKey, required this.onTap});
  final String projectKey;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingXS, vertical: 2),
        decoration: BoxDecoration(
          color: AppColors.backgroundTertiary,
          borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
          border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
        ),
        child: Text(
          projectKey,
          style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.textSecondary),
        ),
      ),
    );
  }
}
