/// Wire models for the Review queue, its recent-changes journal, and entity pages
/// (`backend/docs` contract "Review + entity pages API v1").
///
/// Parsing is strict about identity fields and lenient about optional display fields: an item
/// without an id or a kind is dropped by the list parser rather than shown half-built.
library;

import 'package:omi/backend/schema/gen/review_wire.g.dart' as wire;
import 'package:omi/backend/schema/gen/entity_pages_wire.g.dart' as entity_wire;

String? _str(Object? v) => v is String && v.isNotEmpty ? v : null;
int _int(Object? v) => v is num ? v.toInt() : 0;
double _double(Object? v) => v is num ? v.toDouble() : 0;
DateTime? _date(Object? v) => v is String ? DateTime.tryParse(v)?.toLocal() : null;
List<Map<String, dynamic>> _maps(Object? v) =>
    v is List ? v.whereType<Map<String, dynamic>>().toList(growable: false) : const [];
List<String> _strings(Object? v) => v is List ? v.whereType<String>().toList(growable: false) : const [];
Map<String, dynamic>? _map(Object? v) => v is Map<String, dynamic> ? v : null;

enum ReviewItemKind { speaker, task, samePerson, spelling, agentProposal }

ReviewItemKind? _kind(Object? v) => switch (v) {
      'speaker' => ReviewItemKind.speaker,
      'task' => ReviewItemKind.task,
      'same_person' => ReviewItemKind.samePerson,
      'spelling' => ReviewItemKind.spelling,
      'agent_proposal' => ReviewItemKind.agentProposal,
      _ => null,
    };

enum EntityType { person, organization, project }

EntityType? entityTypeFromWire(Object? v) => switch (v) {
      'person' => EntityType.person,
      'organization' => EntityType.organization,
      'project' => EntityType.project,
      _ => null,
    };

class EntityRef {
  const EntityRef({required this.entityId, required this.type, required this.name});
  final String entityId;
  final EntityType type;
  final String name;

  static EntityRef? fromJson(Map<String, dynamic> json) {
    final id = _str(json['entity_id']);
    final type = entityTypeFromWire(json['type']);
    final name = _str(json['name']);
    if (id == null || type == null || name == null) return null;
    return EntityRef(entityId: id, type: type, name: name);
  }

  static List<EntityRef> listFrom(Object? v) =>
      _maps(v).map(EntityRef.fromJson).whereType<EntityRef>().toList(growable: false);
}

class PersonRef {
  const PersonRef({required this.personId, required this.name, this.organization});
  final String personId;
  final String name;
  final String? organization;

  static PersonRef? fromJson(Map<String, dynamic> json) {
    final id = _str(json['person_id']);
    final name = _str(json['name']);
    if (id == null || name == null) return null;
    return PersonRef(personId: id, name: name, organization: _str(json['organization']));
  }
}

class EntitySummary {
  const EntitySummary({
    required this.entityId,
    required this.type,
    required this.name,
    this.subtitle,
    this.conversationCount = 0,
    this.signals = const [],
  });
  final String entityId;
  final EntityType type;
  final String name;
  final String? subtitle;
  final int conversationCount;
  final List<String> signals;

  static EntitySummary? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final ref = EntityRef.fromJson(json);
    if (ref == null) return null;
    return EntitySummary(
      entityId: ref.entityId,
      type: ref.type,
      name: ref.name,
      subtitle: _str(json['subtitle']),
      conversationCount: _int(json['conversation_count']),
      signals: _strings(json['signals']),
    );
  }
}

class Evidence {
  const Evidence({required this.quote, this.speakerLabel, this.at, this.conversationId, this.conversationTitle});
  final String quote;
  final String? speakerLabel;
  final DateTime? at;
  final String? conversationId;
  final String? conversationTitle;

  static Evidence? fromJson(Map<String, dynamic>? json) {
    final quote = _str(json?['quote']);
    if (json == null || quote == null) return null;
    return Evidence(
      quote: quote,
      speakerLabel: _str(json['speaker_label']),
      at: _date(json['at']),
      conversationId: _str(json['conversation_id']),
      conversationTitle: _str(json['conversation_title']),
    );
  }
}

class TranscriptLine {
  const TranscriptLine({required this.speakerLabel, required this.text, this.at, this.isTarget = false});
  final String speakerLabel;
  final String text;
  final DateTime? at;
  final bool isTarget;

  static TranscriptLine? fromJson(Map<String, dynamic> json) {
    final text = _str(json['text']);
    if (text == null) return null;
    return TranscriptLine(
      speakerLabel: _str(json['speaker_label']) ?? '',
      text: text,
      at: _date(json['at']),
      isTarget: json['is_target'] == true,
    );
  }
}

class SpeakerItem {
  const SpeakerItem({
    required this.promptId,
    required this.conversationId,
    required this.conversationTitle,
    required this.start,
    required this.end,
    this.candidates = const [],
    this.affectedConversationCount = 0,
    this.context = const [],
  });
  final String promptId;
  final String conversationId;
  final String conversationTitle;
  final double start;
  final double end;
  final List<PersonRef> candidates;
  final int affectedConversationCount;
  final List<TranscriptLine> context;

  static SpeakerItem? fromJson(Map<String, dynamic>? json) {
    final promptId = _str(json?['prompt_id']);
    final conversationId = _str(json?['conversation_id']);
    if (json == null || promptId == null || conversationId == null) return null;
    return SpeakerItem(
      promptId: promptId,
      conversationId: conversationId,
      conversationTitle: _str(json['conversation_title']) ?? '',
      start: _double(json['start']),
      end: _double(json['end']),
      candidates: _maps(json['candidates']).map(PersonRef.fromJson).whereType<PersonRef>().toList(growable: false),
      affectedConversationCount: _int(json['affected_conversation_count']),
      context: _maps(json['context']).map(TranscriptLine.fromJson).whereType<TranscriptLine>().toList(growable: false),
    );
  }
}

class TaskItem {
  const TaskItem({
    required this.candidateId,
    required this.description,
    this.dueAt,
    this.workstreamId,
    this.workstreamTitle,
    this.evidence,
  });
  final String candidateId;
  final String description;
  final DateTime? dueAt;
  final String? workstreamId;
  final String? workstreamTitle;
  final Evidence? evidence;

  static TaskItem? fromJson(Map<String, dynamic>? json) {
    final id = _str(json?['candidate_id']);
    final description = _str(json?['description']);
    if (json == null || id == null || description == null) return null;
    return TaskItem(
      candidateId: id,
      description: description,
      dueAt: _date(json['due_at']),
      workstreamId: _str(json['workstream_id']),
      workstreamTitle: _str(json['workstream_title']),
      evidence: Evidence.fromJson(_map(json['evidence'])),
    );
  }
}

class SamePersonItem {
  const SamePersonItem({required this.left, required this.right, this.reason});
  final EntitySummary left;
  final EntitySummary right;
  final String? reason;

  static SamePersonItem? fromJson(Map<String, dynamic>? json) {
    final left = EntitySummary.fromJson(_map(json?['left']));
    final right = EntitySummary.fromJson(_map(json?['right']));
    if (left == null || right == null) return null;
    return SamePersonItem(left: left, right: right, reason: _str(json?['reason']));
  }
}

class SpellingContextSegment {
  const SpellingContextSegment({required this.text, this.speakerLabel, this.isUser = false});
  final String text;
  final String? speakerLabel;
  final bool isUser;

  static SpellingContextSegment fromJson(Map<String, dynamic> json) => SpellingContextSegment(
        text: _str(json['text']) ?? '',
        speakerLabel: _str(json['speaker_label']),
        isUser: json['is_user'] == true,
      );
}

class SpellingContext {
  const SpellingContext({
    required this.conversationTitle,
    required this.segments,
    required this.mainIndex,
    this.conversationDate,
    this.quoteStart,
    this.quoteEnd,
  });
  final String conversationTitle;
  final DateTime? conversationDate;
  final List<SpellingContextSegment> segments;
  final int mainIndex;

  /// UTF-16 code-unit offsets in the main segment, matching Dart String indexes.
  final int? quoteStart;
  final int? quoteEnd;

  SpellingContextSegment get main => segments[mainIndex];

  static SpellingContext? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final segments = _maps(json['segments']).map(SpellingContextSegment.fromJson).toList(growable: false);
    final mainIndex = json['main_index'];
    if (mainIndex is! int || mainIndex < 0 || mainIndex >= segments.length || segments.length > 3) return null;
    return SpellingContext(
      conversationTitle: _str(json['conversation_title']) ?? '',
      conversationDate: _date(json['conversation_date']),
      segments: segments,
      mainIndex: mainIndex,
      quoteStart: json['quote_start'] is int ? json['quote_start'] as int : null,
      quoteEnd: json['quote_end'] is int ? json['quote_end'] as int : null,
    );
  }
}

class SpellingItem {
  const SpellingItem({required this.termId, required this.options, this.allowCustom = true, this.context});
  final String termId;
  final List<String> options;
  final bool allowCustom;
  final SpellingContext? context;

  static SpellingItem? fromJson(Map<String, dynamic>? json) {
    final id = _str(json?['term_id']);
    final options = _strings(json?['options']);
    if (id == null || options.isEmpty) return null;
    return SpellingItem(
      termId: id,
      options: options,
      allowCustom: json?['allow_custom'] != false,
      context: SpellingContext.fromJson(_map(json?['context'])),
    );
  }
}

/// A change Dream proposes but does not apply on its own (closing a task, merging people or
/// memories, editing a memory or an entity summary). Accepting applies it through the undoable
/// journal; dismissing stops it from being proposed again.
class AgentProposalItem {
  const AgentProposalItem({
    required this.editKind,
    required this.targetLabel,
    this.otherLabel,
    this.before = '',
    this.after = '',
    this.reason,
  });

  /// The backend edit kind (`close_task`, `merge_people`, ...), or `vocabulary` for a new term.
  final String editKind;
  final String targetLabel;
  final String? otherLabel;
  final String before;
  final String after;
  final String? reason;

  static AgentProposalItem? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final operation = _map(json['operation']);
    final edit = operation?.isNotEmpty == true ? operation : _map(json['edit']);
    final vocabulary = _map(json['vocabulary']);
    final targetLabel = _str(json['target_label']) ?? '';
    if (edit != null) {
      final kind = _str(edit['kind']);
      if (kind == null) return null;
      return AgentProposalItem(
        editKind: kind,
        targetLabel: targetLabel,
        otherLabel: _str(json['other_label']),
        before: (_str(edit['before']) ?? '').isEmpty
            ? _str(json['target_content']) ?? targetLabel
            : _str(edit['before']) ?? '',
        after: (_str(edit['after']) ?? '').isEmpty &&
                {'supersede_memory', 'merge_people', 'merge_tasks', 'merge_conversations'}.contains(kind)
            ? _str(json['other_content']) ?? _str(json['other_label']) ?? ''
            : _str(edit['after']) ?? '',
        reason: _str(edit['reason']),
      );
    }
    final term = _str(vocabulary?['spelling']);
    if (term == null) return null;
    return AgentProposalItem(editKind: 'vocabulary', targetLabel: targetLabel, after: term);
  }
}

class ReviewItem {
  const ReviewItem({
    required this.itemId,
    required this.kind,
    this.title,
    this.quote,
    this.speaker,
    this.task,
    this.samePerson,
    this.spelling,
    this.agentProposal,
  });
  final String itemId;
  final ReviewItemKind kind;

  /// Server copy, used only as a fallback; the client words the question per [kind].
  final String? title;
  final String? quote;
  final SpeakerItem? speaker;
  final TaskItem? task;
  final SamePersonItem? samePerson;
  final SpellingItem? spelling;
  final AgentProposalItem? agentProposal;

  /// An item whose kind-specific payload is missing cannot be answered, so it is not shown.
  static ReviewItem? fromJson(Map<String, dynamic> json) {
    final id = _str(json['item_id']);
    final kind = _kind(json['kind']);
    if (id == null || kind == null) return null;
    final item = ReviewItem(
      itemId: id,
      kind: kind,
      title: _str(json['title']),
      quote: _str(json['quote']),
      speaker: SpeakerItem.fromJson(_map(json['speaker'])),
      task: TaskItem.fromJson(_map(json['task'])),
      samePerson: SamePersonItem.fromJson(_map(json['same_person'])),
      spelling: SpellingItem.fromJson(_map(json['spelling'])),
      agentProposal: AgentProposalItem.fromJson(_map(json['agent_proposal'])),
    );
    final complete = switch (kind) {
      ReviewItemKind.speaker => item.speaker != null,
      ReviewItemKind.task => item.task != null,
      ReviewItemKind.samePerson => item.samePerson != null,
      ReviewItemKind.spelling => item.spelling != null,
      ReviewItemKind.agentProposal => item.agentProposal != null,
    };
    return complete ? item : null;
  }
}

class ReviewItemsResponse {
  factory ReviewItemsResponse.fromGenerated(wire.GeneratedReviewItemsResponse generated) {
    return fromJson(generated.toJson());
  }

  /// The v2 queue, which also carries Dream's suggestions.
  factory ReviewItemsResponse.fromGeneratedV2(wire.GeneratedReviewItemsResponseV2 generated) {
    return fromJson(generated.toJson());
  }

  const ReviewItemsResponse({required this.items, required this.remainingToday});
  final List<ReviewItem> items;
  final int remainingToday;

  static ReviewItemsResponse fromJson(Map<String, dynamic> json) => ReviewItemsResponse(
        items: _maps(json['items']).map(ReviewItem.fromJson).whereType<ReviewItem>().toList(growable: false),
        remainingToday: _int(json['remaining_today']),
      );
}

enum TaskDismissReason { alreadyDone, notMine, notUseful }

/// One answer; exactly one kind-specific part is set, or [notSure].
class ReviewAnswer {
  const ReviewAnswer._({
    this.speakerPersonId,
    this.speakerNewName,
    this.speakerIsMe = false,
    this.taskAccept,
    this.taskDismissReason,
    this.taskDescription,
    this.taskDueAt,
    this.taskWorkstreamId,
    this.samePerson,
    this.spelling,
    this.proposalAccept,
    this.notSure = false,
  });

  const ReviewAnswer.speaker({String? personId, String? newName, bool isMe = false})
      : this._(speakerPersonId: personId, speakerNewName: newName, speakerIsMe: isMe);
  const ReviewAnswer.acceptTask({String? description, DateTime? dueAt, String? workstreamId})
      : this._(taskAccept: true, taskDescription: description, taskDueAt: dueAt, taskWorkstreamId: workstreamId);
  const ReviewAnswer.dismissTask([TaskDismissReason? reason]) : this._(taskAccept: false, taskDismissReason: reason);
  const ReviewAnswer.samePerson(bool same) : this._(samePerson: same);
  const ReviewAnswer.spelling(String value) : this._(spelling: value);
  const ReviewAnswer.acceptProposal() : this._(proposalAccept: true);
  const ReviewAnswer.dismissProposal() : this._(proposalAccept: false);
  const ReviewAnswer.notSure() : this._(notSure: true);

  final String? speakerPersonId;
  final String? speakerNewName;
  final bool speakerIsMe;
  final bool? taskAccept;
  final TaskDismissReason? taskDismissReason;
  final String? taskDescription;
  final DateTime? taskDueAt;
  final String? taskWorkstreamId;
  final bool? samePerson;
  final String? spelling;
  final bool? proposalAccept;
  final bool notSure;

  Map<String, dynamic> toJson(ReviewItemKind kind) {
    if (notSure) return {'not_sure': true};
    return switch (kind) {
      ReviewItemKind.speaker => {
          'speaker': {'person_id': speakerPersonId, 'new_person_name': speakerNewName, 'is_me': speakerIsMe},
          'not_sure': false,
        },
      ReviewItemKind.task => {
          'task': {
            'decision': taskAccept == true ? 'accept' : 'dismiss',
            'dismiss_reason': switch (taskDismissReason) {
              TaskDismissReason.alreadyDone => 'already_done',
              TaskDismissReason.notMine => 'not_mine',
              TaskDismissReason.notUseful => 'not_useful',
              null => null,
            },
            'edited_description': taskDescription,
            'due_at': taskDueAt?.toUtc().toIso8601String(),
            'workstream_id': taskWorkstreamId,
          },
          'not_sure': false,
        },
      ReviewItemKind.samePerson => {
          'same_person': {'decision': samePerson == true ? 'yes' : 'no'},
          'not_sure': false,
        },
      ReviewItemKind.spelling => {
          'spelling': {'value': spelling},
          'not_sure': false,
        },
      ReviewItemKind.agentProposal => {
          'agent_proposal': {'decision': proposalAccept == true ? 'accept' : 'dismiss'},
          'not_sure': false,
        },
    };
  }
}

enum ReviewChangeKind { rename, mergeMemories, updatePerson, labelSpeaker, titleConversation, closeTask, other }

ReviewChangeKind _changeKind(Object? v) => switch (v) {
      'rename' => ReviewChangeKind.rename,
      'merge_memories' => ReviewChangeKind.mergeMemories,
      'update_person' => ReviewChangeKind.updatePerson,
      'label_speaker' => ReviewChangeKind.labelSpeaker,
      'title_conversation' => ReviewChangeKind.titleConversation,
      'close_task' => ReviewChangeKind.closeTask,
      _ => ReviewChangeKind.other,
    };

class ReviewChangeRef {
  const ReviewChangeRef({required this.type, required this.id, required this.label});
  final String type;
  final String id;
  final String label;
}

/// One place a change landed: the edited span with the speech around it.
class ReviewChangeOccurrence {
  const ReviewChangeOccurrence({this.contextBefore = '', this.before = '', this.after = '', this.contextAfter = ''});
  final String contextBefore;
  final String before;
  final String after;
  final String contextAfter;

  bool get isEmpty => contextBefore.isEmpty && before.isEmpty && after.isEmpty && contextAfter.isEmpty;

  static ReviewChangeOccurrence? fromJson(Map<String, dynamic> json, {String before = '', String after = ''}) {
    final value = ReviewChangeOccurrence(
      contextBefore: _text(json['context_before']),
      before: _str(json['before']) ?? before,
      after: json['after'] is String ? json['after'] as String : after,
      contextAfter: _text(json['context_after']),
    );
    return value.isEmpty ? null : value;
  }
}

String _text(Object? v) => v is String ? v : '';

Map<String, dynamic> _withAdditive(Map<String, dynamic> generated, Object? raw) => {
      ...generated,
      if (raw is Map<String, dynamic>) ...{
        for (final key in const ['diff', 'group_key'])
          if (raw.containsKey(key)) key: raw[key],
      },
    };

/// The server-extracted change itself: what the text was, what it is now, and where. Every field
/// is optional; journal rows written before the diff existed simply omit it.
class ReviewChangeDiff {
  const ReviewChangeDiff({
    this.targetLabel,
    this.field,
    this.before,
    this.after,
    this.occurrences = const [],
    this.occurrenceCount = 0,
    this.sourceTitle,
    this.sourceStartedAt,
  });
  final String? targetLabel;
  final String? field;
  final String? before;

  /// Empty means the item was removed; null means the server did not say.
  final String? after;

  /// Each place in context. Holds one entry built from the top-level context when the server
  /// sends only a count.
  final List<ReviewChangeOccurrence> occurrences;

  /// How many places the change touched in this source, at least one.
  final int occurrenceCount;
  final String? sourceTitle;
  final DateTime? sourceStartedAt;

  static ReviewChangeDiff? fromJson(Map<String, dynamic>? json) {
    if (json == null) return null;
    final before = _str(json['before']);
    final after = json['after'] is String ? json['after'] as String : null;
    final raw = json['occurrences'];
    final listed = raw is List
        ? _maps(raw)
            .map((o) => ReviewChangeOccurrence.fromJson(o, before: before ?? '', after: after ?? ''))
            .whereType<ReviewChangeOccurrence>()
            .toList(growable: false)
        : const <ReviewChangeOccurrence>[];
    final top = ReviewChangeOccurrence.fromJson(json, before: before ?? '', after: after ?? '');
    final occurrences = listed.isNotEmpty ? listed : [if (top != null) top];
    final count = raw is num && raw > 0 ? raw.toInt() : (listed.isNotEmpty ? listed.length : 1);
    final diff = ReviewChangeDiff(
      targetLabel: _str(json['target_label']),
      field: _str(json['field']),
      before: before,
      after: after,
      occurrences: occurrences,
      occurrenceCount: count,
      sourceTitle: _str(json['source_title']),
      sourceStartedAt: _date(json['source_started_at']),
    );
    return before == null && after == null && occurrences.isEmpty ? null : diff;
  }
}

class ReviewChange {
  /// [raw] is the same change as JSON. It carries additive fields (`diff`, `group_key`) through
  /// before the generated wire knows them.
  factory ReviewChange.fromGenerated(wire.GeneratedReviewChange generated, {Map<String, dynamic>? raw}) {
    final value = fromJson(_withAdditive(generated.toJson(), raw));
    if (value == null) throw const FormatException('Malformed ReviewChange');
    return value;
  }

  const ReviewChange({
    required this.changeId,
    required this.kind,
    required this.title,
    required this.createdAt,
    this.reason,
    this.snippet,
    this.editKind,
    this.before,
    this.after,
    this.context,
    this.refs = const [],
    this.undone = false,
    this.diff,
    this.groupKey,
  });
  final String changeId;
  final ReviewChangeKind kind;
  final String title;
  final String? reason;
  final String? snippet;
  final String? editKind;
  final String? before;
  final String? after;
  final SpellingContext? context;
  final List<ReviewChangeRef> refs;
  final DateTime createdAt;
  final bool undone;
  final ReviewChangeDiff? diff;

  /// Stable across conversations for the same change, such as one term respelled everywhere. The
  /// server sends it as `diff.group_key`; a top-level `group_key` is also accepted.
  final String? groupKey;

  ReviewChange copyWith({bool? undone}) => ReviewChange(
        changeId: changeId,
        kind: kind,
        title: title,
        reason: reason,
        snippet: snippet,
        editKind: editKind,
        before: before,
        after: after,
        context: context,
        refs: refs,
        createdAt: createdAt,
        undone: undone ?? this.undone,
        diff: diff,
        groupKey: groupKey,
      );

  static ReviewChange? fromJson(Map<String, dynamic> json) {
    final id = _str(json['change_id']);
    final title = _str(json['title']);
    final createdAt = _date(json['created_at']);
    if (id == null || title == null || createdAt == null) return null;
    return ReviewChange(
      changeId: id,
      kind: _changeKind(json['kind']),
      title: title,
      reason: _str(json['reason']),
      snippet: _str(json['snippet']),
      editKind: _str(json['edit_kind']),
      before: _str(json['before']),
      after: json['after'] is String ? json['after'] as String : null,
      context: SpellingContext.fromJson(_map(json['context'])),
      refs: _maps(json['refs'])
          .map((r) {
            final type = _str(r['type']);
            final rid = _str(r['id']);
            final label = _str(r['label']);
            return type == null || rid == null || label == null
                ? null
                : ReviewChangeRef(type: type, id: rid, label: label);
          })
          .whereType<ReviewChangeRef>()
          .toList(growable: false),
      createdAt: createdAt,
      undone: json['undone'] == true,
      diff: ReviewChangeDiff.fromJson(_map(json['diff'])),
      groupKey: _str(json['group_key']) ?? _str(_map(json['diff'])?['group_key']),
    );
  }
}

class ReviewChangesPage {
  factory ReviewChangesPage.fromGenerated(wire.GeneratedReviewChangesResponse generated, {Map<String, dynamic>? raw}) {
    final json = generated.toJson();
    final rawChanges = raw?['changes'];
    final changes = json['changes'];
    if (rawChanges is List && changes is List && rawChanges.length == changes.length) {
      json['changes'] = [
        for (var i = 0; i < changes.length; i++) _withAdditive(changes[i] as Map<String, dynamic>, rawChanges[i]),
      ];
    }
    return fromJson(json);
  }

  const ReviewChangesPage({required this.changes, this.nextCursor});
  final List<ReviewChange> changes;
  final String? nextCursor;

  static ReviewChangesPage fromJson(Map<String, dynamic> json) => ReviewChangesPage(
        changes: _maps(json['changes']).map(ReviewChange.fromJson).whereType<ReviewChange>().toList(growable: false),
        nextCursor: _str(json['next_cursor']),
      );
}

enum FactSourceKind { conversation, chat, screen, user }

class Fact {
  const Fact({
    required this.factId,
    required this.text,
    required this.sourceKind,
    required this.sourceLabel,
    this.conversationId,
    this.at,
  });
  final String factId;
  final String text;
  final FactSourceKind sourceKind;
  final String sourceLabel;
  final String? conversationId;
  final DateTime? at;

  static Fact? fromJson(Map<String, dynamic> json) {
    final id = _str(json['fact_id']);
    final text = _str(json['text']);
    if (id == null || text == null) return null;
    final source = _map(json['source']) ?? const {};
    return Fact(
      factId: id,
      text: text,
      sourceKind: switch (source['kind']) {
        'chat' => FactSourceKind.chat,
        'screen' => FactSourceKind.screen,
        'user' => FactSourceKind.user,
        _ => FactSourceKind.conversation,
      },
      sourceLabel: _str(source['label']) ?? '',
      conversationId: _str(source['conversation_id']),
      at: _date(source['at']),
    );
  }

  static List<Fact> listFrom(Object? v) => _maps(v).map(Fact.fromJson).whereType<Fact>().toList(growable: false);
}

class TaskRef {
  const TaskRef({required this.taskId, required this.description, this.ownerLabel, this.dueAt, this.waitingOn});
  final String taskId;
  final String description;
  final String? ownerLabel;
  final DateTime? dueAt;
  final String? waitingOn;

  static TaskRef? fromJson(Map<String, dynamic> json) {
    final id = _str(json['task_id']);
    final description = _str(json['description']);
    if (id == null || description == null) return null;
    return TaskRef(
      taskId: id,
      description: description,
      ownerLabel: _str(json['owner_label']),
      dueAt: _date(json['due_at']),
      waitingOn: _str(json['waiting_on']),
    );
  }
}

class ConversationRef {
  const ConversationRef({required this.conversationId, required this.title, this.startedAt, this.durationSeconds = 0});
  final String conversationId;
  final String title;
  final DateTime? startedAt;
  final int durationSeconds;

  static ConversationRef? fromJson(Map<String, dynamic> json) {
    final id = _str(json['conversation_id']);
    if (id == null) return null;
    return ConversationRef(
      conversationId: id,
      title: _str(json['title']) ?? '',
      startedAt: _date(json['started_at']),
      durationSeconds: _int(json['duration_seconds']),
    );
  }
}

class EntityPageData {
  factory EntityPageData.fromGenerated(entity_wire.GeneratedEntityPage generated) {
    final value = fromJson(generated.toJson());
    if (value == null) throw const FormatException('Malformed EntityPageData');
    return value;
  }

  const EntityPageData({
    required this.entityId,
    required this.type,
    required this.name,
    this.subtitle,
    this.organization,
    this.summary,
    this.summaryUpdatedAt,
    this.people = const [],
    this.projects = const [],
    this.facts = const [],
    this.openTasks = const [],
    this.decisions = const [],
    this.recentConversations = const [],
    this.pendingQuestion,
  });
  final String entityId;
  final EntityType type;
  final String name;
  final String? subtitle;
  final EntityRef? organization;
  final String? summary;
  final DateTime? summaryUpdatedAt;
  final List<EntityRef> people;
  final List<EntityRef> projects;
  final List<Fact> facts;
  final List<TaskRef> openTasks;
  final List<Fact> decisions;
  final List<ConversationRef> recentConversations;
  final ReviewItem? pendingQuestion;

  static EntityPageData? fromJson(Map<String, dynamic> json) {
    final ref = EntityRef.fromJson(json);
    if (ref == null) return null;
    final question = _map(json['pending_question']);
    final org = _map(json['organization']);
    return EntityPageData(
      entityId: ref.entityId,
      type: ref.type,
      name: ref.name,
      subtitle: _str(json['subtitle']),
      organization: org == null ? null : EntityRef.fromJson(org),
      summary: _str(json['summary']),
      summaryUpdatedAt: _date(json['summary_updated_at']),
      people: EntityRef.listFrom(json['people']),
      projects: EntityRef.listFrom(json['projects']),
      facts: Fact.listFrom(json['facts']),
      openTasks: _maps(json['open_tasks']).map(TaskRef.fromJson).whereType<TaskRef>().toList(growable: false),
      decisions: Fact.listFrom(json['decisions']),
      recentConversations: _maps(
        json['recent_conversations'],
      ).map(ConversationRef.fromJson).whereType<ConversationRef>().toList(growable: false),
      pendingQuestion: question == null ? null : ReviewItem.fromJson(question),
    );
  }
}
