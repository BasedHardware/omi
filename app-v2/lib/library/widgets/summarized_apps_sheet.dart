import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/apps/app_model.dart';
import 'package:nooto_v2/apps/apps_provider.dart';
import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/library/conversation_model.dart';
import 'package:nooto_v2/library/conversations_provider.dart';
import 'package:nooto_v2/theme/app_theme.dart';

/// Bottom sheet that lets the user pick which app re-summarizes a
/// conversation. Mirrors the legacy `/app` SummarizedAppsBottomSheet —
/// suggested apps surface up top, then installed apps, with a check on
/// the currently-active app id.
///
/// Tapping a row triggers `ConversationsProvider.reprocessWithApp` and
/// closes the sheet immediately. Loading state is owned by the parent
/// detail screen via `isReprocessing(conversationId)`, surfaced through
/// the `AppResultMarkdown` shimmer.
class SummarizedAppsBottomSheet extends StatelessWidget {
  const SummarizedAppsBottomSheet({super.key, required this.conversationId, this.currentAppId});

  final String conversationId;

  /// App id currently producing the summary (highlighted in the list).
  /// Resolved from `conversation.summarizedApp?.appId` at open time.
  final String? currentAppId;

  /// Open the sheet as a modal. Shorthand mirrors how the legacy app
  /// invokes its sheet via `showModalBottomSheet`.
  static Future<void> show(BuildContext context, {required String conversationId, String? currentAppId}) {
    return showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => SummarizedAppsBottomSheet(conversationId: conversationId, currentAppId: currentAppId),
    );
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.7,
      minChildSize: 0.4,
      maxChildSize: 0.9,
      expand: false,
      builder: (context, scrollController) {
        return _Sheet(conversationId: conversationId, currentAppId: currentAppId, scrollController: scrollController);
      },
    );
  }
}

class _Sheet extends StatelessWidget {
  const _Sheet({required this.conversationId, required this.currentAppId, required this.scrollController});

  final String conversationId;
  final String? currentAppId;
  final ScrollController scrollController;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final apps = context.watch<AppsProvider>();
    final convs = context.read<ConversationsProvider>();
    final ConversationItem? conversation = convs.byId(conversationId);

    final suggestedIds = (conversation?.suggestedSummarizationApps ?? const <String>[]).toSet();
    final allEnabled = apps.enabledApps;
    final suggestedApps = <NooApp>[];
    final installedApps = <NooApp>[];
    final seen = <String>{};

    // Resolve suggested ids in order — they may not all be installed; we
    // surface the ones we can render, drop the rest.
    for (final id in suggestedIds) {
      final app = apps.appById(id);
      if (app != null && seen.add(app.id)) {
        suggestedApps.add(app);
      }
    }
    for (final app in allEnabled) {
      if (seen.add(app.id)) installedApps.add(app);
    }
    installedApps.sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));

    return Container(
      decoration: const BoxDecoration(
        color: AppColors.backgroundPrimary,
        borderRadius: BorderRadius.vertical(top: Radius.circular(AppStyles.radiusXLarge)),
      ),
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).padding.bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            margin: const EdgeInsets.only(top: AppStyles.spacingS),
            width: 36,
            height: 4,
            decoration: BoxDecoration(color: AppColors.backgroundQuaternary, borderRadius: BorderRadius.circular(2)),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppStyles.spacingL,
              AppStyles.spacingM,
              AppStyles.spacingS,
              AppStyles.spacingM,
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    l.chooseSummarizationApp,
                    style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
                  ),
                ),
                IconButton(
                  iconSize: 18,
                  icon: const Icon(Icons.close_rounded, color: AppColors.textTertiary),
                  onPressed: () => Navigator.of(context).pop(),
                  tooltip: 'Close',
                ),
              ],
            ),
          ),
          Expanded(
            child: ListView(
              controller: scrollController,
              padding: const EdgeInsets.fromLTRB(0, 0, 0, AppStyles.spacingL),
              children: [
                if (suggestedApps.isNotEmpty) ...[
                  _SectionHeader(label: l.summarizedAppsSuggestedSection),
                  for (final app in suggestedApps)
                    _AppRow(
                      app: app,
                      conversationId: conversationId,
                      isSelected: app.id == currentAppId,
                      isSuggested: true,
                    ),
                ],
                if (installedApps.isNotEmpty) ...[
                  _SectionHeader(label: l.summarizedAppsAvailableSection),
                  for (final app in installedApps)
                    _AppRow(
                      app: app,
                      conversationId: conversationId,
                      isSelected: app.id == currentAppId,
                      isSuggested: false,
                    ),
                ],
                if (suggestedApps.isEmpty && installedApps.isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(AppStyles.spacingXL),
                    child: Text(
                      l.summarizedAppsEmpty,
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 14, color: AppColors.textTertiary),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppStyles.spacingL,
        AppStyles.spacingL,
        AppStyles.spacingL,
        AppStyles.spacingS,
      ),
      child: Text(
        label,
        style: const TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: AppColors.textTertiary,
          letterSpacing: 0.8,
        ),
      ),
    );
  }
}

class _AppRow extends StatelessWidget {
  const _AppRow({required this.app, required this.conversationId, required this.isSelected, required this.isSuggested});

  final NooApp app;
  final String conversationId;
  final bool isSelected;
  final bool isSuggested;

  Future<void> _handleTap(BuildContext context) async {
    final convs = context.read<ConversationsProvider>();
    final messenger = ScaffoldMessenger.maybeOf(context);
    final l = AppLocalizations.of(context);
    Navigator.of(context).pop();
    final ok = await convs.reprocessWithApp(conversationId, app.id);
    if (!ok && messenger != null) {
      messenger.showSnackBar(SnackBar(content: Text(l.reprocessFailed), backgroundColor: AppColors.errorColor));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return InkWell(
      onTap: () => _handleTap(context),
      child: Container(
        constraints: const BoxConstraints(minHeight: AppStyles.touchTargetMinimum),
        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingL, vertical: AppStyles.spacingM),
        child: Row(
          children: [
            _AppAvatar(url: app.imageUrl),
            const SizedBox(width: AppStyles.spacingM),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    app.name,
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                      color: AppColors.textPrimary,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  Wrap(
                    spacing: AppStyles.spacingXS,
                    runSpacing: AppStyles.spacingXS,
                    children: [
                      if (isSelected) _Pill(label: l.currentlyUsing, color: AppColors.brandPrimary),
                      if (isSuggested && !isSelected)
                        _Pill(label: l.suggestedForThisConversation, color: AppColors.warningColor),
                    ],
                  ),
                ],
              ),
            ),
            if (isSelected) const Icon(Icons.check_rounded, size: 18, color: AppColors.brandPrimary),
          ],
        ),
      ),
    );
  }
}

class _AppAvatar extends StatelessWidget {
  const _AppAvatar({required this.url});
  final String url;

  @override
  Widget build(BuildContext context) {
    if (url.isEmpty) {
      return Container(
        width: 32,
        height: 32,
        decoration: BoxDecoration(
          color: AppColors.backgroundTertiary,
          borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
        ),
        child: const Icon(Icons.extension_outlined, size: 16, color: AppColors.textTertiary),
      );
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
      child: CachedNetworkImage(
        imageUrl: url,
        width: 32,
        height: 32,
        fit: BoxFit.cover,
        placeholder: (_, _) => Container(width: 32, height: 32, color: AppColors.backgroundTertiary),
        errorWidget: (_, _, _) => Container(
          width: 32,
          height: 32,
          color: AppColors.backgroundTertiary,
          child: const Icon(Icons.broken_image_outlined, size: 16, color: AppColors.textTertiary),
        ),
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: AppStyles.spacingXS),
      padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color),
      ),
    );
  }
}
