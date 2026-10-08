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

enum ReviewItemKind { speaker, task, samePerson, spelling }

ReviewItemKind? _kind(Object? v) => switch (v) {
      'speaker' => ReviewItemKind.speaker,
      'task' => ReviewItemKind.task,
      'same_person' => ReviewItemKind.samePerson,
      'spelling' => ReviewItemKind.spelling,
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

class SpellingItem {
  const SpellingItem({required this.termId, required this.options, this.allowCustom = true});
  final String termId;
  final List<String> options;
  final bool allowCustom;

  static SpellingItem? fromJson(Map<String, dynamic>? json) {
    final id = _str(json?['term_id']);
    final options = _strings(json?['options']);
    if (id == null || options.isEmpty) return null;
    return SpellingItem(termId: id, options: options, allowCustom: json?['allow_custom'] != false);
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
    );
    final complete = switch (kind) {
      ReviewItemKind.speaker => item.speaker != null,
      ReviewItemKind.task => item.task != null,
      ReviewItemKind.samePerson => item.samePerson != null,
      ReviewItemKind.spelling => item.spelling != null,
    };
    return complete ? item : null;
  }
}

class ReviewItemsResponse {
  factory ReviewItemsResponse.fromGenerated(wire.GeneratedReviewItemsResponse generated) {
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
    this.notSure = false,
  });

  const ReviewAnswer.speaker({String? personId, String? newName, bool isMe = false})
      : this._(speakerPersonId: personId, speakerNewName: newName, speakerIsMe: isMe);
  const ReviewAnswer.acceptTask({String? description, DateTime? dueAt, String? workstreamId})
      : this._(taskAccept: true, taskDescription: description, taskDueAt: dueAt, taskWorkstreamId: workstreamId);
  const ReviewAnswer.dismissTask([TaskDismissReason? reason]) : this._(taskAccept: false, taskDismissReason: reason);
  const ReviewAnswer.samePerson(bool same) : this._(samePerson: same);
  const ReviewAnswer.spelling(String value) : this._(spelling: value);
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

class ReviewChange {
  factory ReviewChange.fromGenerated(wire.GeneratedReviewChange generated) {
    final value = fromJson(generated.toJson());
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
    this.refs = const [],
    this.undone = false,
  });
  final String changeId;
  final ReviewChangeKind kind;
  final String title;
  final String? reason;
  final String? snippet;
  final List<ReviewChangeRef> refs;
  final DateTime createdAt;
  final bool undone;

  ReviewChange copyWith({bool? undone}) => ReviewChange(
        changeId: changeId,
        kind: kind,
        title: title,
        reason: reason,
        snippet: snippet,
        refs: refs,
        createdAt: createdAt,
        undone: undone ?? this.undone,
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
    );
  }
}

class ReviewChangesPage {
  factory ReviewChangesPage.fromGenerated(wire.GeneratedReviewChangesResponse generated) {
    return fromJson(generated.toJson());
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
