import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';

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

  const ConversationSummarySelection({
    required this.content,
    required this.kind,
    this.appId,
    this.resultIndex,
  });

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
      final result = conversation.appResults[index];
      final content = result.content.trim();
      if (content.isNotEmpty) {
        return ConversationSummarySelection(
          content: content,
          kind: ConversationSummaryKind.app,
          appId: result.appId,
          resultIndex: index,
        );
      }
    }

    final overview = conversation.structured.overview.trim();
    final projectedSections = renderSections(conversation.structured.sections);
    if (projectedSections.isNotEmpty && overview == projectedSections) {
      return ConversationSummarySelection(
        content: projectedSections,
        kind: ConversationSummaryKind.sections,
      );
    }
    if (overview.isNotEmpty) {
      return ConversationSummarySelection(
        content: overview,
        kind: ConversationSummaryKind.overview,
      );
    }
    if (projectedSections.isNotEmpty) {
      return ConversationSummarySelection(
        content: projectedSections,
        kind: ConversationSummaryKind.sections,
      );
    }
    return const ConversationSummarySelection(
      content: '',
      kind: ConversationSummaryKind.empty,
    );
  }

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
