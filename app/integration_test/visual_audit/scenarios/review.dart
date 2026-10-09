// Review: the few questions Omi asks (Home entry card, Review page, the shared detail sheet for
// every kind), Recent Changes with Undo, person / organization / project pages, the entity chips
// and inline question on a conversation, and Tasks grouped by project. Synthetic data only.
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/dream_report.dart';
import 'package:omi/backend/schema/gen/dream_wire.g.dart' as dream_wire;
import 'package:omi/backend/schema/review.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/entities/entity_page.dart';
import 'package:omi/pages/review/dream_report_page.dart';
import 'package:omi/pages/review/recent_changes_page.dart';
import 'package:omi/pages/review/review_item_sheet.dart';
import 'package:omi/pages/review/review_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart' show ConversationTab;

import '../fakes.dart';
import '../harness.dart';
import 'capture.dart' show AuditCaptureProvider, AuditLive, HomeFrame;

const _reviewPage = 'lib/pages/review/review_page.dart (ReviewPage)';
const _sheet = 'lib/pages/review/review_item_sheet.dart (showReviewItemSheet)';
const _entityPage = 'lib/pages/entities/entity_page.dart (EntityPage)';

final _now = DateTime.now();
DateTime _at(int daysAgo, int hour, int minute) => DateTime(_now.year, _now.month, _now.day - daysAgo, hour, minute);

const _bela = EntityRef(entityId: 'person:p-bela', type: EntityType.person, name: 'Béla');
const _marcus = EntityRef(entityId: 'person:p-marcus', type: EntityType.person, name: 'Marcus');
const _paraform = EntityRef(entityId: 'org-paraform', type: EntityType.organization, name: 'Paraform');
const _pilot = EntityRef(entityId: 'ws-pilot', type: EntityType.project, name: 'Paraform pilot');
const _hiring = EntityRef(entityId: 'ws-hiring', type: EntityType.project, name: 'Hiring');

final _speakerItem = ReviewItem(
  itemId: 'speaker:prompt-1',
  kind: ReviewItemKind.speaker,
  quote: 'If we get the pilot SOW signed by Friday, I’ll loop in our legal team the same day.',
  speaker: SpeakerItem(
    promptId: 'prompt-1',
    conversationId: 'conv-sync',
    conversationTitle: 'Weekly sync with Paraform',
    start: 412,
    end: 419,
    candidates: const [
      PersonRef(personId: 'p-bela', name: 'Béla', organization: 'Paraform'),
      PersonRef(personId: 'p-marcus', name: 'Marcus'),
    ],
    affectedConversationCount: 4,
    context: [
      TranscriptLine(speakerLabel: 'Marcus', text: 'Legal turnaround is usually two days.', at: _at(0, 14, 13)),
      TranscriptLine(
        speakerLabel: 'Speaker 2',
        text: 'If we get the pilot SOW signed by Friday, I’ll loop in our legal team the same day.',
        at: _at(0, 14, 14),
        isTarget: true,
      ),
      TranscriptLine(speakerLabel: 'You', text: 'Great, I’ll send the signed copy Thursday.', at: _at(0, 14, 14)),
    ],
  ),
);

final _taskItem = ReviewItem(
  itemId: 'task:cand-1',
  kind: ReviewItemKind.task,
  task: TaskItem(
    candidateId: 'cand-1',
    description: 'Send Béla the signed pilot SOW',
    dueAt: _at(-2, 17, 0),
    workstreamId: 'ws-pilot',
    workstreamTitle: 'Paraform pilot',
    evidence: Evidence(
      quote: 'Great, I’ll send the signed copy Thursday.',
      speakerLabel: 'You',
      at: _at(0, 14, 14),
      conversationId: 'conv-sync',
      conversationTitle: 'Weekly sync with Paraform',
    ),
  ),
);

const _samePersonItem = ReviewItem(
  itemId: 'same_person:pair-1',
  kind: ReviewItemKind.samePerson,
  samePerson: SamePersonItem(
    left: EntitySummary(
      entityId: 'person:p-bela',
      type: EntityType.person,
      name: 'Béla',
      subtitle: 'Paraform',
      conversationCount: 6,
      signals: ['Voice profile'],
    ),
    right: EntitySummary(
      entityId: 'person:p-bela-k',
      type: EntityType.person,
      name: 'Bela K',
      conversationCount: 2,
      signals: ['From contacts', 'paraform.com'],
    ),
    reason: 'Same name and company, and both appear in the Paraform pilot conversations.',
  ),
);

const _spellingItem = ReviewItem(
  itemId: 'spelling:term-1',
  kind: ReviewItemKind.spelling,
  quote: 'We’re piloting Pairform’s hiring tool for six weeks.',
  spelling: SpellingItem(termId: 'term-1', options: ['Paraform', 'Pairform']),
);

/// A short silent WAV; the scenarios never play audio.
Uint8List _clip() => Uint8List.fromList(List<int>.filled(44 + 3200, 0));

ReviewProvider _review({List<ReviewItem>? items}) => ReviewProvider(
      isEligible: () => true,
      reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
      loadItems: () async => ApiSuccess(ReviewItemsResponse(
        items: items ?? [_speakerItem, _taskItem, _samePersonItem],
        remainingToday: items?.length ?? 3,
      )),
      sendAnswer: (_, __) async => const ApiSuccess(1),
      loadClip: (_) async => ApiSuccess(_clip()),
      playClip: (_, __) async => true,
      loadProjects: () async => const ApiSuccess([_pilot, _hiring]),
      loadConversationEntities: (_) async => const ApiSuccess([_paraform, _pilot]),
    );

Future<ReviewProvider> _loadedReview(AuditRun a, {List<ReviewItem>? items}) async {
  final review = _review(items: items);
  await a.tester.runAsync(review.load);
  return review;
}

Future<void> _openSheet(AuditRun a, ReviewItem item) async {
  final review = await _loadedReview(a);
  await a.pumpHost(
    (context) => showReviewItemSheet(context, item),
    providers: [ChangeNotifierProvider<ReviewProvider>.value(value: review)],
  );
}

final _personPage = EntityPageData(
  entityId: 'person:p-bela',
  type: EntityType.person,
  name: 'Béla Kovács',
  subtitle: 'Head of Partnerships',
  organization: _paraform,
  summary: 'Your main contact at Paraform for the pilot. You talk most weeks, usually on Tuesdays. '
      'He handles the contract side and is waiting on your signed SOW.',
  summaryUpdatedAt: _at(0, 12, 0),
  projects: const [_pilot],
  facts: [
    Fact(
      factId: 'f1',
      text: 'Based in Budapest; in San Francisco about once a month',
      sourceKind: FactSourceKind.conversation,
      sourceLabel: 'Paraform intro',
      conversationId: 'conv-intro',
      at: _at(14, 10, 0),
    ),
    Fact(
      factId: 'f2',
      text: 'Prefers a short written update before calls',
      sourceKind: FactSourceKind.chat,
      sourceLabel: 'Chat',
      at: _at(10, 9, 0),
    ),
    Fact(
      factId: 'f3',
      text: 'Hosting the Budapest workshop on Oct 20',
      sourceKind: FactSourceKind.conversation,
      sourceLabel: 'Weekly sync',
      conversationId: 'conv-sync',
      at: _at(0, 14, 0),
    ),
    Fact(
      factId: 'f4',
      text: 'Reviewed the pilot pricing page',
      sourceKind: FactSourceKind.screen,
      sourceLabel: 'Screen',
      at: _at(6, 16, 0),
    ),
  ],
  openTasks: [
    TaskRef(taskId: 't1', description: 'Send Béla the signed pilot SOW', ownerLabel: 'You', dueAt: _at(-2, 17, 0)),
    const TaskRef(taskId: 't2', description: 'Security questionnaire from Paraform', waitingOn: 'Béla'),
  ],
  recentConversations: [
    ConversationRef(
        conversationId: 'conv-sync',
        title: 'Weekly sync with Paraform',
        startedAt: _at(0, 14, 2),
        durationSeconds: 2280),
    ConversationRef(
        conversationId: 'conv-scope', title: 'Pilot scoping call', startedAt: _at(7, 11, 0), durationSeconds: 3120),
    ConversationRef(
        conversationId: 'conv-intro', title: 'Paraform intro', startedAt: _at(14, 10, 0), durationSeconds: 1440),
  ],
  pendingQuestion: _samePersonItem,
);

final _orgPage = EntityPageData(
  entityId: 'org-paraform',
  type: EntityType.organization,
  name: 'Paraform',
  subtitle: 'Hiring platform · partner',
  summary: 'A hiring platform you’re piloting. Béla runs the relationship; Marcus handles legal and logistics. '
      'The signed SOW is the open item.',
  people: const [_bela, _marcus],
  projects: const [_pilot],
  facts: [
    Fact(
      factId: 'o1',
      text: 'Offices in San Francisco and Budapest',
      sourceKind: FactSourceKind.conversation,
      sourceLabel: 'Paraform intro',
      at: _at(14, 10, 0),
    ),
    Fact(
      factId: 'o2',
      text: 'Legal review usually takes two days',
      sourceKind: FactSourceKind.conversation,
      sourceLabel: 'Weekly sync',
      at: _at(0, 14, 0),
    ),
  ],
  recentConversations: [
    ConversationRef(
        conversationId: 'conv-sync',
        title: 'Weekly sync with Paraform',
        startedAt: _at(0, 14, 2),
        durationSeconds: 2280),
    ConversationRef(
        conversationId: 'conv-scope', title: 'Pilot scoping call', startedAt: _at(7, 11, 0), durationSeconds: 3120),
  ],
);

final _projectPage = EntityPageData(
  entityId: 'ws-pilot',
  type: EntityType.project,
  name: 'Paraform pilot',
  subtitle: 'Active · 9 conversations',
  organization: _paraform,
  summary: 'A 6-week pilot of Paraform’s hiring tool. Pricing is agreed; the signed SOW is the next step, '
      'then a kickoff workshop in Budapest on Oct 20.',
  people: const [_bela, _marcus],
  decisions: [
    Fact(
      factId: 'd1',
      text: 'Pilot price fixed at the startup tier',
      sourceKind: FactSourceKind.conversation,
      sourceLabel: 'Pilot scoping call',
      at: _at(7, 11, 0),
    ),
    Fact(
      factId: 'd2',
      text: 'Workshop in Budapest, not remote',
      sourceKind: FactSourceKind.conversation,
      sourceLabel: 'Weekly sync',
      at: _at(0, 14, 0),
    ),
  ],
  openTasks: [
    TaskRef(taskId: 't1', description: 'Send Béla the signed pilot SOW', ownerLabel: 'You', dueAt: _at(-2, 17, 0)),
    TaskRef(taskId: 't3', description: 'Book the workshop room', ownerLabel: 'Marcus', dueAt: _at(-7, 17, 0)),
    const TaskRef(taskId: 't2', description: 'Security questionnaire', waitingOn: 'Béla'),
  ],
);

Future<void> _pumpEntity(AuditRun a, EntityPageData page) async {
  final review = await _loadedReview(a, items: const [_samePersonItem]);
  await a.pump(
    EntityPage(entityId: page.entityId, load: (_) async => ApiSuccess(page)),
    scaffold: false,
    providers: [ChangeNotifierProvider<ReviewProvider>.value(value: review)],
  );
}

List<ReviewChange> _changes() => [
      ReviewChange(
        changeId: 'ch1',
        kind: ReviewChangeKind.rename,
        title: '“Pairform” → “Paraform” in 7 notes',
        reason: 'You confirmed the spelling in Review.',
        createdAt: _at(0, 9, 30),
      ),
      ReviewChange(
        changeId: 'ch2',
        kind: ReviewChangeKind.mergeMemories,
        title: 'Merged two memories',
        reason: 'Both came from your own words, a week apart.',
        snippet: '“Prefers morning meetings” + “Likes calls before 11” → “Prefers meetings before 11 AM”',
        createdAt: _at(0, 8, 10),
      ),
      ReviewChange(
        changeId: 'ch3',
        kind: ReviewChangeKind.closeTask,
        title: 'Closed “Book flight to Lisbon”',
        createdAt: _at(0, 7, 45),
        undone: true,
      ),
      ReviewChange(
        changeId: 'ch4',
        kind: ReviewChangeKind.updatePerson,
        title: 'Updated Béla: Head of Partnerships, Paraform',
        reason: 'Béla said it when introducing the team.',
        snippet: '“…I run partnerships at Paraform, so anything contract-side comes through me.”',
        createdAt: _at(1, 18, 20),
      ),
      ReviewChange(
        changeId: 'ch5',
        kind: ReviewChangeKind.labelSpeaker,
        title: 'Labeled Marcus in 2 conversations',
        reason: 'Same voice as the clip you labeled on Oct 3.',
        createdAt: _at(1, 15, 5),
      ),
      ReviewChange(
        changeId: 'ch6',
        kind: ReviewChangeKind.titleConversation,
        title: 'Titled a conversation “Lunch with Priya about hiring”',
        reason: 'It was untitled; the summary is about two open roles.',
        createdAt: _at(3, 13, 0),
      ),
    ];

ServerConversation _syncConversation() {
  TranscriptSegment seg(String id, String text, String speaker, {bool isUser = false}) {
    final start = 400 + double.parse(id) * 6;
    return TranscriptSegment(
      id: id,
      text: text,
      speaker: speaker,
      isUser: isUser,
      personId: null,
      start: start,
      end: start + 5,
      translations: [],
    );
  }

  final started = _at(0, 14, 2);
  return ServerConversation(
    id: 'conv-sync',
    createdAt: started,
    startedAt: started,
    finishedAt: started.add(const Duration(minutes: 38)),
    structured: Structured(
      'Weekly sync with Paraform',
      'Security questionnaire is done. Béla will loop in legal once the pilot SOW is signed; the Budapest '
          'workshop stays on the 20th.',
      emoji: '📅',
      category: 'work',
    ),
    transcriptSegments: [
      seg('1', 'Where are we on the security review?', 'SPEAKER_0', isUser: true),
      seg('2', 'Questionnaire is done. Legal turnaround is usually two days on our side.', 'SPEAKER_1'),
      seg('3', 'If we get the pilot SOW signed by Friday, I’ll loop in our legal team the same day.', 'SPEAKER_2'),
      seg('4', 'Great, I’ll send the signed copy Thursday.', 'SPEAKER_0', isUser: true),
      seg('5', 'Perfect. And let’s keep the Budapest workshop on the 20th.', 'SPEAKER_2'),
    ],
    status: ConversationStatus.completed,
  );
}

ActionItemWithMetadata _task(String id, String description, {String? workstreamId, DateTime? dueAt, int order = 0}) =>
    ActionItemWithMetadata(
      id: id,
      description: description,
      completed: false,
      sortOrder: 1000 + order,
      workstreamId: workstreamId,
      dueAt: dueAt,
    );

Map<String, dynamic> _dreamRun(String id, String at, {String trigger = 'schedule', String status = 'complete'}) => {
      'run_id': id,
      'created_at': at,
      'trigger': trigger,
      'status': status,
      'error_type': status == 'failed' ? 'HTTPStatusError' : null,
      'records_read': 42,
      'records_queued_after': 66,
      'tokens': 7800,
      'cost_usd': 0.0156,
      'edits': status == 'failed'
          ? []
          : [
              {
                'kind': 'spelling',
                'target_label': 'Paraform weekly sync',
                'before': 'Bella',
                'after': 'Béla',
                'reason': 'Spelled Béla in the calendar invite and in three other conversations',
                'evidence_count': 4,
                'outcome': 'shadow',
              },
              {
                'kind': 'merge_memories',
                'target_label': 'Prefers morning meetings',
                'before': '',
                'after': 'Prefers meetings before 11am',
                'reason': 'Two memories say the same thing',
                'evidence_count': 2,
                'outcome': 'shadow',
              },
              {
                'kind': 'close_task',
                'target_label': 'Send the SOW to Paraform',
                'before': '',
                'after': '',
                'reason': 'You said it was sent in Thursday\'s call',
                'evidence_count': 1,
                'outcome': 'shadow',
              },
            ],
      'questions': status == 'failed'
          ? []
          : [
              {'kind': 'same_person', 'text': 'Is Bela K the same person as Béla?'},
            ],
      'slow_tasks': status == 'failed'
          ? []
          : [
              {'description': 'Book the venue for the team offsite'},
            ],
      'vocabulary': status == 'failed'
          ? []
          : [
              {
                'kind': 'person',
                'spelling': 'Béla',
                'aliases': ['Bella']
              },
              {'kind': 'organization', 'spelling': 'Paraform', 'aliases': []},
              {
                'kind': 'jargon',
                'spelling': 'Soniox',
                'aliases': ['Sonix']
              },
            ],
      'feedback': status == 'failed'
          ? []
          : [
              {'component': 'transcription', 'failure_class': 'spelling', 'severity': 'warning', 'count': 4},
            ],
      'privacy_rejected': status == 'failed' ? 0 : 1,
    };

DreamReport _dreamReport({bool empty = false}) =>
    DreamReport.fromGenerated(dream_wire.GeneratedDreamRunsResponse.fromJson({
      'mode': 'shadow',
      'passes_today': 2,
      'passes_limit': 4,
      'manual_runs_today': 1,
      'manual_runs_limit': 3,
      'queued_changes': empty ? 0 : 66,
      'runs': empty
          ? []
          : [
              _dreamRun('r3', '2026-10-09T12:00:41Z', trigger: 'manual'),
              _dreamRun('r2', '2026-10-09T11:00:47Z'),
              _dreamRun('r1', '2026-10-09T06:00:05Z', status: 'failed'),
            ],
    }));

final reviewScenarios = <AuditScenario>[
  AuditScenario(
    id: 'review-entry-home',
    title: 'Home: the “Questions for you” card opens Review',
    page: 'lib/pages/review/widgets/review_entry_card.dart (ReviewEntryCard) on Home',
    state: 'Review on; three questions queued; four conversations today',
    run: (a) async {
      final review = await _loadedReview(a);
      ServerConversation convo(String id, String title, String emoji, DateTime at, int minutes) => ServerConversation(
            id: id,
            createdAt: at,
            startedAt: at,
            finishedAt: at.add(Duration(minutes: minutes)),
            structured: Structured(title, 'Overview', emoji: emoji, category: 'work'),
            status: ConversationStatus.completed,
          );
      final items = [
        convo('h1', 'Weekly sync with Paraform', '📅', _at(0, 14, 2), 38),
        convo('h2', 'Lunch with Priya about hiring', '🍽️', _at(0, 12, 10), 46),
        convo('h3', 'Morning run notes', '🏃', _at(0, 7, 31), 6),
      ];
      final conversations = ConversationProvider(
        conversationListFetcher: () async => (items: items, ok: true),
        isSignedIn: () => true,
      )
        ..conversations = items
        ..groupConversationsByDate();
      await a.pump(const HomeFrame(), scaffold: false, providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: AuditDeviceProvider()),
        ChangeNotifierProvider<CaptureProvider>.value(value: AuditCaptureProvider(AuditLive.idle)),
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
        ChangeNotifierProvider<ReviewProvider>.value(value: review),
      ]);
      expect(find.byKey(const Key('review_entry_card')), findsOneWidget);
      await a.shot('Open the app: the Review card sits above today’s conversations');
    },
  ),
  AuditScenario(
    id: 'review-home',
    title: 'Review: three simple question cards',
    page: _reviewPage,
    state: 'A speaker clip (two candidates), a suggested task, and a same-person question',
    run: (a) async {
      final review = await _loadedReview(a);
      await a.pump(const ReviewPage(), scaffold: false, providers: [
        ChangeNotifierProvider<ReviewProvider>.value(value: review),
      ]);
      await a.shot('Open Review from the Home card');
    },
  ),
  AuditScenario(
    id: 'review-caught-up',
    title: 'Review: nothing left to answer',
    page: _reviewPage,
    state: 'Review on with an empty queue',
    run: (a) async {
      final review = await _loadedReview(a, items: const []);
      await a.pump(const ReviewPage(), scaffold: false, providers: [
        ChangeNotifierProvider<ReviewProvider>.value(value: review),
      ]);
      await a.shot('Answer the last question');
    },
  ),
  AuditScenario(
    id: 'review-sheet-speaker',
    title: 'Detail sheet: who said this',
    page: _sheet,
    state: 'The speaker question; Béla preselected as the closest voice',
    run: (a) async {
      await _openSheet(a, _speakerItem);
      await a.shot('Tap the speaker card');
    },
  ),
  AuditScenario(
    id: 'review-sheet-task',
    title: 'Detail sheet: suggested task, then the dismiss reasons',
    page: _sheet,
    state: 'A task suggested from the user’s own words, in the Paraform pilot project',
    run: (a) async {
      await _openSheet(a, _taskItem);
      await a.shot('Tap the task card');
      await a.tap(find.byKey(const Key('review_task_dismiss')));
      await a.shot('Tap Dismiss: the reasons appear', step: 'dismiss');
    },
  ),
  AuditScenario(
    id: 'review-sheet-same-person',
    title: 'Detail sheet: same person?',
    page: _sheet,
    state: 'Béla (voice profile, six conversations) and “Bela K” from contacts',
    run: (a) async {
      await _openSheet(a, _samePersonItem);
      await a.shot('Tap the same-person card');
    },
  ),
  AuditScenario(
    id: 'review-sheet-spelling',
    title: 'Detail sheet: how is this spelled?',
    page: _sheet,
    state: 'Two candidate spellings from a transcript',
    run: (a) async {
      await _openSheet(a, _spellingItem);
      await a.tap(find.text('Paraform'));
      await a.shot('Choose a spelling');
    },
  ),
  AuditScenario(
    id: 'review-recent-changes',
    title: 'Recent Changes with Undo, one already undone',
    page: 'lib/pages/review/recent_changes_page.dart (RecentChangesPage)',
    state: 'Six automatic edits over three days; the task close was undone',
    run: (a) async {
      await a.pump(
        RecentChangesPage(
          loadChanges: ({cursor}) async => ApiSuccess(ReviewChangesPage(changes: _changes())),
          setUndone: (id, {required undone}) async =>
              ApiSuccess(_changes().firstWhere((c) => c.changeId == id).copyWith(undone: undone)),
        ),
        scaffold: false,
      );
      await a.scrollSeries('Open Recent Changes from Review');
    },
  ),
  AuditScenario(
    id: 'review-entity-person',
    title: 'Person page kept current by Omi',
    page: _entityPage,
    state: 'Béla: summary, a pending same-person question, open threads, facts with sources, conversations',
    run: (a) async {
      await _pumpEntity(a, _personPage);
      await a.scrollSeries('Open Béla');
    },
  ),
  AuditScenario(
    id: 'review-entity-organization',
    title: 'Organization page',
    page: _entityPage,
    state: 'Paraform: summary, people, projects, conversations and facts',
    run: (a) async {
      await _pumpEntity(a, _orgPage);
      await a.scrollSeries('Open Paraform');
    },
  ),
  AuditScenario(
    id: 'review-entity-project',
    title: 'Project page',
    page: _entityPage,
    state: 'Paraform pilot: summary, people, decisions and open tasks',
    run: (a) async {
      await _pumpEntity(a, _projectPage);
      await a.scrollSeries('Open the Paraform pilot project');
    },
  ),
  AuditScenario(
    id: 'review-conversation-inline',
    title: 'Conversation: organization and project chips, and the speaker question in the transcript',
    page: 'lib/pages/conversation_detail/page.dart (ConversationDetailPage) with ConversationEntityChips',
    state: 'The Paraform sync; Review on with a speaker question about Speaker 2 in this conversation',
    run: (a) async {
      final review = await _loadedReview(a, items: [_speakerItem]);
      final conversation = _syncConversation();
      await a.pump(
        ConversationDetailPage(conversation: conversation, initialTab: ConversationTab.transcript),
        providers: [
          ChangeNotifierProvider<ConversationProvider>.value(
            value: ConversationProvider(isSignedIn: () => true)..conversations = [conversation],
          ),
          ChangeNotifierProvider(
            create: (_) => ConversationDetailProvider()..selectedDate = conversationLocalDayKey(conversation.createdAt),
          ),
          ChangeNotifierProvider<ReviewProvider>.value(value: review),
        ],
      );
      await a.shot('Open the conversation on Transcript');
    },
  ),
  AuditScenario(
    id: 'review-tasks-by-project',
    title: 'Tasks grouped by project',
    page: 'lib/pages/action_items/project_task_sections.dart (projectTaskSections) in ActionItemsPage',
    state: 'Six open tasks: three in Paraform pilot, two in Hiring, one with no project',
    run: (a) async {
      final review = await _loadedReview(a);
      await a.tester.runAsync(review.loadProjects);
      final actionItems = ActionItemsProvider(
        getActionItems: ({
          int limit = 100,
          int offset = 0,
          bool? completed,
          String? conversationId,
          DateTime? startDate,
          DateTime? endDate,
          DateTime? dueStartDate,
          DateTime? dueEndDate,
        }) async =>
            ActionItemsResponse(actionItems: [
          _task('t1', 'Send Béla the signed pilot SOW', workstreamId: 'ws-pilot', dueAt: _at(-2, 17, 0), order: 1),
          _task('t3', 'Book the workshop room', workstreamId: 'ws-pilot', dueAt: _at(-7, 17, 0), order: 2),
          _task('t2', 'Security questionnaire', workstreamId: 'ws-pilot', order: 3),
          _task('t4', 'Draft the backend engineer posting', workstreamId: 'ws-hiring', dueAt: _at(-5, 9, 0), order: 4),
          _task('t5', 'Follow up with Priya on referrals', workstreamId: 'ws-hiring', order: 5),
          _task('t6', 'Renew passport', dueAt: _at(-24, 9, 0), order: 6),
        ]),
      );
      await a.tester.runAsync(actionItems.ensureLoaded);
      await a.pump(
        const HomeFrame(tasks: ActionItemsPage()),
        scaffold: false,
        providers: [
          ChangeNotifierProvider<ActionItemsProvider>.value(value: actionItems),
          ChangeNotifierProvider<HomeProvider>(create: (_) => HomeProvider()..setIndex(HomeProvider.tasksTab)),
          ChangeNotifierProvider<DeviceProvider>.value(value: AuditDeviceProvider()),
          ChangeNotifierProvider<CaptureProvider>.value(value: AuditCaptureProvider(AuditLive.idle)),
          ChangeNotifierProvider<ReviewProvider>.value(value: review),
        ],
      );
      await a.tap(find.byTooltip('More options').first);
      await a.shot('Open the ⋯ menu on Tasks', step: 'menu');
      await a.tap(find.text('Group by Project'));
      await a.shot('Choose Group by Project', step: 'grouped');
    },
  ),
  AuditScenario(
    id: 'review-dream-report',
    title: 'Dream Report in preview mode',
    page: 'lib/pages/review/dream_report_page.dart (DreamReportPage)',
    state:
        'Shadow mode; a manual pass with fixes, a question, a task and learned words; a scheduled pass; a failed pass',
    run: (a) async {
      await a.pump(
        DreamReportPage(
          loadReport: () async => ApiSuccess(_dreamReport()),
          runNow: () async => ApiSuccess(
            DreamRun.fromGenerated(dream_wire.GeneratedDreamRun.fromJson(_dreamRun('r4', '2026-10-09T12:30:00Z'))),
          ),
        ),
        scaffold: false,
      );
      await a.scrollSeries('Open Dream Report from Review');
    },
  ),
  AuditScenario(
    id: 'review-dream-report-empty',
    title: 'Dream Report before the first pass',
    page: 'lib/pages/review/dream_report_page.dart (DreamReportPage)',
    state: 'Shadow mode, no passes yet',
    run: (a) async {
      await a.pump(
        DreamReportPage(loadReport: () async => ApiSuccess(_dreamReport(empty: true))),
        scaffold: false,
      );
      await a.shot('Open Dream Report before any pass', step: 'empty');
    },
  ),
];
