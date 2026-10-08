import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/home/home_content.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/local_segment_store.dart';

import 'native_test_host.dart';

const _classicHome = 'classic flutter home';

class _InertRecordings extends ChangeNotifier implements LocalRecordingsProvider {
  @override
  List<LocalRecording> get recordings => const [];

  @override
  Future<void> refresh() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _InertDevice extends ChangeNotifier implements DeviceProvider {
  @override
  bool get havingNewFirmware => false;

  @override
  BtDevice? get pairedDevice => null;

  @override
  bool get isConnected => false;

  @override
  BtDevice? get connectedDevice => null;

  @override
  bool get isConnecting => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _InertCalls extends ChangeNotifier implements PhoneCallProvider {
  @override
  PhoneCallState get callState => PhoneCallState.idle;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<({List<DailySummary> items, bool ok})> _noRecaps() async => (items: const <DailySummary>[], ok: true);

/// The Home owners with no I/O behind them, around [home], with [conversations] already loaded.
Widget _app(Widget home, {List<ServerConversation> conversations = const []}) =>
    NativeTestHost.app(MultiProvider(providers: [
      ChangeNotifierProvider(
          create: (_) => ConversationProvider(isSignedIn: () => true)
            ..conversations = [...conversations]
            ..groupConversationsByDate()),
      ChangeNotifierProvider<LocalRecordingsProvider>(create: (_) => _InertRecordings()),
      ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
      ChangeNotifierProvider(create: (_) => HomeProvider()),
      ChangeNotifierProvider<DeviceProvider>(create: (_) => _InertDevice()),
      ChangeNotifierProvider<PhoneCallProvider>(create: (_) => _InertCalls()),
      ChangeNotifierProvider(
          create: (_) => CaptureProvider(
              externalActions: const NoopCaptureExternalActions(),
              inProgressConversationLoader: () async {},
              localSegmentStore: LocalSegmentStore.disabled())),
      ChangeNotifierProvider(
          create: (_) => SpeakerTagPromptsProvider(
              fetchPrompts: () async => const ApiSuccess(GeneratedSpeakerTagPromptsResponse()))),
    ], child: Scaffold(body: home)));

/// A Home inside the native shell: the shell's spinner is its fallback until [onRejected] restores
/// the classic shell, so the test's fallback names what the shell would show.
Widget _home({VoidCallback? onRejected, Key? key}) => IosNativeHome(
    key: key,
    requestInitialLoad: false,
    loadRecaps: _noRecaps,
    fallback: const Text(_classicHome),
    onRejected: onRejected);

Future<Object?> _refuseUpdates(int viewId, MethodCall call) async {
  if (call.method == 'update') throw PlatformException(code: 'invalid_native_snapshot');
  return null;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a Home snapshot Swift refuses renders the fallback, invalidates and reports it once', (tester) async {
    final host = NativeTestHost.install(answer: _refuseUpdates);
    var rejections = 0;
    await tester.pumpWidget(_app(_home(onRejected: () => rejections++)));
    await NativeTestHost.settle(tester);
    expect(find.text(_classicHome), findsOneWidget);
    expect(find.byType(UiKitView), findsNothing);
    final view = host.created.single;
    expect(host.methodsOf(view), ['update', 'invalidate']);
    expect(rejections, 1);

    // Later rebuilds keep the fallback and never report or retry again.
    await tester.pumpWidget(_app(_home(onRejected: () => rejections++)));
    await NativeTestHost.settle(tester);
    expect(find.text(_classicHome), findsOneWidget);
    expect(host.created, [view]);
    expect(rejections, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a current Home view without a handler renders the fallback and reports it', (tester) async {
    final host = NativeTestHost.install(answer: (_, call) async {
      if (call.method == 'update') throw MissingPluginException();
      return null;
    });
    var rejections = 0;
    await tester.pumpWidget(_app(_home(onRejected: () => rejections++)));
    await NativeTestHost.settle(tester);
    expect(find.text(_classicHome), findsOneWidget);
    expect(find.byType(UiKitView), findsNothing);
    expect(host.methodsOf(host.created.single), ['update', 'invalidate']);
    expect(rejections, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a replaced Home view losing its handler does not reject the current one', (tester) async {
    final firstUpdate = Completer<void>();
    late final NativeTestHost host;
    host = NativeTestHost.install(answer: (viewId, call) async {
      if (viewId == host.created.first && call.method == 'update') {
        await firstUpdate.future;
        throw MissingPluginException();
      }
      return null;
    });
    var rejections = 0;
    final key = GlobalKey<IosNativeHomeState>();
    await tester.pumpWidget(_app(_home(key: key, onRejected: () => rejections++)));
    await NativeTestHost.settle(tester);
    final first = host.created.single;

    // Scrolling to the top replaces the platform view under the same State.
    key.currentState!.scrollToTop();
    await NativeTestHost.settle(tester);
    expect(host.created, hasLength(2));
    expect(host.disposed, [first]);
    firstUpdate.complete();
    await NativeTestHost.settle(tester);
    expect(find.byType(UiKitView), findsOneWidget);
    expect(find.text(_classicHome), findsNothing);
    expect(host.methodsOf(host.created.last), contains('update'));
    expect(host.methodsOf(host.created.last), isNot(contains('invalidate')));
    expect(rejections, 0);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a Home remounted in a route that refused one starts on the fallback and reports it', (tester) async {
    final host = NativeTestHost.install(answer: _refuseUpdates);
    var mounted = true;
    var rejections = 0;
    late StateSetter swap;
    await tester.pumpWidget(_app(StatefulBuilder(builder: (context, setState) {
      swap = setState;
      return mounted ? _home(onRejected: () => rejections++) : const Text('another tab');
    })));
    await NativeTestHost.settle(tester);
    expect(rejections, 1);

    host.answer = (_, __) async => null;
    swap(() => mounted = false);
    await NativeTestHost.settle(tester);
    swap(() => mounted = true);
    await tester.pump();
    expect(find.text(_classicHome), findsOneWidget, reason: 'A new State starts on the fallback');
    expect(rejections, 2, reason: 'Its owner hears of it after that first frame');
    await NativeTestHost.settle(tester);
    expect(rejections, 2);
    expect(host.created, hasLength(1), reason: 'No native view is created for the refused Home again');
    expect(find.byType(UiKitView), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('HomeContentPage falls back to its classic conversation list after a rejection', (tester) async {
    final host = NativeTestHost.install(answer: _refuseUpdates);
    final page = GlobalKey<HomeContentPageState>();
    final conversations = [
      for (var index = 0; index < 30; index++)
        ServerConversation(
            id: 'home-$index',
            createdAt: DateTime.utc(2026, 10, 4, 10).subtract(Duration(minutes: index)),
            status: ConversationStatus.completed,
            structured: Structured('Conversation $index', 'Overview'))
    ];
    await tester.pumpWidget(_app(HomeContentPage(key: page, requestInitialLoad: false, loadRecaps: _noRecaps),
        conversations: conversations));
    await NativeTestHost.settle(tester);
    expect(find.byType(ConversationsPage), findsOneWidget);
    expect(find.byType(UiKitView), findsNothing);
    expect(host.methodsOf(host.created.single), ['update', 'invalidate']);

    // Scrolling to the top reaches the classic list that replaced the native Home, not the rejected
    // native State, whose rebuild would only show the same fallback again.
    final list = find.descendant(of: find.byType(ConversationsPage), matching: find.byType(Scrollable)).first;
    await tester.drag(find.byType(ConversationsPage), const Offset(0, -600));
    await tester.pumpAndSettle();
    expect(tester.state<ScrollableState>(list).position.pixels, greaterThan(0));
    page.currentState!.scrollToTop();
    await tester.pumpAndSettle();
    expect(tester.state<ScrollableState>(list).position.pixels, 0);
    expect(host.created, hasLength(1));
    expect(tester.takeException(), isNull);
  });
}
