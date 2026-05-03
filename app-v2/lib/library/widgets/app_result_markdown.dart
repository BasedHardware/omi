import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/apps/app_model.dart';
import 'package:nooto_v2/apps/apps_provider.dart';
import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/library/conversation_model.dart';
import 'package:nooto_v2/theme/app_theme.dart';
import 'package:nooto_v2/widgets/generative_ui/generative_markdown_widget.dart';

/// Renders the conversation's primary content slot. Three states:
///
/// 1. **App-produced summary** (`apps_results[0].content` non-empty) —
///    routes the markdown through [GenerativeMarkdownWidget] so embedded
///    XML tags (rich-list, chart, accordion, …) render as widgets. An
///    attribution row is appended at the bottom; tapping it triggers
///    [onPickApp] (typically: open the SummarizedAppsBottomSheet).
///
/// 2. **Plain overview fallback** (`apps_results` empty but
///    `Structured.overview` non-empty) — renders overview as plain
///    markdown, no attribution row.
///
/// 3. **Empty** (both missing) — collapses to a SizedBox.shrink().
///
/// Mirrors the legacy `/app` AppResultDetailWidget pattern but doesn't
/// own the picker open/close — the parent screen handles that so the
/// loading state can live alongside the conversation list.
class AppResultMarkdown extends StatelessWidget {
  const AppResultMarkdown({super.key, required this.item, required this.onPickApp, this.reprocessing = false});

  final ConversationItem item;

  /// Called when the user taps the attribution row (or the placeholder
  /// "no summary" caption when an app result exists but has empty content).
  final VoidCallback onPickApp;

  /// While true, the markdown body is hidden behind a centered spinner.
  /// Driven by `ConversationsProvider.isReprocessing(conversationId)`.
  final bool reprocessing;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final result = item.summarizedApp;
    final fallback = item.overview.trim();

    if (reprocessing) {
      return _ReprocessingPlaceholder(label: l.reprocessingConversation);
    }

    if (result != null && result.content.trim().isNotEmpty) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          GenerativeMarkdownWidget(content: result.content, selectable: true),
          const SizedBox(height: AppStyles.spacingM),
          _AttributionRow(appId: result.appId, onTap: onPickApp),
        ],
      );
    }

    if (result != null && result.content.trim().isEmpty) {
      // The backend wrote an apps_results entry but produced no content
      // (rare — usually means the prompt failed). Surface a tappable
      // empty state so the user can swap apps without dead-ending.
      return _EmptyResult(label: l.noSummaryForApp, onTap: onPickApp);
    }

    if (fallback.isEmpty) {
      // No overview AND no apps_results — surface a tappable empty state
      // so the user can pick an app to summarize this conversation.
      return _EmptyResult(label: l.summarizeWithApp, onTap: onPickApp);
    }

    // Plain Structured.overview fallback. No attribution row (text wasn't
    // produced by an app), but expose a tappable caption so the user can
    // upgrade this to an app-produced summary on demand.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        MarkdownBody(
          data: fallback,
          selectable: true,
          styleSheet: MarkdownStyleSheet(
            p: const TextStyle(fontSize: 15, color: AppColors.textSecondary, height: 1.5),
            pPadding: const EdgeInsets.only(bottom: AppStyles.spacingM),
          ),
        ),
        const SizedBox(height: AppStyles.spacingM),
        _PickAppCaption(label: l.summarizeWithApp, onTap: onPickApp),
      ],
    );
  }
}

/// Tappable caption shown at the bottom of the OVERVIEW slot when no app
/// has summarized this conversation yet. Opens the summarized-apps picker.
class _PickAppCaption extends StatelessWidget {
  const _PickAppCaption({required this.label, required this.onTap});
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          height: AppStyles.touchTargetMinimum,
          padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS, vertical: AppStyles.spacingS),
          alignment: Alignment.centerLeft,
          child: Row(
            children: [
              const Icon(Icons.auto_awesome_outlined, size: 18, color: AppColors.brandPrimary),
              const SizedBox(width: AppStyles.spacingS),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: AppColors.brandPrimary),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AttributionRow extends StatelessWidget {
  const _AttributionRow({required this.appId, required this.onTap});

  final String? appId;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final apps = context.watch<AppsProvider>();
    final NooApp? app = appId != null ? apps.appById(appId!) : null;

    return Semantics(
      button: true,
      label: app != null ? l.summarizedBy(app.name) : l.summaryTemplate,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          height: AppStyles.touchTargetMinimum,
          padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS, vertical: AppStyles.spacingS),
          alignment: Alignment.centerLeft,
          child: Row(
            children: [
              _AppIcon(app: app),
              const SizedBox(width: AppStyles.spacingS),
              Flexible(
                child: Text(
                  app != null ? l.summarizedBy(app.name) : l.summaryTemplate,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: AppColors.brandPrimary),
                ),
              ),
              const SizedBox(width: AppStyles.spacingXS),
              const Icon(Icons.expand_more_rounded, size: 18, color: AppColors.brandPrimary),
            ],
          ),
        ),
      ),
    );
  }
}

class _AppIcon extends StatelessWidget {
  const _AppIcon({required this.app});

  final NooApp? app;

  @override
  Widget build(BuildContext context) {
    final url = app?.imageUrl;
    if (url == null || url.isEmpty) {
      return Container(
        width: 20,
        height: 20,
        decoration: BoxDecoration(
          color: AppColors.backgroundTertiary,
          borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
        ),
        child: const Icon(Icons.extension_outlined, size: 12, color: AppColors.textTertiary),
      );
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
      child: CachedNetworkImage(
        imageUrl: url,
        width: 20,
        height: 20,
        fit: BoxFit.cover,
        placeholder: (_, _) => Container(width: 20, height: 20, color: AppColors.backgroundTertiary),
        errorWidget: (_, _, _) => Container(
          width: 20,
          height: 20,
          color: AppColors.backgroundTertiary,
          child: const Icon(Icons.broken_image_outlined, size: 12, color: AppColors.textTertiary),
        ),
      ),
    );
  }
}

class _EmptyResult extends StatelessWidget {
  const _EmptyResult({required this.label, required this.onTap});
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        height: AppStyles.touchTargetMinimum,
        alignment: Alignment.centerLeft,
        child: Text(label, style: const TextStyle(fontSize: 13, color: AppColors.textTertiary)),
      ),
    );
  }
}

class _ReprocessingPlaceholder extends StatelessWidget {
  const _ReprocessingPlaceholder({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingXL),
      child: Row(
        children: [
          const SizedBox(
            width: 18,
            height: 18,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(AppColors.brandPrimary),
            ),
          ),
          const SizedBox(width: AppStyles.spacingM),
          Text(label, style: const TextStyle(fontSize: 14, color: AppColors.textTertiary)),
        ],
      ),
    );
  }
}
