part of 'native_ui_host_test.dart';

class _AppFormOwner extends InertAddAppProvider {
  int updates = 0;
  @override
  Future<void> getAppCapabilities() async {
    capabilities = [AppCapability(id: 'chat', title: 'Chat'), AppCapability(id: 'memories', title: 'Memories')];
  }

  @override
  Future<bool> updateApp() async {
    updates++;
    return false;
  }
}

class _StorageOwner extends InertSyncProvider {
  int refreshes = 0;
  @override
  Future<void> refreshWals() async {
    refreshes++;
  }
}

NativeRow _advancedRow(WidgetTester tester, String id) {
  final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
  return [...surface.toolbar, ...surface.sections.expand((s) => s.rows)].singleWhere((row) => row.id == id);
}

Widget _advancedHost(Widget page, {AddAppProvider? owner, SyncProvider? storage}) => MultiProvider(
        providers: [
          ...defaultAuditProviders(),
          if (owner != null) ChangeNotifierProvider<AddAppProvider>.value(value: owner),
          if (storage != null) ChangeNotifierProvider<SyncProvider>.value(value: storage)
        ],
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            theme: buildOmiTheme(brightness: Brightness.dark),
            home: page));

void registerNativeAdvancedHostChecks(Future<void> Function(WidgetTester, String) checkNativeHost) {
  testWidgets('native app editing preserves original validators and does not update before confirmation',
      (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    final owner = _AppFormOwner();
    addTearDown(owner.dispose);
    final app = App.fromJson({
      'id': 'native-owner-fixture',
      'name': 'Fixture app',
      'author': 'Fixture',
      'description': 'A seeded app for UI verification',
      'image': 'https://example.com/logo.png',
      'category': 'productivity',
      'capabilities': ['chat'],
      'chat_prompt': 'Keep the owner',
      'private': true,
      'is_paid': false,
      'price': 0.0,
      'thumbnails': <String>[]
    });
    await primeNetworkImages(tester, [app.image]);
    await tester.pumpWidget(_advancedHost(UpdateAppPage(app: app), owner: owner));
    await checkNativeHost(tester, 'real-native-app-owner-dark');
    expect(owner.formKey.currentState, isNotNull);
    expect(_advancedRow(tester, 'owner_save').enabled, false);
    await _advancedRow(tester, 'owner_name').action!('');
    await tester.pump();
    expect(_advancedRow(tester, 'owner_save').enabled, false);
    await _advancedRow(tester, 'owner_name').action!('Fixture app edited');
    await tester.pump();
    expect(owner.hasChanges, true);
    expect(_advancedRow(tester, 'owner_save').enabled, true);
    expect(owner.validateForm(), true, reason: 'The mounted original form remains the validator');
    expect(owner.updates, 0);
    await _advancedRow(tester, 'owner_name').action!('Fixture app');
    await tester.pump();
    expect(owner.hasChanges, false);
    expect(owner.updates, 0);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('native dated Tasks retain date bounds, paging and the current failure state', (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    final bounds = <({DateTime start, int offset})>[];
    final page = DayTasksPage(
        date: DateTime(2026, 10, 2),
        fetchTasks: ({required startDate, required endDate, limit = 50, offset = 0}) async {
          bounds.add((start: startDate, offset: offset));
          return ApiSuccess(ActionItemsResponse(actionItems: [
            ActionItemWithMetadata(id: 'fixture-$offset', description: 'Task page $offset', completed: false)
          ], hasMore: offset == 0));
        });
    await tester.pumpWidget(_advancedHost(page));
    await checkNativeHost(tester, 'real-native-dated-tasks-dark');
    expect(bounds.single, (start: DateTime(2026, 10, 2), offset: 0));
    await _advancedRow(tester, 'day_tasks_load_more').action!(null);
    await tester.pump();
    expect(bounds.last.offset, 1);
    expect(_advancedRow(tester, 'day_task:fixture-1').title, 'Task page 1');
    await _advancedRow(tester, 'day_previous').action!(null);
    await tester.pump();
    expect(bounds.last, (start: DateTime(2026, 10, 1), offset: 0));
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('native fair-use and storage settings keep their HTTP and preference owners', (tester) async {
    final backend = await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    backend.failNext('GET', '/v1/fair-use/status',
        status: 200,
        body: jsonEncode({
          'stage': 'restrict',
          'speech_hours_today': 1.5,
          'speech_hours_3day': 2.0,
          'speech_hours_weekly': 3.0,
          'message': 'Synthetic status',
          'usage_pct': {'daily': 75.0, 'three_day': 25.0, 'weekly': 30.0},
          'limits': {'daily_hours': 2.0, 'three_day_hours': 8.0, 'weekly_hours': 10.0},
          'case_ref': 'synthetic-case',
          'dg_budget': {'daily_limit_ms': 60000, 'used_ms': 30000, 'remaining_ms': 30000, 'exhausted': false}
        }));
    await tester.pumpWidget(_advancedHost(const FairUsePage()));
    await checkNativeHost(tester, 'real-native-fair-use-dark');
    expect(backend.countOf('GET', '/v1/fair-use/status'), 1);
    expect(_advancedRow(tester, 'fair_use_daily').value, 75.0);
    expect(_advancedRow(tester, 'fair_use_budget').value, 50.0);
    backend.failNext('GET', '/v1/fair-use/status', status: 500);
    await tester.widget<IosNativeSurface>(find.byType(IosNativeSurface)).onRefresh!(null);
    await tester.pump();
    expect(tester.widget<IosNativeSurface>(find.byType(IosNativeSurface)).failed, true);
    final storage = _StorageOwner();
    addTearDown(storage.dispose);
    SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
    await tester.pumpWidget(_advancedHost(const LocalStoragePage(), storage: storage));
    await checkNativeHost(tester, 'real-native-local-storage-dark');
    await _advancedRow(tester, 'local_storage_enabled').action!(false);
    await tester.pump();
    expect(SharedPreferencesUtil().unlimitedLocalStorageEnabled, false);
    expect(storage.refreshes, 1);
    await tester.pumpWidget(_advancedHost(const PrivateCloudSyncPage()));
    await checkNativeHost(tester, 'real-native-cloud-storage-dark');
    expect(_advancedRow(tester, 'cloud_storage_enabled').value, false);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
  testWidgets('native developer URLs stay unsaved until Save and filters retain their selections', (tester) async {
    final backend = await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    await tester.pumpWidget(_advancedHost(const DeveloperSettingsPage()));
    await checkNativeHost(tester, 'real-native-developer-dark');
    final owner = tester.element(find.byType(IosNativeSurface)).read<DeveloperModeProvider>();
    owner.conversationEventsToggled = true;
    owner.notifyListeners();
    await tester.pump();
    await _advancedRow(tester, 'developer_conversation:url').action!('https://example.com/fixture');
    await tester.pump();
    expect(owner.hasUnsavedWebhookChanges, true);
    expect(_advancedRow(tester, 'developer_save').enabled, true);
    expect(backend.countOf('POST', '/v1/users/developer/webhook/memory_created'), 0);
    owner.discardWebhookChanges();
    await tester.pump();
    expect(owner.webhookOnConversationCreated.text, '');
    expect(owner.hasUnsavedWebhookChanges, false);
    await tester.pumpWidget(_advancedHost(const Scaffold(body: FilterBottomSheet())));
    await checkNativeHost(tester, 'real-native-app-filters-dark');
    final catalog = tester.element(find.byType(IosNativeSurface)).read<AppProvider>();
    await _advancedRow(tester, 'app_filter_sort:A-Z').action!(true);
    await tester.pump();
    expect(catalog.isFilterSelected('A-Z', 'Sort'), true);
    expect(_advancedRow(tester, 'app_filter_sort:A-Z').value, true);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('native export Cancel aborts the existing download and cleans its temporary directory', (tester) async {
    await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
    addTearDown(JourneyHermeticBoot.stop);
    final started = Completer<void>();
    final finished = Completer<void>();
    var cleanupCount = 0;
    var exported = false;
    final directory = await Directory.systemTemp.createTemp('native-export-fixture-');
    await tester.pumpWidget(_advancedHost(Scaffold(
        body: Builder(
            builder: (context) => TextButton(
                key: const Key('start_native_export'),
                child: const Text('Synthetic export'),
                onPressed: () {
                  unawaited(DataExport.run(context,
                      exportDirectory: () async => directory,
                      cleanupDirectory: (value) async {
                        cleanupCount++;
                        if (value != null && await value.exists()) await value.delete(recursive: true);
                      },
                      sweepStaleExports: (_) async => 0,
                      onExported: () => exported = true,
                      download: (path, {onProgress, abortTrigger, authorizationSnapshot}) async {
                        onProgress?.call(4096);
                        started.complete();
                        await abortTrigger;
                        return null;
                      }).whenComplete(finished.complete));
                })))));
    await tester.tap(find.byKey(const Key('start_native_export')));
    await tester.pump();
    await checkNativeHost(tester, 'real-native-export-progress-dark');
    await started.future.timeout(const Duration(seconds: 10));
    expect(_advancedRow(tester, 'export_bytes').title, contains('4'));
    await _advancedRow(tester, 'export_cancel').action!(null);
    for (var i = 0; i < 20 && !finished.isCompleted; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    await finished.future.timeout(const Duration(seconds: 10));
    expect(DataExport.exportInProgress.value, false);
    expect(await directory.exists(), false);
    expect(cleanupCount, 1);
    expect(exported, false);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}
