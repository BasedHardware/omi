// Inert providers and fixtures for the pre-ui-program suite: the current suite's fakes.dart without
// what these revisions lack (capture groups, speaker tag prompts). Each stands in for a provider
// whose real constructor reaches BLE, audio, platform channels or an un-injectable HTTP call.
import 'dart:ui' as ui;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/foundation.dart' show ChangeNotifier, SynchronousFuture;
import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/locale_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/services/wals/wal.dart';

/// A provider for every type a registered page reads, so any page pumps without a
/// ProviderNotFoundException. A scenario seeds state by passing its own provider of the same type.
List<SingleChildWidget> defaultAuditProviders() => [
      ChangeNotifierProvider(create: (_) => MessageProvider()),
      ChangeNotifierProvider(
          create: (_) => ActionItemsProvider(
                getActionItems: (
                        {limit = 100,
                        offset = 0,
                        completed,
                        conversationId,
                        startDate,
                        endDate,
                        dueStartDate,
                        dueEndDate}) async =>
                    const ActionItemsResponse(actionItems: []),
                deleteActionItemRequest: (_) async => true,
                updateActionItemRequest: (id, {description, completed, dueAt}) async => null,
              )),
      ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
      ChangeNotifierProvider(create: (_) => AppProvider()),
      ChangeNotifierProvider(create: (_) => ConversationProvider(isSignedIn: () => true)),
      ChangeNotifierProvider(create: (_) => HomeProvider()),
      ChangeNotifierProvider(create: (_) => IntegrationProvider()),
      ChangeNotifierProvider(create: (_) => FolderProvider()),
      ChangeNotifierProvider(create: (_) => UsageProvider()),
      ChangeNotifierProvider(create: (_) => VoiceRecorderProvider()),
      ChangeNotifierProvider(
          create: (_) => MemoriesProvider(
                fetchMemoriesRequest: ({limit = 100, offset = 0, thisDeviceOnly = false}) async =>
                    const GetMemoriesResult([], true),
              )),
      ChangeNotifierProvider(create: (_) => GoalsProvider()),
      ChangeNotifierProvider<TaskIntegrationProvider>(create: (_) => LoadedTaskIntegrationProvider()),
      ChangeNotifierProvider<DeviceProvider>(create: (_) => AuditDeviceProvider()),
      ChangeNotifierProvider(create: (_) => CaptureProvider()),
      ChangeNotifierProvider(create: (_) => UserProvider()),
      ChangeNotifierProvider(create: (_) => LocaleProvider()),
      ChangeNotifierProvider<PhoneCallProvider>(create: (_) => InertPhoneCallProvider()),
      ChangeNotifierProvider<LocalRecordingsProvider>(create: (_) => InertLocalRecordingsProvider()),
      ChangeNotifierProvider<SyncProvider>(create: (_) => InertSyncProvider()),
      ChangeNotifierProvider(create: (_) => PeopleProvider(loadPeople: () async => const [])),
      ChangeNotifierProvider(create: (_) => OnboardingProvider()),
      ChangeNotifierProvider(create: (_) => McpProvider()),
      ChangeNotifierProvider<PaymentMethodProvider>(create: (_) => InertPaymentMethodProvider()),
      ChangeNotifierProvider(create: (_) => AuthenticationProvider(initializeListeners: false)),
    ];

/// A device provider with no BLE behind it.
class AuditDeviceProvider extends ChangeNotifier implements DeviceProvider {
  AuditDeviceProvider(
      {this.connected = false, this.battery = 0, this.charging = false, this.newFirmware = false, this.device});
  final bool connected;
  final int battery;
  final bool charging;
  final bool newFirmware;
  final BtDevice? device;

  @override
  bool get isConnected => connected;
  @override
  BtDevice? get connectedDevice => connected ? device : null;
  @override
  BtDevice? get pairedDevice => device;
  @override
  int get batteryLevel => battery;
  @override
  bool get isCharging => charging;
  @override
  bool get havingNewFirmware => newFirmware;
  @override
  String get latestStableFirmwareVersion => '';
  @override
  String get currentFirmwareVersion => 'Unknown';
  @override
  Future<void> getDeviceInfo() async {}
  @override
  Future<void> refreshRingStorageStatus() async {}
  @override
  bool get isDeviceStorageSupport => false;
  @override
  bool get isConnecting => false;
  @override
  void setIsConnected(bool value) {}
  @override
  Future<void> initiateConnection(String source, {bool boundDeviceOnly = false}) async {}
  @override
  void setOnFirmwareUpdatePage(bool value) {}
  @override
  void resetFirmwareUpdateState() {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class InertSyncProvider extends ChangeNotifier implements SyncProvider {
  @override
  SyncState get syncState => const SyncState();
  @override
  List<Wal> get allWals => const [];
  @override
  List<Wal> get pendingLocalTranscriptionWals => const [];
  @override
  List<Wal> walsForDisplayFilter(WalDisplayFilter filter) => const [];
  @override
  Future<void> discoverDeviceWals({String? firmwareVersion}) async {}
  @override
  int get clearableWalsCount => 0;
  @override
  int get missingWalsInSeconds => 0;
  @override
  int get needsAttentionWalsCount => 0;
  @override
  bool get isSyncing => false;
  @override
  bool get syncCompleted => false;
  @override
  List<SyncedConversationPointer> get syncedConversationsPointers => const [];
  @override
  List<Wal> get uploadedWals => const [];
  @override
  List<Wal> get displaySortedWals => const [];
  @override
  bool get isRateLimited => false;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class InertLocalRecordingsProvider extends ChangeNotifier implements LocalRecordingsProvider {
  @override
  List<LocalRecording> get recordings => const [];
  @override
  Future<void> refresh() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class InertPhoneCallProvider extends ChangeNotifier implements PhoneCallProvider {
  @override
  PhoneCallState get callState => PhoneCallState.idle;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class LoadedTaskIntegrationProvider extends TaskIntegrationProvider {
  @override
  bool get hasLoaded => true;
}

/// AddAppProvider's catalog calls have no injectable fetcher; keep its default empty catalog.
class InertAddAppProvider extends AddAppProvider {
  InertAddAppProvider()
      : super(listApiKeysServerFn: (_) async => const [], deleteApiKeyServerFn: (_, __) async => true);
  @override
  Future<void> getCategories() async {
    // mapCategoryIdToName() has no orElse; an empty list throws as soon as a category is shown.
    categories = [Category(title: 'Productivity', id: 'productivity')];
  }

  @override
  Future<void> getAppCapabilities() async {}
  @override
  Future<void> getPaymentPlans() async {}
}

/// PaymentMethodProvider's calls have no injectable fetcher; keep its not-connected default.
class InertPaymentMethodProvider extends PaymentMethodProvider {
  @override
  Future getPaymentMethodsStatus() async {}
  @override
  Future getSupportedCountries() async {}
  @override
  Future<String?> connectStripe() async => null;
}

/// A completed synthetic conversation from 2026-09-20 10:00 local.
ServerConversation auditConversation(
  String id, {
  String title = 'Standup notes',
  bool discarded = false,
  List<TranscriptSegment> segments = const [],
}) {
  return ServerConversation(
    id: id,
    createdAt: DateTime(2026, 9, 20, 10),
    structured: Structured(title, 'We agreed to simplify the recording flow and ship the revised notes Friday.',
        emoji: '\u{1F4AC}', category: 'work'),
    status: ConversationStatus.completed,
    discarded: discarded,
    transcriptSegments: segments,
  );
}

/// Fills Flutter's image cache with a flat tile for each of [urls], so CachedNetworkImage renders
/// without reaching flutter_cache_manager (whose sqflite and path_provider plugins have no test
/// implementation) or the network.
Future<void> primeNetworkImages(WidgetTester tester, Iterable<String> urls) async {
  final tile = await tester.runAsync(() {
    final recorder = ui.PictureRecorder();
    Canvas(recorder).drawRect(const Rect.fromLTWH(0, 0, 8, 8), Paint()..color = const Color(0xFF5B5B66));
    return recorder.endRecording().toImage(8, 8);
  });
  for (final url in urls) {
    PaintingBinding.instance.imageCache.putIfAbsent(CachedNetworkImageProvider(url),
        () => OneFrameImageStreamCompleter(SynchronousFuture(ImageInfo(image: tile!.clone()))));
  }
}
