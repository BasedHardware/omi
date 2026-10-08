part of 'native_ui_host_test.dart';

class _OfflineOwner extends InertSyncProvider {
  SyncState state = const SyncState();
  int retries = 0;
  @override
  SyncState get syncState => state;
  void change(SyncState value) {
    state = value;
    notifyListeners();
  }

  @override
  Future<void> retrySync() async {
    retries++;
  }
}

void registerNativeRemainingHostChecks(Future<void> Function(WidgetTester, String) checkNativeHost) {
  testWidgets('native usage keeps the existing period and timezone owner and captures only a live view',
      (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    final now = DateTime(2026, 10, 4, 12);
    final owner = UsageProvider(deviceTimeZone: () async => 'Asia/Kolkata', now: () => now);
    addTearDown(owner.dispose);
    // The seeded page intentionally skips its fetch lifecycle; resolve the existing
    // timezone owner explicitly before supplying the calendar-scoped fixture.
    await owner.refreshUsageTimeZone();
    final stats = UsageStats(
        transcriptionSeconds: 3600, speechSeconds: 3500, wordsTranscribed: 800, insightsGained: 8, memoriesCreated: 4);
    final history = [
      UsageHistoryPoint(
          date: '2026-10-04',
          transcriptionSeconds: 3600,
          speechSeconds: 3500,
          wordsTranscribed: 800,
          insightsGained: 8,
          memoriesCreated: 4)
    ];
    for (final period in ['today', 'monthly', 'yearly', 'all_time']) {
      owner.debugSetUsage(period, stats, history);
    }
    await tester.pumpWidget(MultiProvider(
        providers: [...defaultAuditProviders(), ChangeNotifierProvider<UsageProvider>.value(value: owner)],
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            theme: buildOmiTheme(brightness: Brightness.dark),
            home: UsagePage(debugSkipFetch: true, debugNow: now))));
    await checkNativeHost(tester, 'real-native-detailed-usage-dark');
    expect(_advancedRow(tester, 'usage_words').subtitle, '800');
    await _advancedRow(tester, 'usage_period_choice').action!('1');
    await tester.pump(const Duration(milliseconds: 400));
    await Future<void>.delayed(const Duration(milliseconds: 200));
    await tester.pump();
    expect(_advancedRow(tester, 'usage_period_choice').value, '1');
    expect(owner.usageTimeZone, 'Asia/Kolkata');
    await _advancedRow(tester, 'usage_metric').action!('minutes');
    await tester.pump();
    expect(_advancedRow(tester, 'usage_chart').points.map((p) => p['y']).reduce((a, b) => (a as num) + (b as num)), 60);
    final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
    final bytes = await surface.controller!.captureImage();
    expect(bytes, isNotNull);
    expect(bytes!.take(8), [137, 80, 78, 71, 13, 10, 26, 10]);
    final id = nativeViewId(tester, find.byType(UiKitView));
    await MethodChannel('com.omi.native_ui/surface/$id').invokeMethod<void>('invalidate');
    expect(await surface.controller!.captureImage(), isNull);
    await tester.pumpWidget(const SizedBox());
    expect(await surface.controller!.captureImage(), isNull);
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('native import status reads through the existing HTTP owner without importing or deleting',
      (tester) async {
    final backend = await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    backend.failNext('GET', '/v1/import/jobs',
        status: 200,
        body: jsonEncode([
          {
            'job_id': 'fixture-import',
            'status': 'completed',
            'total_files': 5,
            'processed_files': 5,
            'conversations_created': 3,
            'conversations_skipped': 2,
            'created_at': '2026-10-04T05:00:00Z'
          }
        ]));
    await tester.pumpWidget(_advancedHost(const ImportHistoryPage()));
    await checkNativeHost(tester, 'real-native-import-history-dark');
    expect(backend.countOf('GET', '/v1/import/jobs'), 1);
    expect(_advancedRow(tester, 'import_job:fixture-import').title, 'Completed');
    expect(_advancedRow(tester, 'import_job:fixture-import').subtitle, contains('3 conversations'));
    expect(backend.countOf('POST', '/v1/import/limitless'), 0);
    expect(backend.countOf('DELETE', '/v1/import/limitless'), 0);
    await _advancedRow(tester, 'import_refresh').action!(null);
    await tester.pump();
    expect(backend.countOf('GET', '/v1/import/jobs'), 2);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('native transcription omits saved keys until explicit reveal and retains draft clearing', (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    const key = 'synthetic-stt-secret';
    await SharedPreferencesUtil().saveCustomSttConfig(const CustomSttConfig(provider: SttProvider.openai, apiKey: key));
    await tester.pumpWidget(_advancedHost(const TranscriptionSettingsPage()));
    await checkNativeHost(tester, 'real-native-transcription-provider-dark');
    IosNativeSurface surface() => tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
    String projection() => jsonEncode(surface().sections.map((s) => s.projection).toList());
    expect(projection(), isNot(contains(key)));
    final input = surface().sections.expand((s) => s.rows).singleWhere((r) => r.keyboard == 'password');
    expect(input.value, '');
    await _advancedRow(tester, 'stt_api_key_visibility').action!(null);
    await tester.pump();
    expect(_advancedRow(tester, 'stt_api_key_revealed').subtitle, key);
    await _advancedRow(tester, 'stt_api_key_visibility').action!(null);
    await tester.pump();
    expect(projection(), isNot(contains(key)));
    await input.action!('replacement-draft');
    await tester.pump();
    expect(SharedPreferencesUtil().customSttConfig.apiKey, key,
        reason: 'Editing never replaces the active saved config');
    await _advancedRow(tester, 'stt_api_key_clear').action!(null);
    await tester.pump();
    expect(surface().sections.expand((s) => s.rows).where((r) => r.id == 'stt_api_key_visibility'), isEmpty);
    expect(SharedPreferencesUtil().customSttConfig.apiKey, key);
    expect(surface().sections.expand((s) => s.rows).singleWhere((r) => r.keyboard == 'password').id, isNot(input.id));
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('native large JSON retains explicit validation', (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    await tester.pumpWidget(_advancedHost(TranscriptionJsonEditorPage(
        title: 'Request configuration',
        initialJson: jsonEncode({'fixture': 'x' * 15000}),
        provider: SttProvider.custom,
        onReset: () => {'fixture': 'reset'})));
    await checkNativeHost(tester, 'real-native-large-json-dark');
    expect(_advancedRow(tester, 'json_text').valid, true);
    expect(_advancedRow(tester, 'json_text').maximumLength, 262144);
    await _advancedRow(tester, 'json_text').action!('{');
    await tester.pump();
    expect(_advancedRow(tester, 'json_save').enabled, false);
    await _advancedRow(tester, 'json_text').action!('{}');
    await tester.pump();
    expect(_advancedRow(tester, 'json_save').enabled, true);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('native offline sync reuses status priority, retry and retention owners', (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    final owner = _OfflineOwner();
    addTearDown(owner.dispose);
    await tester.pumpWidget(_advancedHost(const AutoSyncPage(), storage: owner));
    await checkNativeHost(tester, 'real-native-offline-sync-dark');
    expect(_advancedRow(tester, 'offline_status_title').title,
        AppLocalizations.of(tester.element(find.byType(IosNativeSurface))).syncCardAllBackedUp);
    expect(owner.retries, 0);
    owner.change(const SyncState(
        status: SyncStatus.syncing, phase: SyncPhase.downloadingFromDevice, progress: .5, speedKBps: 8));
    await tester.pump();
    expect(_advancedRow(tester, 'offline_download').value, .5);
    expect(_advancedRow(tester, 'offline_download').title, contains('8.0'));
    owner.change(const SyncState(status: SyncStatus.error, errorMessage: 'Fixture failed'));
    await tester.pump();
    await _advancedRow(tester, 'offline_retry').action!(null);
    expect(owner.retries, 1);
    await _advancedRow(tester, 'offline_retention').action!(false);
    await tester.pump();
    expect(SharedPreferencesUtil().autoRemoveSyncedCopies, false);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}
