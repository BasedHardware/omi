import 'dart:async';

import 'package:flutter/material.dart';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/summary_generation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/extensions/string.dart';

/// Analytics id for Omi's own summary (the sheet-viewed event already calls it "auto").
const _omiAnalyticsId = 'auto';

/// The "Summarize with" sheet: Omi's own summary first (no network needed), the reader's templates,
/// suggestions for this conversation, then the catalog and the template creator. A tap selects a
/// row; Summarize runs it and closes the sheet.
Future<void> showSummaryTemplateSheet(BuildContext context) {
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.summarySheetTitle,
    padding: EdgeInsets.zero,
    builder: (_) => const SummaryTemplateSheet(),
  );
}

/// Body of [showSummaryTemplateSheet].
class SummaryTemplateSheet extends StatefulWidget {
  const SummaryTemplateSheet({super.key});

  @override
  State<SummaryTemplateSheet> createState() => _SummaryTemplateSheetState();
}

class _SummaryTemplateSheetState extends State<SummaryTemplateSheet> {
  late final ConversationDetailProvider _provider;

  /// The selected row; null is Omi.
  String? _selectedAppId;
  bool _useForNewConversations = false;
  String? _installingAppId;

  @override
  void initState() {
    super.initState();
    _provider = context.read<ConversationDetailProvider>();
    final current = _provider.getDisplayedSummarySelection();
    // Omi unless the summary on screen came from a template.
    _selectedAppId = current.isApp ? current.appId : null;
    PlatformManager.instance.analytics.summarizedAppSheetViewed(
      conversationId: _provider.conversation.id,
      currentSummarizedAppId: current.isApp ? current.appId : null,
    );
    _provider.addListener(_onProviderChanged);
    _provider.fetchAndCacheEnabledConversationApps();
    _provider.fetchAndCacheSuggestedApps();
  }

  @override
  void dispose() {
    _provider.removeListener(_onProviderChanged);
    super.dispose();
  }

  void _onProviderChanged() {
    if (!mounted) return;
    // Template lists land (or change) after the sheet opens; a selection inherited from the
    // displayed summary must not outlive its row.
    _dropUnresolvableSelection();
    setState(() {});
  }

  App? _appFor(String? appId) {
    if (appId == null) return null;
    return _provider.cachedEnabledConversationApps.firstWhereOrNull((app) => app.id == appId) ??
        _provider.cachedSuggestedApps.firstWhereOrNull((app) => app.id == appId) ??
        _provider.findAppById(appId);
  }

  /// Whether [_selectedAppId] still names a source the sheet offers (or is Omi). The displayed
  /// summary may reference a template that has since been deleted; such a selection must not
  /// survive into Summarize as an invisible, predictable 403/404. While the template lists are
  /// still loading nothing can prove the selection, so it does not resolve yet: Summarize stays
  /// disabled until a row backs it (or the provider change drops it onto Omi).
  bool get _selectionResolves {
    final appId = _selectedAppId;
    if (appId == null) return true; // Omi is always offered.
    final app = _appFor(appId);
    return app != null && (_isEnabled(app) || _isSuggested(app));
  }

  bool _isSuggested(App app) => _provider.cachedSuggestedApps.any((suggested) => suggested.id == app.id);

  bool _isEnabled(App app) =>
      _provider.cachedEnabledConversationApps.any((enabled) => enabled.id == app.id) ||
      _provider.isSuggestedAppAvailable(app.id);

  Future<void> _summarize() async {
    final provider = _provider;
    if (provider.loadingReprocessConversation || _installingAppId != null) return;
    // An inherited selection that no offered row backs (the template was deleted) is not a real
    // choice: fall back to Omi instead of submitting an invisible id.
    if (!_selectionResolves) _selectedAppId = null;
    final appId = _selectedAppId;
    final app = _appFor(appId);
    if (appId != null && app != null && !_isEnabled(app)) {
      // A suggestion the reader has not added yet: add it first, as the template list always did.
      setState(() => _installingAppId = appId);
      bool installed;
      try {
        installed = await provider.enableApp(app);
      } catch (_) {
        installed = false;
      }
      if (!mounted) return;
      setState(() => _installingAppId = null);
      if (!installed) {
        OmiFeedback.error(context, context.l10n.failedToInstallApp(app.name.decodeString));
        return;
      }
    }
    if (provider.loadingReprocessConversation) return;
    final previous = provider.getSummarySelection();
    PlatformManager.instance.analytics.summarizedAppSelected(
      conversationId: provider.conversation.id,
      selectedAppId: appId ?? _omiAnalyticsId,
      previousAppId: previous.isApp ? previous.appId : null,
    );
    // The server preference write runs alongside the summary; this request names its source itself.
    if (_useForNewConversations) unawaited(provider.setDefaultSummaryTemplateAppId(appId));
    if (mounted) Navigator.of(context).pop();
    await startSummary(provider, appId);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = _provider;
    final enabled = provider.cachedEnabledConversationApps;
    final enabledIds = {for (final app in enabled) app.id};
    final suggested = provider.cachedSuggestedApps.where((app) => !enabledIds.contains(app.id)).toList();
    final lastUsedId = provider.getLastUsedSummarizationAppId();
    final load = provider.enabledTemplatesLoad;
    // An inherited selection with no offered row behind it is not a choice yet: Summarize waits
    // for the lists to back it (or the provider change to drop it onto Omi).
    final busy = provider.loadingReprocessConversation || _installingAppId != null || !_selectionResolves;

    final templates = <Widget>[
      if (enabled.isNotEmpty)
        for (final app in enabled) _appRow(app, isLastUsed: app.id == lastUsedId)
      else if (load == SummaryTemplatesLoad.failed)
        _TemplatesLoadError(onRetry: provider.fetchAndCacheEnabledConversationApps)
      else if (load == SummaryTemplatesLoad.loaded)
        _InlineMessage(key: const Key('summary_templates_empty'), text: l10n.summaryNoTemplatesYet)
      else ...const [_SkeletonRow(), _SkeletonRow()],
    ];

    return SizedBox(
      height: MediaQuery.sizeOf(context).height * 0.75,
      child: Column(
        children: [
          Expanded(
            child: ListView(
              padding: const EdgeInsets.only(bottom: OmiSpacing.md),
              children: [
                _TemplateRow(
                  key: const Key('summary_template_omi'),
                  leading: const _OmiAvatar(),
                  title: l10n.omiAppName,
                  subtitle: l10n.summaryOmiTemplateSubtitle,
                  selected: _selectedAppId == null,
                  onTap: () => setState(() => _selectedAppId = null),
                ),
                _SectionHeader(l10n.summaryYourTemplates),
                ...templates,
                if (suggested.isNotEmpty) ...[
                  _SectionHeader(l10n.summarySuggestedTemplates),
                  for (final app in suggested) _appRow(app, isLastUsed: app.id == lastUsedId),
                ],
                const SizedBox(height: OmiSpacing.xs),
                Divider(height: 1, thickness: 0.5, color: OmiColors.border, indent: OmiSpacing.md),
                _LinkRow(
                  key: const Key('summary_template_browse'),
                  icon: Icons.grid_view_rounded,
                  label: l10n.summaryBrowseTemplates,
                  onTap: () => openSummaryTemplateCatalog(context),
                ),
                _LinkRow(
                  key: const Key('summary_template_create'),
                  icon: Icons.add_rounded,
                  label: l10n.summaryCreateYourOwn,
                  onTap: () => openCreateSummaryTemplate(context),
                ),
              ],
            ),
          ),
          Container(
            decoration: BoxDecoration(border: Border(top: BorderSide(color: OmiColors.border, width: 0.5))),
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xs),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: [
                DefaultTextStyle.merge(
                  style: OmiType.subhead,
                  child: OmiCheckboxRow(
                    key: const Key('summary_template_use_for_new'),
                    label: l10n.summaryUseForNewConversations,
                    value: _useForNewConversations,
                    onChanged: (value) => setState(() => _useForNewConversations = value),
                  ),
                ),
                const SizedBox(height: OmiSpacing.xs),
                OmiButton(
                  key: const Key('summary_template_confirm'),
                  label: l10n.summarize,
                  expand: true,
                  isLoading: _installingAppId != null,
                  onPressed: busy ? null : _summarize,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Marks an inherited selection dead as soon as no offered row backs it, so the check mark
  /// never sits on an invisible source while Summarize still submits its id. The template lists
  /// may still be arriving, so this only judges after they settle; until then the Summarize
  /// button is simply disabled ([_selectionResolves]).
  void _dropUnresolvableSelection() {
    if (_selectedAppId == null) return;
    if (_provider.enabledTemplatesLoad == SummaryTemplatesLoad.loading ||
        _provider.suggestedTemplatesLoad == SummaryTemplatesLoad.loading) {
      return;
    }
    if (_selectionResolves) return;
    _selectedAppId = null;
  }

  Widget _appRow(App app, {required bool isLastUsed}) {
    return _TemplateRow(
      key: Key('summary_template_app_${app.id}'),
      leading: _AppAvatar(app: app),
      title: app.name.decodeString,
      tag: isLastUsed ? context.l10n.lastUsedLabel : null,
      selected: _selectedAppId == app.id,
      installing: _installingAppId == app.id,
      onTap: () => setState(() => _selectedAppId = app.id),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      header: true,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.lg, OmiSpacing.md, OmiSpacing.xs),
        child: Text(text, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600)),
      ),
    );
  }
}

/// One selectable source: avatar, name, optional subtitle or tag, and a check when selected.
class _TemplateRow extends StatelessWidget {
  const _TemplateRow({
    super.key,
    required this.leading,
    required this.title,
    required this.selected,
    required this.onTap,
    this.subtitle,
    this.tag,
    this.installing = false,
  });

  final Widget leading;
  final String title;
  final String? subtitle;
  final String? tag;
  final bool selected;
  final bool installing;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      inMutuallyExclusiveGroup: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          OmiHaptics.selection();
          onTap();
        },
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: 2),
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: OmiSpacing.xs),
          constraints: const BoxConstraints(minHeight: 52),
          decoration: BoxDecoration(
            color: selected ? OmiColors.surface2 : Colors.transparent,
            borderRadius: OmiRadius.mdAll,
          ),
          child: Row(
            children: [
              leading,
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: OmiType.callout.copyWith(fontWeight: FontWeight.w500),
                          ),
                        ),
                        if (tag != null) ...[
                          const SizedBox(width: OmiSpacing.xs),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.smAll),
                            child: Text(
                              tag!,
                              style: OmiType.caption.copyWith(
                                color: OmiColors.textSecondary,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                    if (subtitle != null)
                      Text(subtitle!, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                  ],
                ),
              ),
              const SizedBox(width: OmiSpacing.xs),
              SizedBox(
                width: 24,
                child: installing
                    ? const OmiSpinner(size: OmiSpinnerSize.small)
                    : selected
                        ? Icon(Icons.check_circle_rounded, color: OmiColors.textPrimary, size: 22)
                        : Icon(Icons.circle_outlined, color: OmiColors.textTertiary, size: 22),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _OmiAvatar extends StatelessWidget {
  const _OmiAvatar();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 32,
      height: 32,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
      child: Image.asset(
        Assets.images.herologo.path,
        width: 18,
        height: 18,
        color: OmiColors.onAccent,
        colorBlendMode: BlendMode.srcIn,
        excludeFromSemantics: true,
      ),
    );
  }
}

class _AppAvatar extends StatelessWidget {
  const _AppAvatar({required this.app});

  final App app;

  @override
  Widget build(BuildContext context) {
    final fallback = CircleAvatar(
      backgroundColor: OmiColors.surface3,
      radius: 16,
      child: Text(
        app.name.decodeString.characters.firstOrNull?.toUpperCase() ?? '',
        style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600),
      ),
    );
    // An app without an image has nothing to fetch: draw its initial.
    if (app.image.trim().isEmpty) return fallback;
    return CachedNetworkImage(
      imageUrl: app.getImageUrl(),
      memCacheWidth: 96,
      imageBuilder: (context, imageProvider) =>
          CircleAvatar(backgroundColor: OmiColors.surface3, radius: 16, backgroundImage: imageProvider),
      errorWidget: (context, url, error) => fallback,
      placeholder: (context, url) => fallback,
    );
  }
}

/// A loading row: visible blocks on the sheet's surface, without a shimmer that freezes.
class _SkeletonRow extends StatelessWidget {
  const _SkeletonRow();

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: Padding(
        key: const Key('summary_template_skeleton'),
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
        child: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(color: OmiColors.surface3, shape: BoxShape.circle),
            ),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  FractionallySizedBox(
                    widthFactor: 0.55,
                    child: Container(
                      height: 14,
                      decoration: BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.smAll),
                    ),
                  ),
                  const SizedBox(height: 6),
                  FractionallySizedBox(
                    widthFactor: 0.35,
                    child: Container(
                      height: 10,
                      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TemplatesLoadError extends StatelessWidget {
  const _TemplatesLoadError({required this.onRetry});

  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Padding(
      key: const Key('summary_templates_error'),
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.xs, OmiSpacing.xxs),
      child: Row(
        children: [
          Icon(Icons.error_outline_rounded, size: 20, color: OmiColors.textTertiary),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(
            child: Text(
              context.l10n.summaryTemplatesLoadFailed,
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            ),
          ),
          OmiButton.tertiary(
            key: const Key('summary_templates_retry'),
            label: context.l10n.tryAgain,
            size: OmiButtonSize.compact,
            onPressed: onRetry,
          ),
        ],
      ),
    );
  }
}

class _InlineMessage extends StatelessWidget {
  const _InlineMessage({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.xs),
      child: Text(text, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
    );
  }
}

class _LinkRow extends StatelessWidget {
  const _LinkRow({super.key, required this.icon, required this.label, required this.onTap});

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 52),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
            child: Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
                  child: Icon(icon, size: 18, color: OmiColors.textPrimary),
                ),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(child: Text(label, style: OmiType.callout.copyWith(fontWeight: FontWeight.w500))),
                Icon(Icons.chevron_right_rounded, color: OmiColors.textTertiary, size: 22),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
