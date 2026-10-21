import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/utils/note_citations.dart';

/// The one summary body a conversation detail surface should render or export.
///
/// [appId] is optional metadata. [resultIndex] is the identity for an app
/// result, including legacy results whose app id is null; a null app id alone
/// must never be used to decide that a result is first-party content.
enum ConversationSummaryKind { app, overview, sections, empty }

class ConversationSummarySelection {
  final String content;
  final ConversationSummaryKind kind;
  final String? appId;
  final int? resultIndex;

  /// Renderable first-party sections; app outputs and edited overviews keep their flat path.
  final List<Section> sections;

  const ConversationSummarySelection(
      {required this.content, required this.kind, this.appId, this.resultIndex, this.sections = const []});

  bool get isApp => kind == ConversationSummaryKind.app;

  /// Whether this selection can still be edited safely against [conversation].
  ///
  /// App results are addressed by app id by the current mutation API, so the
  /// selected id must be unique and the indexed result must still be the same
  /// result captured at edit start. Non-app selections must still be the
  /// conversation's current primary selection as well, preventing a stale
  /// overview edit from overwriting a newly selected app result.
  bool canEdit(ServerConversation conversation) {
    if (isApp) {
      final index = resultIndex;
      final selectedAppId = appId;
      if (index == null || index < 0 || index >= conversation.appResults.length || selectedAppId == null) {
        return false;
      }

      final result = conversation.appResults[index];
      if (result.appId != selectedAppId || result.content.trim() != content) return false;
      return conversation.appResults.where((candidate) => candidate.appId == selectedAppId).length == 1;
    }

    final current = select(conversation);
    return current.kind == kind &&
        current.content == content &&
        current.appId == appId &&
        current.resultIndex == resultIndex;
  }

  /// Select the first usable app output, then the compatibility overview, then
  /// the deterministic section projection. A generated overview that is
  /// exactly that projection is represented by sections to avoid mounting the
  /// same Markdown twice.
  static ConversationSummarySelection select(ServerConversation conversation) {
    for (var index = 0; index < conversation.appResults.length; index++) {
      final selection = _appResult(conversation, index);
      if (selection != null) return selection;
    }
    return firstParty(conversation);
  }

  /// Every summary [conversation] holds: Omi's own first (when it has one), then each non-empty
  /// app result in server order — except results that share a source identity: duplicate app ids
  /// are valid read-only data, but sibling chips with the same `sourceKey` would both look
  /// selected and the second could never be resolved by key, so only the first is offered (the
  /// freshest result once the reprocess contract lands it first). Legacy results without an app
  /// id keep their per-result keys and stay individually viewable.
  static List<ConversationSummarySelection> available(ServerConversation conversation) {
    final omi = firstParty(conversation);
    final seenKeys = <String>{};
    return [
      if (omi.kind != ConversationSummaryKind.empty) omi,
      for (var index = 0; index < conversation.appResults.length; index++)
        if (_appResult(conversation, index) case final selection?)
          if (seenKeys.add(selection.sourceKey)) selection,
    ];
  }

  /// Omi's own summary: the compatibility overview or the section projection, else empty.
  static ConversationSummarySelection firstParty(ServerConversation conversation) {
    final knownIDs = conversation.transcriptSegments.map((segment) => segment.id).where((id) => id.isNotEmpty);
    String presentable(String text) => repairNoteCitations(text, knownIDs).text;
    final overview = conversation.structured.overview.trim();
    final projectedSections = renderSections(conversation.structured.sections);
    final validIDs = knownIDs.toSet();
    final sections =
        conversation.structured.sections.where((section) => section.bodyMarkdown.trim().isNotEmpty).map((section) {
      final heading = repairNoteCitations(section.heading, knownIDs);
      final body = repairNoteCitations(section.bodyMarkdown, knownIDs);
      // Inline citations the repair removes join the typed provenance (macOS presentableSection),
      // so a legacy note whose only evidence was `[s01234]` keeps its transcript pointer.
      return Section(
        heading: heading.text,
        bodyMarkdown: body.text,
        kind: section.kind,
        sourceSegmentIds: [...?section.sourceSegmentIds, ...heading.sourceIDs, ...body.sourceIDs]
            .where(validIDs.contains)
            .toSet()
            .toList(),
      );
    }).toList(growable: false);
    if (projectedSections.isNotEmpty && overview == projectedSections) {
      return ConversationSummarySelection(
          content: presentable(projectedSections), kind: ConversationSummaryKind.sections, sections: sections);
    }
    if (overview.isNotEmpty) {
      return ConversationSummarySelection(content: presentable(overview), kind: ConversationSummaryKind.overview);
    }
    if (projectedSections.isNotEmpty) {
      return ConversationSummarySelection(
          content: presentable(projectedSections), kind: ConversationSummaryKind.sections, sections: sections);
    }
    return const ConversationSummarySelection(content: '', kind: ConversationSummaryKind.empty);
  }

  static ConversationSummarySelection? _appResult(ServerConversation conversation, int index) {
    final result = conversation.appResults[index];
    final content = result.content.trim();
    if (content.isEmpty) return null;
    return ConversationSummarySelection(
      content: content,
      kind: ConversationSummaryKind.app,
      appId: result.appId,
      resultIndex: index,
    );
  }

  /// Identifies a source across refreshes: "omi", or the app id (the result index for legacy
  /// output without one).
  String get sourceKey => isApp ? 'app:${appId ?? '#$resultIndex'}' : 'omi';

  /// The canonical Markdown projection of structured sections.
  ///
  /// Heading-only sections are intentionally ignored: a heading without a
  /// body is not useful summary content and must not make an otherwise empty
  /// summary look populated.
  static String renderSections(List<Section> sections) {
    final blocks = <String>[];
    for (final section in sections) {
      final heading = section.heading.trim();
      final body = section.bodyMarkdown.trim();
      if (body.isEmpty) continue;
      blocks.add(heading.isEmpty ? body : '## $heading\n\n$body');
    }
    return blocks.join('\n\n');
  }
}
