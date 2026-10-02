// Settings screens with heavy, long, empty and failing data: the states where a layout that looks
// fine with the fixture account breaks once a real account's data arrives.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/pages/conversations/synced_conversations_page.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/goals/goals_page.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/pages/payments/payments_page.dart';
import 'package:omi/pages/settings/conversation_display_settings.dart';
import 'package:omi/pages/settings/custom_vocabulary_page.dart';
import 'package:omi/pages/settings/data_privacy_page.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:omi/pages/settings/permissions_page.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/pages/settings/developer.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/pages/settings/import_history_page.dart';
import 'package:omi/pages/settings/people.dart';
import 'package:omi/pages/settings/phone_call_settings_page.dart';
import 'package:omi/pages/settings/profile.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/pages/settings/settings_groups.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/integrations/asana_service.dart';
import 'package:omi/services/integrations/clickup_service.dart';
import 'package:omi/services/integrations/todoist_service.dart';
import 'package:omi/services/wals.dart';

import '../fakes.dart';
import '../harness.dart';

const _autoSync = 'lib/pages/conversations/auto_sync_page.dart (AutoSyncPage)';

/// Every row state the sync pages draw, newest first, a few minutes apart on one morning.
List<Wal> _everyWalState() {
  final start = DateTime(2026, 9, 20, 11, 40).millisecondsSinceEpoch ~/ 1000;
  var i = 0;
  Wal wal(WalStatus status,
          {int retries = 0,
          bool syncing = false,
          WalStorage storage = WalStorage.disk,
          WalStorage? original,
          int seconds = 754}) =>
      Wal(
        timerStart: start - (i++) * 900,
        codec: BleAudioCodec.opus,
        seconds: seconds,
        status: status,
        storage: storage,
        originalStorage: original,
        device: 'omi-device-1',
        retryCount: retries,
      )..isSyncing = syncing;
  return [
    wal(WalStatus.miss, syncing: true, storage: WalStorage.sdcard),
    wal(WalStatus.miss),
    wal(WalStatus.miss, retries: 1),
    wal(WalStatus.miss, retries: walMaxAutoRetries),
    wal(WalStatus.uploaded),
    wal(WalStatus.corrupted),
    wal(WalStatus.outsideRecoveryWindow, seconds: 5 * 3600 + 42 * 60),
    wal(WalStatus.unsupportedAudio, seconds: 8),
    wal(WalStatus.uploadRejected),
    wal(WalStatus.miss, storage: WalStorage.sdcard, original: WalStorage.sdcard),
    wal(WalStatus.synced),
    wal(WalStatus.synced, storage: WalStorage.disk, original: WalStorage.sdcard),
  ];
}

/// A SyncProvider holding [wals] in a fixed [state]; nothing syncs.
class _SyncData extends InertSyncProvider {
  _SyncData(this.wals, {this.state = const SyncState(), this.pointers = const []});

  final List<Wal> wals;
  final SyncState state;
  final List<SyncedConversationPointer> pointers;
  WalStatusFilter _statusFilter = WalStatusFilter.pending;

  bool _pending(Wal w) => w.status == WalStatus.miss || w.status == WalStatus.inProgress;

  @override
  SyncState get syncState => state;
  @override
  List<Wal> get allWals => wals;
  @override
  List<Wal> get displaySortedWals => wals;
  @override
  List<Wal> walsForDisplayFilter(WalDisplayFilter filter) => switch (filter) {
        WalDisplayFilter.all => wals,
        WalDisplayFilter.synced => wals.where((w) => w.status == WalStatus.synced).toList(),
        WalDisplayFilter.pending => wals.where((w) => w.status != WalStatus.synced).toList(),
      };
  @override
  int get clearableWalsCount => wals.length;
  @override
  int get needsAttentionWalsCount =>
      wals.where((w) => w.syncDisplayState.index >= WalSyncDisplayState.failed.index).length;
  @override
  bool get isSyncing => state.isSyncing;
  @override
  bool get syncCompleted => pointers.isNotEmpty;
  @override
  List<SyncedConversationPointer> get syncedConversationsPointers => pointers;
  @override
  List<Wal> get uploadedWals => const [];
  @override
  ({int processed, int total}) get offlineServerProcessingCounts => (processed: 2, total: 5);
  @override
  List<Wal> get syncedWals => wals.where((w) => w.status == WalStatus.synced).toList();
  @override
  List<Wal> get pendingDeletableWals => wals.where(_pending).toList();
  // The legacy page.
  @override
  Future<void> refreshWals() async {}
  @override
  bool get isLoadingWals => false;
  @override
  String? get syncError => state.errorMessage;
  @override
  Wal? get failedWal => state.failedWal;
  @override
  List<Wal> get missingWals => wals.where((w) => w.status == WalStatus.miss).toList();
  @override
  double? get syncSpeedKBps => state.speedKBps;
  @override
  bool get isSdCardSyncing => false;
  @override
  WalStatusFilter get statusFilter => _statusFilter;
  @override
  void setStatusFilter(WalStatusFilter filter) {
    _statusFilter = filter;
    notifyListeners();
  }

  @override
  int get pendingStatusCount => wals.where(_pending).length;
  @override
  int get syncedStatusCount => syncedWals.length;
  @override
  int get corruptedStatusCount => wals.where((w) => w.status == WalStatus.corrupted).length;
  @override
  List<Wal> get filteredByStatusWals => switch (_statusFilter) {
        WalStatusFilter.pending => wals.where(_pending).toList(),
        WalStatusFilter.synced => syncedWals,
        WalStatusFilter.corrupted => wals.where((w) => w.status == WalStatus.corrupted).toList(),
      };
  @override
  Wal? getWalById(String id) => wals.where((w) => w.id == id).firstOrNull;
}

/// A connected ring-buffer pendant (firmware 3.0.20+) whose storage is nearly full.
class _RingDevice extends AuditDeviceProvider {
  _RingDevice() : super(connected: true, battery: 64);
  @override
  String get currentFirmwareVersion => '3.0.21';
  @override
  RingStatus? get ringStatus =>
      RingStatus(usedBytes: 61 * 1024 * 1024, unreadPackets: 4, freeBytes: 2 * 1024 * 1024, rtcValid: 1);
}

List<SyncedConversationPointer> _pointers() => [
      for (final (i, title, type) in [
        (
          0,
          'Quarterly planning with the design team and the two contractors from Lisbon',
          SyncedConversationType.newConversation
        ),
        (1, '', SyncedConversationType.newConversation),
        (2, 'Coffee catch-up', SyncedConversationType.updatedConversation),
      ])
        SyncedConversationPointer(
          type: type,
          index: i,
          key: DateTime(2026, 9, 20),
          conversation: auditConversation('synced-$i', title: title),
        ),
    ];

const _longName = 'Maximiliana Alexandra Featherstonehaugh-Montgomery';
const _longEmail = 'maximiliana.featherstonehaugh-montgomery@a-very-long-company-domain.example.com';

/// A paired pendant with a long user-given name, low battery and a firmware update waiting.
final _longDevice = BtDevice(
  id: 'C8:2A:91:7F:00:1E',
  name: "Maximiliana's Omi pendant (kitchen, the one with the blue lanyard)",
  type: DeviceType.omi,
  rssi: -61,
  modelNumber: 'Omi DevKit 2',
  firmwareRevision: '2.0.10',
  hardwareRevision: 'Seeed Xiao BLE Sense nRF52840 rev C',
  manufacturerName: 'Based Hardware',
  serialNumber: 'OMI-2026-0009-7741-AXQ',
);

UsageStats _stats(int seconds, int words, int insights, int memories) => UsageStats(
    transcriptionSeconds: seconds,
    speechSeconds: seconds ~/ 2,
    wordsTranscribed: words,
    insightsGained: insights,
    memoriesCreated: memories);

/// Usage answered locally: heavy numbers in every period, an hourly and a daily history.
UsageProvider _heavyUsage() {
  final today = DateTime.now();
  return UsageProvider(
    deviceTimeZone: () async => 'UTC',
    usageRequest: ({required String period, required String? timeZone}) async => UserUsageResponse(
      today: _stats(9 * 3600 + 41 * 60, 84213, 312, 47),
      monthly: _stats(214 * 3600 + 5 * 60, 1874320, 6021, 980),
      yearly: _stats(1523 * 3600, 12403551, 48210, 7302),
      allTime: _stats(4210 * 3600 + 59 * 60, 99999999, 230118, 41007),
      history: [
        for (var h = 0; h < 24; h += 2)
          UsageHistoryPoint(
            date: period == 'today'
                ? DateTime.utc(today.year, today.month, today.day, h).toIso8601String()
                : DateTime(today.year, today.month, 1 + h).toIso8601String().substring(0, 10),
            transcriptionSeconds: 600 * h,
            speechSeconds: 300 * h,
            wordsTranscribed: 4000 * h + 120,
            insightsGained: h,
            memoriesCreated: h ~/ 2,
          ),
      ],
    ),
  );
}

Map<String, Object> _subscription(
        {required String plan, required int wordsUsed, required int wordsLimit, double chat = 0}) =>
    {
      'subscription': {
        'plan': plan,
        'status': 'active',
        'limits': {'transcription_seconds': 4 * 3600, 'words_transcribed': wordsLimit, 'insights_gained': 50},
        'current_period_end': DateTime(2026, 10, 31).millisecondsSinceEpoch ~/ 1000,
      },
      'transcription_seconds_used': 4 * 3600 + 120,
      'transcription_seconds_limit': 4 * 3600,
      'words_transcribed_used': wordsUsed,
      'words_transcribed_limit': wordsLimit,
      'insights_gained_used': 61,
      'insights_gained_limit': 50,
      'chat_quota_used': chat * 30,
      'chat_quota_unit': 'questions',
      'chat_quota_percent': chat * 100,
      'show_subscription_ui': true,
    };

Map<String, Object?> _key(String id, String name, String prefix, {String? lastUsed}) => {
      'id': id,
      'name': name,
      'key_prefix': prefix,
      'created_at': '2026-09-01T10:00:00Z',
      'last_used_at': lastUsed,
      'scopes': ['conversations:read', 'memories:read', 'memories:write', 'action_items:read'],
    };

class _VocabularyUser extends UserProvider {
  _VocabularyUser(this.words);
  final List<String> words;
  @override
  List<String> get transcriptionVocabulary => words;
}

class _NumbersPhoneCallProvider extends PhoneCallProvider {
  _NumbersPhoneCallProvider() : super.forTesting();
  @override
  bool get numbersLoaded => true;
  @override
  List<VerifiedPhoneNumber> get verifiedNumbers => [
        VerifiedPhoneNumber.fromJson(const {
          'id': 'n1',
          'phone_number': '+1 (415) 555-0137',
          'friendly_name': "Maximiliana's work phone (shared with the whole support team)",
          'is_primary': true,
          'verified_at': '2026-09-01T10:00:00Z',
        }),
        VerifiedPhoneNumber.fromJson(const {
          'id': 'n2',
          'phone_number': '+44 20 7946 0958',
          'is_primary': false,
          'verified_at': '2026-09-02T10:00:00Z',
        }),
      ];
  @override
  Future<void> loadVerifiedNumbers() async {}
}

class _ConnectedPayments extends InertPaymentMethodProvider {
  @override
  bool get isStripeConnected => true;
  @override
  bool get isPayPalConnected => true;
  @override
  PaymentMethodType? get activeMethod => PaymentMethodType.stripe;
}

Goal _goal(String id, String title, num current, num target, {String type = 'numeric', String? unit}) => Goal.fromJson({
      'id': id,
      'title': title,
      'goal_type': type,
      'current_value': current,
      'target_value': target,
      if (unit != null) 'unit': unit,
    });

Person _person(String id, String name, int count) => Person(
      id: id,
      name: name,
      createdAt: DateTime.utc(2026, 9, 1),
      updatedAt: DateTime.utc(2026, 9, 1),
      conversationCount: count,
      lastHeardAt: DateTime.now().subtract(Duration(days: count)),
      talkSeconds: count * 245.0,
      confidence: 'confirmed',
      voiceReadiness: 'ready',
    );

void _silencePhoneCallEvents() {
  const channel = 'com.omi/phone_calls/events';
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMessageHandler(channel, (_) async => const StandardMethodCodec().encodeSuccessEnvelope(null));
  addTearDown(() => messenger.setMockMessageHandler(channel, null));
}

final _moreEdgeScenarios = <AuditScenario>[
  AuditScenario(
    id: 'edge-settings-long-profile',
    title: 'Settings and Account with a very long name and email',
    page: 'lib/pages/settings/settings_drawer.dart (SettingsDrawer)',
    state: 'A 50-character name and an 80-character email',
    prefs: const {'givenName': _longName, 'email': _longEmail},
    run: (a) async {
      await a.pump(const SettingsDrawer());
      await a.shot('Open Settings with a long name and email', step: 'settings');
      await a.pump(const ProfilePage());
      await a.shot('Open Account with a long name and email', step: 'account');
    },
  ),
  AuditScenario(
    id: 'edge-settings-no-name',
    title: 'Settings and Account before a name or email is known',
    page: 'lib/pages/settings/settings_drawer.dart (SettingsDrawer)',
    state: 'Empty name and email (a fresh phone sign-in)',
    prefs: const {'givenName': '', 'email': ''},
    run: (a) async {
      await a.pump(const SettingsDrawer());
      await a.shot('Open Settings with no name or email', step: 'settings');
      await a.pump(const ProfilePage());
      await a.shot('Open Account with no name or email', step: 'account');
    },
  ),
  AuditScenario(
    id: 'edge-settings-search-empty',
    title: 'Settings search with no results',
    page: 'lib/pages/settings/settings_drawer.dart (SettingsDrawer)',
    state: 'A query that matches nothing, then a long one',
    run: (a) async {
      await a.pump(const SettingsDrawer());
      await a.tap(find.bySemanticsLabel('Search'));
      await a.enterText(find.byType(TextField).first, 'zzqx');
      await a.shot('Search Settings for something that is not there', step: 'none');
      await a.enterText(find.byType(TextField).first, 'notifications for conversation summaries every evening');
      await a.shot('Search with a long query', step: 'long');
    },
  ),
  AuditScenario(
    id: 'edge-device-long-name',
    title: 'Device group and Device Settings: long device name, 9% battery, firmware update',
    page: 'lib/pages/settings/device_settings.dart (DeviceSettings)',
    state: 'A connected pendant with a 66-character name, long hardware strings, 9% battery and an update',
    run: (a) async {
      final device = AuditDeviceProvider(connected: true, battery: 9, newFirmware: true, device: _longDevice);
      await a.pump(const DeviceGroupPage(), providers: [ChangeNotifierProvider<DeviceProvider>.value(value: device)]);
      await a.shot('Open Device', step: 'group');
      await a.pump(const DeviceSettings(), providers: [ChangeNotifierProvider<DeviceProvider>.value(value: device)]);
      await a.scrollSeries('Open Device Settings');
    },
  ),
  AuditScenario(
    id: 'edge-usage-free-over-limit',
    title: 'Plan & Usage on the free plan, over every limit, with heavy usage',
    page: 'lib/pages/settings/usage_page.dart (UsagePage)',
    state: 'Basic plan with words, minutes and insights over their limits; tens of millions of words all time',
    run: (a) async {
      a.server.stubs['GET /v1/users/me/subscription'] =
          _subscription(plan: 'basic', wordsUsed: 15230, wordsLimit: 10000);
      await a.pump(const UsagePage(), providers: [ChangeNotifierProvider<UsageProvider>.value(value: _heavyUsage())]);
      await a.scrollSeries('Open Plan & Usage on the free plan', step: 900);
      await a.tap(find.text('All time'));
      await a.shot('Pick All time', step: 'all');
    },
  ),
  AuditScenario(
    id: 'edge-usage-unlimited',
    title: 'Plan & Usage on Unlimited with chat nearly used up',
    page: 'lib/pages/settings/usage_page.dart (UsagePage)',
    state: 'Unlimited plan; chat quota at 92%',
    run: (a) async {
      a.server.stubs['GET /v1/users/me/subscription'] =
          _subscription(plan: 'unlimited', wordsUsed: 1874320, wordsLimit: -1, chat: 0.92);
      await a.pump(const UsagePage(), providers: [ChangeNotifierProvider<UsageProvider>.value(value: _heavyUsage())]);
      await a.scrollSeries('Open Plan & Usage on Unlimited', step: 900);
    },
  ),
  AuditScenario(
    id: 'edge-developer-many-keys',
    title: 'Developer settings with several API and MCP keys',
    page: 'lib/pages/settings/developer.dart (DeveloperSettingsPage)',
    state: 'Four developer keys and three MCP keys, some with long names, one never used',
    run: (a) async {
      a.server.stubs['GET /v1/dev/keys'] = [
        _key('k1', 'Zapier production sync for the whole sales and success organisation', 'omi_dev_a81f',
            lastUsed: '2026-10-01T09:00:00Z'),
        _key('k2', 'Local script', 'omi_dev_09bc'),
        _key('k3', 'n8n', 'omi_dev_77d2', lastUsed: '2026-09-29T09:00:00Z'),
        _key('k4', 'Staging webhook relay (do not delete)', 'omi_dev_4e10', lastUsed: '2026-08-01T09:00:00Z'),
      ];
      a.server.stubs['GET /v1/mcp/keys'] = [
        _key('m1', 'Claude Desktop on the studio iMac upstairs', 'omi_mcp_1f2a', lastUsed: '2026-10-01T09:00:00Z'),
        _key('m2', 'Cursor', 'omi_mcp_88aa'),
        _key('m3', 'Claude Code', 'omi_mcp_c0de', lastUsed: '2026-09-30T09:00:00Z'),
      ];
      await a.pump(const DeveloperSettingsPage());
      await a.scrollSeries('Open Developer settings with keys');
    },
  ),
  AuditScenario(
    id: 'edge-goals-many',
    title: 'Goals: long titles, done, overshot, not started, units',
    page: 'lib/pages/goals/goals_page.dart (GoalsPage)',
    state: 'Six goals mixing long titles, 0%, 100%, over 100%, units and a yes/no goal',
    run: (a) async {
      final goals = GoalsProvider(
          goalsFetcher: () async => [
                _goal('g1', 'Read twelve books this year, including at least three in Portuguese', 4, 12,
                    unit: 'books'),
                _goal('g2', 'Run 100 km', 132, 100, unit: 'km'),
                _goal('g3', 'Meditate', 0, 30, unit: 'days'),
                _goal('g4', 'Ship the redesign', 1, 1, type: 'boolean'),
                _goal('g5', 'Save for the trip', 2450.5, 6000, unit: 'USD'),
                _goal('g6', 'Call mum every Sunday', 7, 8),
              ]);
      await a.tester.runAsync(goals.init);
      await a.pump(const GoalsPage(),
          scaffold: false, providers: [ChangeNotifierProvider<GoalsProvider>.value(value: goals)]);
      await a.scrollSeries('Open Goals with six goals');
    },
  ),
  AuditScenario(
    id: 'edge-goals-empty',
    title: 'Goals with none set',
    page: 'lib/pages/goals/goals_page.dart (GoalsPage)',
    state: 'No goals',
    run: (a) async {
      final goals = GoalsProvider(goalsFetcher: () async => []);
      await a.tester.runAsync(goals.init);
      await a.pump(const GoalsPage(),
          scaffold: false, providers: [ChangeNotifierProvider<GoalsProvider>.value(value: goals)]);
      await a.shot('Open Goals with none');
    },
  ),
  AuditScenario(
    id: 'edge-people-long-names',
    title: 'People with very long names',
    page: 'lib/pages/settings/people.dart (UserPeoplePage)',
    state: 'Three confirmed people with 40–60 character names and one with a two-letter name',
    run: (a) async {
      final people = PeopleProvider(
        setPinned: (_, __) async => true,
        deletePersonById: (_) async => true,
        loadPeople: () async => [
          _person('p1', 'Dr. Alexandria Montgomery-Featherstonehaugh III', 41),
          _person('p2', 'María José Carolina de los Ángeles Fernández', 3),
          _person('p3', 'Bo', 1),
        ],
      );
      await a.pump(const UserPeoplePage(), providers: [ChangeNotifierProvider<PeopleProvider>.value(value: people)]);
      await a.shot('Open People with long names');
    },
  ),
  AuditScenario(
    id: 'edge-people-empty',
    title: 'People with nobody yet',
    page: 'lib/pages/settings/people.dart (UserPeoplePage)',
    state: 'An account that has not named anyone',
    run: (a) async {
      await a.pump(const UserPeoplePage(), providers: [
        ChangeNotifierProvider<PeopleProvider>.value(value: PeopleProvider(loadPeople: () async => const []))
      ]);
      await a.shot('Open People with nobody yet');
    },
  ),
  AuditScenario(
    id: 'edge-integrations-connected',
    title: 'Integrations with three task apps connected',
    page: 'lib/pages/settings/integrations_page.dart (IntegrationsPage)',
    state: 'Todoist (default), Asana and ClickUp connected through the fixture backend',
    run: (a) async {
      a.server.stubs['GET /v1/task-integrations'] = {
        'integrations': {
          'todoist': {'connected': true, 'access_token': 'synthetic'},
          'asana': {'connected': true, 'access_token': 'synthetic', 'user_gid': 'u1'},
          'clickup': {'connected': true, 'access_token': 'synthetic', 'user_id': 'u1'},
        },
        'default_app': 'todoist',
      };
      final tasks = TaskIntegrationProvider();
      await a.tester.runAsync(tasks.loadFromBackend);
      // The services are app-wide singletons: sign them back out for the scenarios after this one.
      addTearDown(() {
        TodoistService().setAuthenticated(false);
        AsanaService().setAuthenticated(false);
        ClickUpService().setAuthenticated(false);
      });
      await a.pump(const IntegrationsPage(), scaffold: false, providers: [
        ChangeNotifierProvider<TaskIntegrationProvider>.value(value: tasks),
        ChangeNotifierProvider<AddAppProvider>(create: (_) => InertAddAppProvider()),
      ]);
      await a.scrollSeries('Open Integrations with three apps connected');
    },
  ),
  AuditScenario(
    id: 'edge-data-protection',
    title: 'Data Protection',
    page: 'lib/pages/settings/data_privacy_page.dart (DataPrivacyPage)',
    state: 'Signed-in fixture account with default protection',
    run: (a) async {
      await a.pump(const DataPrivacyPage());
      await a.scrollSeries('Open Data Protection');
    },
  ),
  AuditScenario(
    id: 'edge-conversation-display',
    title: 'Conversation Display',
    page: 'lib/pages/settings/conversation_display_settings.dart (ConversationDisplaySettings)',
    state: 'Default display settings',
    run: (a) async {
      await a.pump(const ConversationDisplaySettings());
      await a.scrollSeries('Open Conversation Display');
    },
  ),
  AuditScenario(
    id: 'edge-permissions',
    title: 'Permissions',
    page: 'lib/pages/settings/permissions_page.dart (PermissionsPage)',
    state: 'Permission checks answered by the test platform (nothing granted)',
    run: (a) async {
      // permission_handler: every permission reads as denied (0).
      const channel = MethodChannel('flutter.baseflow.com/permissions/methods');
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(channel, (call) async => call.method == 'checkServiceStatus' ? 1 : 0);
      addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
      await a.pump(const PermissionsPage());
      await a.scrollSeries('Open Permissions');
    },
  ),
  AuditScenario(
    id: 'edge-vocabulary',
    title: 'Custom Vocabulary: forty words with long ones, and none',
    page: 'lib/pages/settings/custom_vocabulary_page.dart (CustomVocabularyPage)',
    state: 'Forty words including long product names; then an empty list',
    run: (a) async {
      final words = [
        'Omi',
        'Featherstonehaugh',
        'Kubernetes',
        'PostHog',
        'Supercalifragilisticexpialidocious',
        'Montgomery-Featherstonehaugh',
        'n8n',
        'Lisbon',
        'OKRs',
        'Zapier',
        'GraphQL',
        'Seeed',
        'nRF52840',
        'Deepgram',
        'Parakeet',
        'Whisper',
        'Anthropic',
        'Claude',
        'Firebase',
        'Crashlytics',
        'Figma',
        'Linear',
        'Notion',
        'Asana',
        'ClickUp',
        'Todoist',
        'Maximiliana',
        'Ashwin',
        'Bengaluru',
        'Thiruvananthapuram',
        'Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch',
        'FlutterFlow',
        'Riverpod',
        'OAuth',
        'WebSocket',
        'TestFlight',
        'App Store Connect',
        'Stripe Connect',
        'PayPal',
        'Omi DevKit 2',
      ];
      await a.pump(const CustomVocabularyPage(),
          providers: [ChangeNotifierProvider<UserProvider>.value(value: _VocabularyUser(words))]);
      await a.scrollSeries('Open Custom Vocabulary with forty words');
      await a.pump(const CustomVocabularyPage(),
          providers: [ChangeNotifierProvider<UserProvider>.value(value: _VocabularyUser(const []))]);
      await a.shot('Open Custom Vocabulary with none', step: 'empty');
    },
  ),
  AuditScenario(
    id: 'edge-phone-calls-numbers',
    title: 'Phone Call settings with two verified numbers',
    page: 'lib/pages/settings/phone_call_settings_page.dart (PhoneCallSettingsPage)',
    state: 'A primary number with a long name and an international one without a name',
    run: (a) async {
      _silencePhoneCallEvents();
      await a.pump(const PhoneCallSettingsPage(),
          providers: [ChangeNotifierProvider<PhoneCallProvider>.value(value: _NumbersPhoneCallProvider())]);
      await a.shot('Open Phone Call settings with numbers');
    },
  ),
  AuditScenario(
    id: 'edge-import-history',
    title: 'Import history: running, failed with a long error, done',
    page: 'lib/pages/settings/import_history_page.dart (ImportHistoryPage)',
    state: 'Three import jobs: processing 37 of 1,204 files, failed with a long server error, completed',
    run: (a) async {
      a.server.stubs['GET /v1/import/jobs'] = [
        {
          'job_id': 'j1',
          'status': 'processing',
          'total_files': 1204,
          'processed_files': 37,
          'created_at': '2026-10-01T09:00:00Z'
        },
        {
          'job_id': 'j2',
          'status': 'failed',
          'total_files': 18,
          'processed_files': 3,
          'error': 'The export archive could not be read: the file at lifelogs/2025/12/31/entry-0007.json is not valid '
              'JSON (unexpected end of input at line 1, column 18432). Export again from Limitless and retry.',
          'created_at': '2026-09-20T09:00:00Z'
        },
        {
          'job_id': 'j3',
          'status': 'completed',
          'total_files': 312,
          'processed_files': 312,
          'conversations_created': 298,
          'conversations_skipped': 14,
          'created_at': '2026-09-01T09:00:00Z'
        },
      ];
      await a.pump(const ImportHistoryPage());
      await a.scrollSeries('Open Import history');
    },
  ),
  AuditScenario(
    id: 'edge-payments-connected',
    title: 'Payments with Stripe and PayPal both connected',
    page: 'lib/pages/payments/payments_page.dart (PaymentsPage)',
    state: 'Stripe connected and default; PayPal connected',
    run: (a) async {
      await a.pump(const PaymentsPage(),
          providers: [ChangeNotifierProvider<PaymentMethodProvider>.value(value: _ConnectedPayments())]);
      await a.shot('Open Payments with both connected');
    },
  ),
];

final settingsEdgeScenarios = <AuditScenario>[
  ..._moreEdgeScenarios,
  AuditScenario(
    id: 'edge-offline-sync-every-state',
    title: 'Offline Sync: every recording state, a long sync error, conversations created, storage nearly full',
    page: _autoSync,
    state: 'Twelve recordings covering every sync state; a sync error whose message is a long recovery '
        'instruction; three conversations created; a 3.0.21 pendant at 97% storage',
    run: (a) async {
      final sync = _SyncData(
        _everyWalState(),
        state: const SyncState(
          status: SyncStatus.error,
          errorMessage: 'Your Omi stopped responding while sending recordings. Press the button on your Omi '
              'to stop recording, keep it close to your phone, then sync again.',
        ),
        pointers: _pointers(),
      );
      await a.pump(const AutoSyncPage(), providers: [
        ChangeNotifierProvider<SyncProvider>.value(value: sync),
        ChangeNotifierProvider<DeviceProvider>.value(value: _RingDevice()),
      ]);
      await a.shot('Open Offline Sync with every recording state', step: 'open');
      final list = find.byType(Scrollable).first;
      await a.tester.dragUntilVisible(find.text('All'), list, const Offset(0, -300));
      await a.tap(find.text('All'));
      a.tester.state<ScrollableState>(list).position.jumpTo(0);
      await a.settle();
      await a.scrollSeries('Pick All: every recording, newest first');
    },
  ),
  AuditScenario(
    id: 'edge-offline-sync-uploading',
    title: 'Offline Sync while uploading, with the Manage Storage sheet',
    page: _autoSync,
    state: 'Uploading file 3 of 12; four recordings waiting, two synced',
    run: (a) async {
      final wals = _everyWalState().where((w) => w.status == WalStatus.miss || w.status == WalStatus.synced).toList();
      final sync = _SyncData(
        wals,
        state: const SyncState(
          status: SyncStatus.syncing,
          phase: SyncPhase.uploadingToCloud,
          currentFile: 3,
          totalFiles: 12,
        ),
      );
      await a.pump(const AutoSyncPage(), providers: [ChangeNotifierProvider<SyncProvider>.value(value: sync)]);
      await a.shot('Open Offline Sync while recordings upload', step: 'uploading');
      await a.tap(find.bySemanticsLabel('Manage Storage'));
      await a.shot('Tap Manage Storage', step: 'manage');
    },
  ),
  AuditScenario(
    id: 'edge-offline-sync-ready',
    title: 'Offline Sync with recordings ready to back up',
    page: _autoSync,
    state: 'Three recordings waiting to sync and nothing failed',
    run: (a) async {
      final wals = _everyWalState().where((w) => w.status == WalStatus.miss && w.retryCount == 0 && !w.isSyncing);
      await a.pump(const AutoSyncPage(),
          providers: [ChangeNotifierProvider<SyncProvider>.value(value: _SyncData(wals.toList()))]);
      await a.shot('Open Offline Sync with recordings waiting');
    },
  ),
  AuditScenario(
    id: 'edge-offline-sync-legacy',
    title: 'Offline Sync (older pendants): pending recordings from the phone and the SD card',
    page: 'lib/pages/conversations/sync_page.dart (SyncPage)',
    state: 'The legacy page with every recording state; pending ones come from two sources',
    run: (a) async {
      final sync = _SyncData(_everyWalState(), pointers: _pointers());
      await a.pump(const SyncPage(), providers: [ChangeNotifierProvider<SyncProvider>.value(value: sync)]);
      await a.scrollSeries('Open the legacy Offline Sync page');
    },
  ),
  AuditScenario(
    id: 'edge-synced-conversations',
    title: 'Conversations created by a sync: a long title and an untitled one',
    page: 'lib/pages/conversations/synced_conversations_page.dart (SyncedConversationsPage)',
    state: 'Two new conversations (one with a very long title, one untitled) and one updated',
    run: (a) async {
      final sync = _SyncData(const [], pointers: _pointers());
      await a
          .pump(const SyncedConversationsPage(), providers: [ChangeNotifierProvider<SyncProvider>.value(value: sync)]);
      await a.shot('Tap the conversations-created row');
    },
  ),
];
