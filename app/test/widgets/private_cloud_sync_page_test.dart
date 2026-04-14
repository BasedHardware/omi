import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/private_cloud_sync_page.dart';
import 'package:omi/providers/user_provider.dart';

class _StubUserProvider extends UserProvider {
  _StubUserProvider({required this.enabled, this.loading = false});

  final bool enabled;
  final bool loading;

  @override
  bool get privateCloudSyncEnabled => enabled;

  @override
  bool get isLoading => loading;
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<void> _pumpPage(
    WidgetTester tester,
    UserProvider userProvider, {
    Future<List<CloudAudioConversation>> Function()? loadCloudAudioConversations,
    Future<bool> Function()? deleteAllCloudAudioOverride,
    Future<bool?> Function(BuildContext context)? confirmDeleteOverride,
  }) async {
    await tester.pumpWidget(
      ChangeNotifierProvider<UserProvider>.value(
        value: userProvider,
        child: MaterialApp(
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: PrivateCloudSyncPage(
            loadCloudAudioConversations: loadCloudAudioConversations ?? getCloudAudioConversations,
            deleteAllCloudAudio: deleteAllCloudAudioOverride ?? deleteAllCloudAudio,
            confirmDeleteOverride: confirmDeleteOverride,
          ),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('keeps delete-all action visible when cloud sync is enabled and list is empty', (tester) async {
    final userProvider = _StubUserProvider(enabled: true);
    addTearDown(userProvider.dispose);

    await _pumpPage(tester, userProvider);

    final context = tester.element(find.byType(PrivateCloudSyncPage));
    final l10n = AppLocalizations.of(context);

    expect(find.text(l10n.deleteAllAudio), findsOneWidget);
    expect(find.text(l10n.noCloudAudioFiles), findsOneWidget);
  });

  testWidgets('ignores stale cloud-audio fetches after delete all succeeds', (tester) async {
    final userProvider = _StubUserProvider(enabled: true);
    final loadCompleter = Completer<List<CloudAudioConversation>>();
    addTearDown(userProvider.dispose);

    await _pumpPage(
      tester,
      userProvider,
      loadCloudAudioConversations: () => loadCompleter.future,
      deleteAllCloudAudioOverride: () async => true,
      confirmDeleteOverride: (_) async => true,
    );

    final context = tester.element(find.byType(PrivateCloudSyncPage));
    final l10n = AppLocalizations.of(context);

    await tester.tap(find.text(l10n.deleteAllAudio));
    await tester.pump();
    await tester.pump();

    loadCompleter.complete([
      CloudAudioConversation(
        id: 'conv-1',
        title: 'Phantom conversation',
        audioFileCount: 1,
        totalDuration: 42,
      ),
    ]);
    await tester.pump();
    await tester.pump();

    expect(find.text('Phantom conversation'), findsNothing);
    expect(find.text(l10n.noCloudAudioFiles), findsOneWidget);
  });
}
