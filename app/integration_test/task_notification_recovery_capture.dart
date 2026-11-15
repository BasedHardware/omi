// Local integration target: production UI/providers/HTTP/auth fencing, synthetic
// Firebase/APNs/EventKit/provider I/O only. Never connects to customer accounts.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api/notifications.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/widgets/task_selection_action_bar.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/integrations/automatic_apple_reminders_export.dart';
import 'package:omi/services/notifications/fcm_token_registration.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _Gateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot get currentUser => const AuthUserSnapshot(uid: 'synthetic-caelis', email: 'fixture@local.test');
  @override
  Future<RefreshedAuthToken?> forceRefresh() async =>
      RefreshedAuthToken(token: 'synthetic-only', expirationTime: DateTime.now().add(const Duration(hours: 1)));
  @override
  Future<void> signOut() async {}
}

Future<void> main() async {
  MarionetteBinding.ensureInitialized();
  SharedPreferences.setMockInitialValues({'uid': 'synthetic-caelis'});
  await SharedPreferencesUtil.init();
  PlatformManager.initializeForLocalHarness();
  AuthService.installLocalHarnessTokenGateway(_Gateway());
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  Env.overrideApiBaseUrl('http://127.0.0.1:${server.port}/');
  Env.armDebugJourneyCredentialTrust();
  Env.addDebugTrustedAuthority('127.0.0.1');
  final receipts = ValueNotifier<String>('Ready');
  final row = <String, dynamic>{'id': 'synthetic-task', 'description': 'Synthetic task', 'completed': false};
  var nativeCreates = 0;
  var cloudCreates = 0;
  var tokenSaves = 0;
  var apnsReady = false;
  var refuseStatus = false;
  var stallApplePermission = false;
  void publish() {
    receipts.value = 'Todoist writes: $cloudCreates; Apple writes: $nativeCreates; token saves: $tokenSaves';
    debugPrint('CAELIS_RECEIPT ${receipts.value}');
  }

  server.listen((request) async {
    final data = await utf8.decoder.bind(request).join();
    Object body = {'status': 'Ok'};
    if (request.headers.value(HttpHeaders.authorizationHeader) != 'Bearer synthetic-only') {
      request.response.statusCode = 401;
    } else if (request.uri.path == '/v1/task-integrations') {
      if (refuseStatus) request.response.statusCode = 503;
      body = {
        'default_app': 'todoist',
        'integrations': {
          'apple_reminders': {'connected': true},
          'todoist': {'connected': true}
        }
      };
    } else if (request.uri.path == '/v1/action-items') {
      body = request.method == 'GET'
          ? {
              'action_items': [row],
              'has_more': false
            }
          : row;
    } else if (request.uri.path == '/v1/task-integrations/todoist/tasks') {
      cloudCreates++;
      body = {'success': true};
    } else if (request.uri.path == '/v1/action-items/synthetic-task') {
      row.addAll(jsonDecode(data) as Map<String, dynamic>);
      body = row;
    } else if (request.uri.path == '/v1/users/fcm-token') {
      tokenSaves++;
      // A refused save must not become a success receipt; retry the same token.
      body = {'status': tokenSaves == 1 ? 'Deferred' : 'Ok'};
    } else {
      request.response.statusCode = 404;
    }
    request.response.headers.contentType = ContentType.json;
    request.response.write(jsonEncode(body));
    await request.response.close();
    publish();
  });
  final tasks = ActionItemsProvider(
      automaticAppleRemindersExport: AutomaticAppleRemindersExport(
    permission: () async => true,
    create: (_) async {
      nativeCreates++;
      publish();
      return 'synthetic-native';
    },
  ));
  await tasks.ensureLoaded();
  final connections = TaskIntegrationProvider(
      readApplePermission: () => stallApplePermission ? Completer<bool>().future : Future.value(true));
  await connections.loadFromBackend();
  final registration = FcmTokenRegistration(
    capture: () => AuthService.instance.captureSessionSnapshot(),
    isCurrent: (owner) => AuthService.instance.isSessionSnapshotCurrent(owner),
    requiresApns: true,
    readApns: () async => apnsReady ? 'synthetic-apns' : null,
    readToken: () async => 'synthetic-fcm',
    readTimeZone: () async => 'Asia/Kolkata',
    persist: (token, zone, owner) => saveFcmTokenServer(
        token: token, timeZone: zone, canSend: () => AuthService.instance.isSessionSnapshotCurrent(owner)),
  );
  OmiColors.active = OmiPalette.dark;
  runApp(MultiProvider(
      providers: [
        ChangeNotifierProvider<ActionItemsProvider>.value(value: tasks),
        ChangeNotifierProvider<TaskIntegrationProvider>.value(value: connections),
      ],
      child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: buildOmiTheme(brightness: Brightness.dark),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            appBar: AppBar(title: const Text('Task routing QA')),
            body: Stack(children: [
              ListView(padding: const EdgeInsets.all(20), children: [
                const Text('Synthetic account · Todoist selected · Apple permission granted'),
                const SizedBox(height: 24),
                FilledButton(
                    key: const Key('qa_create'),
                    onPressed: () async {
                      await tasks.createActionItem(description: 'Synthetic task');
                      publish();
                    },
                    child: const Text('Create task')),
                FilledButton(
                    key: const Key('qa_select'),
                    onPressed: () => tasks.startSelectionWithItem('synthetic-task'),
                    child: const Text('Select task for export')),
                FilledButton(
                    key: const Key('qa_push'),
                    onPressed: () {
                      unawaited(registration.refresh());
                      Timer(const Duration(seconds: 12), () {
                        apnsReady = true;
                        debugPrint('CAELIS_APNS_READY');
                      });
                    },
                    child: const Text('Test late APNs and refused save')),
                FilledButton(
                    key: const Key('qa_stall_apple'),
                    onPressed: () {
                      stallApplePermission = true;
                      debugPrint('CAELIS_APPLE_PERMISSION_STALLED');
                    },
                    child: const Text('Stall unrelated Apple permission')),
                FilledButton(
                    key: const Key('qa_status_failure'),
                    onPressed: () {
                      refuseStatus = !refuseStatus;
                      debugPrint('CAELIS_STATUS_REFUSED $refuseStatus');
                    },
                    child: const Text('Toggle status failure')),
                const SizedBox(height: 24),
                ValueListenableBuilder<String>(
                    valueListenable: receipts,
                    builder: (context, value, child) => Text(value, key: const Key('qa_receipt'))),
              ]),
              const Align(alignment: Alignment.bottomCenter, child: TaskSelectionActionBar())
            ]),
          ))));
}
