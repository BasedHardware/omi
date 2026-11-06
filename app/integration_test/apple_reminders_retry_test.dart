// Exercise production EventKit export and retry on an isolated iPhone simulator.
// The loopback server commits the task link before withholding its acknowledgement.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/action_items/services/action_item_export_service.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/integrations/apple_reminders_service.dart';
import 'package:omi/services/integrations/automatic_apple_reminders_export.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _owner = 'synthetic-reminder-retry';

class _Gateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot get currentUser => const AuthUserSnapshot(uid: _owner);

  @override
  Future<RefreshedAuthToken?> forceRefresh() async =>
      RefreshedAuthToken(token: 'synthetic-only', expirationTime: DateTime.now().add(const Duration(hours: 1)));

  @override
  Future<void> signOut() async {}
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('automatic export and later manual retry share one real EventKit reminder', (tester) async {
    await tester.runAsync(() async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('uid', _owner);
      await SharedPreferencesUtil.init();
      PlatformManager.initializeForLocalHarness();
      AuthService.installLocalHarnessTokenGateway(_Gateway());

      final reminders = AppleRemindersService();
      expect(await reminders.hasPermission(), isTrue, reason: 'Grant reminders on the isolated simulator first');
      final id = 'reminder-retry-${DateTime.now().microsecondsSinceEpoch}';
      final item = ActionItemWithMetadata(id: id, description: id, completed: true, status: 'completed');
      final writtenIds = <String>{};
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      Env.overrideApiBaseUrl('http://127.0.0.1:${server.port}/');
      Env.armDebugJourneyCredentialTrust();
      Env.addDebugTrustedAuthority('127.0.0.1');
      var receiptAvailable = false;
      Map<String, dynamic>? committed;
      server.listen((request) async {
        final response = request.response;
        response.headers.contentType = ContentType.json;
        if (request.headers.value(HttpHeaders.authorizationHeader) != 'Bearer synthetic-only') {
          response.statusCode = HttpStatus.unauthorized;
        } else if (request.uri.path == '/v1/task-integrations') {
          response.write(jsonEncode({
            'default_app': 'apple_reminders',
            'integrations': {
              'apple_reminders': {'connected': true}
            }
          }));
        } else if (request.method == 'PATCH' && request.uri.path == '/v1/action-items/$id') {
          final patch = jsonDecode(await utf8.decoder.bind(request).join()) as Map<String, dynamic>;
          writtenIds.add(patch['apple_reminder_id'] as String);
          committed = {'id': id, 'description': id, 'completed': true, 'status': 'completed', ...patch};
          if (!receiptAvailable) response.statusCode = HttpStatus.serviceUnavailable;
          response.write(jsonEncode(receiptAvailable ? committed : {'detail': 'synthetic lost receipt'}));
        } else {
          response.statusCode = HttpStatus.notFound;
        }
        await response.close();
      });

      try {
        expect(await AutomaticAppleRemindersExport().export(item, canContinue: () => true), isFalse);
        expect(committed?['exported'], isTrue);
        expect(writtenIds, hasLength(1));
        final original = writtenIds.single;
        expect((await reminders.getRemindersStatus({id: original}))[id]?['completed'], isTrue);

        // Preserve edits made in Reminders before a retry, and keep the task's
        // stale unexported copy to simulate a client that lost the response.
        final editedTitle = '$id edited';
        expect(await reminders.updateReminderById(original, title: editedTitle), isTrue);
        receiptAvailable = true;
        expect(await ActionItemExportService.export(item, TaskIntegrationApp.appleReminders), ExportResult.success);
        expect(writtenIds, {original});
        final titles = await reminders.getExistingReminders();
        expect(titles.where((title) => title == editedTitle), hasLength(1));
        expect(titles, isNot(contains(id)));

        // Simultaneous exports of different tasks with the same title keep
        // separate reminders, and repeated exports of one task reuse its ID.
        final another = item.copyWith(id: '$id-concurrent', description: editedTitle);
        final third = another.copyWith(id: '$id-concurrent-other');
        final concurrent = await Future.wait([
          reminders.exportTaskReminder(another, ownerUid: _owner),
          reminders.exportTaskReminder(third, ownerUid: _owner),
          reminders.exportTaskReminder(another, ownerUid: _owner),
        ]);
        writtenIds.addAll(concurrent.whereType<String>());
        expect(concurrent, everyElement(isNotNull));
        expect(concurrent[2], concurrent[0]);
        expect(writtenIds, hasLength(3));
        expect(await reminders.exportTaskReminder(third, ownerUid: _owner), concurrent[1]);
        expect((await reminders.getExistingReminders()).where((title) => title == editedTitle), hasLength(3));
        expect(await reminders.exportTaskReminder(item, ownerUid: 'different-owner'), isNull);
      } finally {
        await server.close(force: true);
        for (final reminder in writtenIds) {
          await reminders.deleteReminderById(reminder);
        }
        await prefs.remove('uid');
      }
    });
  });
}
