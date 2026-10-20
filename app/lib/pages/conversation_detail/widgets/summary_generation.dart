import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';
import 'package:omi/pages/conversation_detail/widgets/summarized_apps_sheet.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/extensions/string.dart';

/// The name a summary source goes by: Omi for its own summary ([appId] null), otherwise the
/// template's name.
String summarySourceName(ConversationDetailProvider provider, String? appId, AppLocalizations l10n) {
  if (appId == null) return l10n.omiAppName;
  final selected = provider.selectedAppForReprocessing;
  final app = provider.findAppById(appId) ?? (selected?.id == appId ? selected : null);
  return app?.name.decodeString ?? l10n.unknownApp;
}

/// The saved "Make this my default" template, when it still resolves to an app.
String? resolvedDefaultSummaryTemplateId(ConversationDetailProvider provider) {
  final id = provider.defaultSummaryTemplateAppId;
  if (id == null || provider.findAppById(id) == null) return null;
  return id;
}

/// Starts a summary with [appId]'s template, remembering a template as last used. Null is Omi:
/// the request forces Omi's own notes, so a server preferred template never runs in its place.
Future<void> startSummary(ConversationDetailProvider provider, String? appId) async {
  if (provider.loadingReprocessConversation) return;
  if (appId != null) {
    final app = provider.findAppById(appId);
    if (app != null) provider.setSelectedAppForReprocessing(app);
    provider.trackLastUsedSummarizationApp(appId);
  }
  await provider.reprocessConversation(appId: appId, forceOmi: appId == null);
}

/// The Omi mark drawn on the primary pill, in the pill's label colour.
class _OmiMark extends StatelessWidget {
  const _OmiMark();

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: Image.asset(
        Assets.images.herologo.path,
        width: 18,
        height: 18,
        color: OmiColors.onAccent,
        colorBlendMode: BlendMode.srcIn,
      ),
    );
  }
}

/// A rounded card on [OmiColors.surface1] that the summary states share.
class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.children, super.key});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(OmiSpacing.lg),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: children),
    );
  }
}

/// "Not summarized yet": one primary action that summarizes straight away (with Omi, or the saved
/// default template) and one way to the template sheet, then the first line of the transcript.
class SummaryEmptyState extends StatelessWidget {
  const SummaryEmptyState({super.key, this.onOpenTranscript});

  /// Switches the page to the Transcript tab; the excerpt's link is hidden without it.
  final VoidCallback? onOpenTranscript;

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ConversationDetailProvider>();
    final l10n = context.l10n;
    final defaultAppId = resolvedDefaultSummaryTemplateId(provider);
    final busy = provider.loadingReprocessConversation;
    final segments = provider.conversationOrNull?.transcriptSegments ?? const <TranscriptSegment>[];
    final firstSegment = segments.where((segment) => segment.text.trim().isNotEmpty).firstOrNull;

    return Column(
      key: const Key('summary_empty_state'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _SummaryCard(
          children: [
            Text(l10n.summaryNotSummarizedYet, style: OmiType.title3),
            const SizedBox(height: OmiSpacing.xs),
            Text(l10n.summaryEmptyStateBody, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
            const SizedBox(height: OmiSpacing.lg),
            OmiButton(
              key: const Key('summary_empty_primary'),
              label: defaultAppId == null
                  ? l10n.summaryWithOmi
                  : l10n.summaryWithTemplate(summarySourceName(provider, defaultAppId, l10n)),
              leading: defaultAppId == null ? const _OmiMark() : null,
              expand: true,
              onPressed: busy ? null : () => startSummary(provider, defaultAppId),
            ),
            const SizedBox(height: OmiSpacing.xxs),
            OmiButton.tertiary(
              key: const Key('summary_empty_choose_template'),
              label: l10n.summaryUseDifferentTemplate,
              expand: true,
              onPressed: busy ? null : () => showSummarizedAppsSheet(context),
            ),
          ],
        ),
        if (firstSegment != null) ...[
          const SizedBox(height: OmiSpacing.xl),
          SummaryTranscriptExcerpt(segment: firstSegment, segments: segments, onOpenTranscript: onOpenTranscript),
        ],
      ],
    );
  }
}

/// "From the transcript": the conversation's first line, so the reader sees what Omi will
/// summarize, with a link to the whole transcript.
class SummaryTranscriptExcerpt extends StatelessWidget {
  const SummaryTranscriptExcerpt({super.key, required this.segment, required this.segments, this.onOpenTranscript});

  final TranscriptSegment segment;
  final List<TranscriptSegment> segments;
  final VoidCallback? onOpenTranscript;

  static String initials(String name) {
    final words = name.trim().split(RegExp(r'\s+')).where((word) => word.isNotEmpty).toList();
    if (words.isEmpty) return '?';
    final first = words.first.characters.first.toUpperCase();
    if (words.length == 1) return first;
    return '$first${words[1].characters.first.toUpperCase()}';
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = context.read<ConversationDetailProvider>();
    final people = context.read<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    final name = SpeakerNames.forSegments(
      segments,
      people: people,
      l10n: l10n,
      unresolved: provider.conversationOrNull?.speakerResolution?.status == 'unavailable',
    ).forSegment(segment);

    return Column(
      key: const Key('summary_transcript_excerpt'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          l10n.summaryFromTheTranscript.toUpperCase(),
          style:
              OmiType.caption.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600, letterSpacing: 0.6),
        ),
        const SizedBox(height: OmiSpacing.sm),
        Semantics(
          container: true,
          label: name,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ExcludeSemantics(
                child: Container(
                  width: 28,
                  height: 28,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
                  child: Text(
                    initials(name),
                    style: OmiType.caption.copyWith(fontWeight: FontWeight.w600, color: OmiColors.textSecondary),
                  ),
                ),
              ),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Text(
                  segment.text.trim(),
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
                ),
              ),
            ],
          ),
        ),
        if (onOpenTranscript != null)
          Padding(
            padding: const EdgeInsets.only(left: 28 + OmiSpacing.sm - OmiSpacing.md),
            child: OmiButton.tertiary(
              key: const Key('summary_read_full_transcript'),
              label: l10n.summaryReadFullTranscript,
              size: OmiButtonSize.compact,
              onPressed: onOpenTranscript,
            ),
          ),
      ],
    );
  }
}

/// The one progress surface while a summary is being written: "Summarizing with <source>…" over
/// a skeleton of the summary it will replace.
class SummaryGeneratingState extends StatelessWidget {
  const SummaryGeneratingState({super.key});

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ConversationDetailProvider>();
    final label =
        context.l10n.summarySummarizingWith(summarySourceName(provider, provider.reprocessingAppId, context.l10n));
    Widget bar(double widthFactor, {double height = 14}) => FractionallySizedBox(
          widthFactor: widthFactor,
          alignment: Alignment.centerLeft,
          child: Container(
            height: height,
            decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
          ),
        );

    return Semantics(
      key: const Key('summary_generating_state'),
      liveRegion: true,
      label: label,
      child: ExcludeSemantics(
        child: Padding(
          padding: const EdgeInsets.only(top: OmiSpacing.xs, bottom: OmiSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  const OmiSpinner(size: OmiSpinnerSize.small),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: Text(label, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                  ),
                ],
              ),
              const SizedBox(height: OmiSpacing.xl),
              bar(0.45, height: 20),
              const SizedBox(height: OmiSpacing.md),
              bar(1),
              const SizedBox(height: OmiSpacing.xs),
              bar(0.92),
              const SizedBox(height: OmiSpacing.xs),
              bar(0.7),
              const SizedBox(height: OmiSpacing.xl),
              bar(0.35, height: 18),
              const SizedBox(height: OmiSpacing.md),
              bar(0.85),
              const SizedBox(height: OmiSpacing.xs),
              bar(0.6),
            ],
          ),
        ),
      ),
    );
  }
}

/// Why the last summary request produced nothing, with what to do next.
class SummaryFailureCard extends StatelessWidget {
  const SummaryFailureCard({super.key, required this.failure});

  final SummaryFailure failure;

  @override
  Widget build(BuildContext context) {
    final provider = context.read<ConversationDetailProvider>();
    final l10n = context.l10n;
    final busy = context.select<ConversationDetailProvider, bool>((p) => p.loadingReprocessConversation);
    final (
      String title,
      String body,
      String primaryLabel,
      Future<void> Function() primary,
      String? secondaryLabel,
      Future<void> Function()? secondary
    ) = switch (failure.kind) {
      SummaryFailureKind.template => (
          l10n.summaryTemplateFailedTitle(summarySourceName(provider, failure.appId, l10n)),
          l10n.summaryTemplateFailedBody,
          l10n.tryAgain,
          () => startSummary(provider, failure.appId),
          l10n.summaryWithOmiInstead,
          () => startSummary(provider, null),
        ),
      SummaryFailureKind.busy => (
          l10n.summaryBusyTitle,
          l10n.summaryBusyBody,
          l10n.summaryCheckAgain,
          () async {
            // Keep the busy card (its retry action) unless a fresh read actually landed;
            // a failed or superseded refresh must not silently dismiss it.
            if (await provider.refreshConversation()) {
              provider.dismissSummaryFailure();
            }
          },
          null,
          null,
        ),
      SummaryFailureKind.rateLimited => (
          l10n.summaryLimitTitle,
          l10n.summaryLimitBody,
          l10n.ok,
          () async => provider.dismissSummaryFailure(),
          null,
          null,
        ),
      SummaryFailureKind.generic => (
          l10n.summaryFailedTitle,
          l10n.summaryFailedBody,
          l10n.tryAgain,
          () => startSummary(provider, failure.appId),
          l10n.summaryUseDifferentTemplate,
          () => showSummarizedAppsSheet(context),
        ),
    };
    // Retrying is pointless while another reprocess runs; acknowledging never is.
    final blocked = busy && failure.kind != SummaryFailureKind.rateLimited;

    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.lg),
      child: Semantics(
        liveRegion: true,
        container: true,
        child: _SummaryCard(
          key: Key('summary_failure_${failure.kind.name}'),
          children: [
            Text(title, style: OmiType.headline),
            const SizedBox(height: OmiSpacing.xs),
            Text(body, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
            const SizedBox(height: OmiSpacing.lg),
            OmiButton(
              key: const Key('summary_failure_primary'),
              label: primaryLabel,
              expand: true,
              onPressed: blocked ? null : primary,
            ),
            if (secondaryLabel != null && secondary != null) ...[
              const SizedBox(height: OmiSpacing.xxs),
              OmiButton.tertiary(
                key: const Key('summary_failure_secondary'),
                label: secondaryLabel,
                expand: true,
                onPressed: blocked ? null : secondary,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// The summaries this conversation holds, on top of the one shown: Omi's own and each template's,
/// the shown one filled; tapping another shows it, and "+" opens the template sheet.
class SummarySourceChips extends StatelessWidget {
  const SummarySourceChips({super.key, required this.selection});

  /// The summary on screen.
  final ConversationSummarySelection selection;

  @override
  Widget build(BuildContext context) {
    final provider = context.read<ConversationDetailProvider>();
    final l10n = context.l10n;
    final sources = provider.conversationOrNull == null
        ? <ConversationSummarySelection>[selection]
        : ConversationSummarySelection.available(provider.conversation);
    if (!sources.any((source) => source.sourceKey == selection.sourceKey)) sources.insert(0, selection);
    String name(ConversationSummarySelection source) =>
        source.isApp ? (provider.findAppById(source.appId)?.name.decodeString ?? l10n.unknownApp) : l10n.omiAppName;
    return Padding(
      key: const Key('summary_source_chips'),
      padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            for (final source in sources) ...[
              OmiFilterChip(
                key: Key('summary_source_${source.sourceKey}'),
                label: name(source),
                selected: source.sourceKey == selection.sourceKey,
                onSelected: () => provider.showSummarySource(source),
              ),
              const SizedBox(width: OmiSpacing.xs),
            ],
            OmiFilterChip(
              key: const Key('summary_source_add'),
              label: '',
              icon: Icons.add,
              semanticsLabel: l10n.summaryUseDifferentTemplate,
              selected: false,
              onSelected: () => showSummarizedAppsSheet(context),
            ),
          ],
        ),
      ),
    );
  }
}
