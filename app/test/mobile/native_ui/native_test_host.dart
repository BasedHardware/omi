import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

/// Answers one call on a native view's channel. Throw a [PlatformException] to report an error, or
/// a [MissingPluginException] to behave like a view whose handler is gone.
typedef NativeViewAnswer = Future<Object?> Function(int viewId, MethodCall call);

/// A hermetic stand-in for the iOS host. The debug seam enables native presentation, the account is
/// a synthetic signed-in owner, and UiKitView creation and disposal are answered locally: each view
/// gets a mocked `<viewType>/<id>` channel that lives until the view is disposed.
class NativeTestHost {
  NativeTestHost._(this.answer);

  /// Replaceable mid-test, for example to stop refusing snapshots.
  NativeViewAnswer answer;
  final created = <int>[];
  final disposed = <int>[];
  final calls = <(int, MethodCall)>[];
  final _channels = <int, MethodChannel>{};

  static TestDefaultBinaryMessenger get _messenger => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  Iterable<String> methodsOf(int viewId) => calls.where((call) => call.$1 == viewId).map((call) => call.$2.method);

  /// Delivers a call from the native view to its Dart handler; null means no handler answered.
  Future<ByteData?> sendFromNative(int viewId, MethodCall call) async {
    final channel = _channels[viewId]!;
    ByteData? reply;
    await _messenger.handlePlatformMessage(channel.name, channel.codec.encodeMethodCall(call), (data) => reply = data);
    return reply;
  }

  /// Signs in the synthetic owner without enabling the debug host, for tests of the real platform
  /// gates. The previous token gateway is put back when the test ends.
  static void installOwner() {
    final previous = AuthService.installLocalHarnessTokenGateway(const _SignedInOwner());
    addTearDown(() => AuthService.installLocalHarnessTokenGateway(previous));
    // The first snapshot of a new owner advances the session generation; settle it before mounting.
    AuthService.instance.captureSessionSnapshot();
  }

  /// Installs the host for the current test; everything is removed when the test ends.
  static NativeTestHost install({NativeViewAnswer? answer}) {
    final host = NativeTestHost._(answer ?? (_, __) async => null);
    IosNativeSurface.debugNativeHostForTest = true;
    installOwner();
    _messenger.setMockMethodCallHandler(SystemChannels.platform_views, (call) async {
      switch (call.method) {
        case 'create':
          final arguments = call.arguments as Map;
          final id = arguments['id'] as int;
          final channel = MethodChannel('${arguments['viewType']}/$id');
          host.created.add(id);
          host._channels[id] = channel;
          _messenger.setMockMethodCallHandler(channel, (call) {
            host.calls.add((id, call));
            return host.answer(id, call);
          });
        case 'dispose':
          final id = call.arguments as int;
          host.disposed.add(id);
          final channel = host._channels[id];
          if (channel != null) _messenger.setMockMethodCallHandler(channel, null);
      }
      return null;
    });
    addTearDown(() {
      IosNativeSurface.debugNativeHostForTest = false;
      _messenger.setMockMethodCallHandler(SystemChannels.platform_views, null);
      for (final channel in host._channels.values) {
        _messenger.setMockMethodCallHandler(channel, null);
      }
    });
    return host;
  }

  /// A localized app with the appearance owner that every snapshot reads.
  static Widget app(Widget home) => ChangeNotifierProvider(
      create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {}),
      child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: home));

  /// Lets the support check, the view creation and the first post-frame publish complete.
  static Future<void> settle(WidgetTester tester) async {
    for (var frame = 0; frame < 5; frame++) {
      await tester.pump();
    }
  }
}

final class _SignedInOwner implements AuthTokenGateway {
  const _SignedInOwner();

  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'native-test-owner');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {}
}
