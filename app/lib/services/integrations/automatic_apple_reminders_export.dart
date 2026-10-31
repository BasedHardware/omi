import 'package:omi/backend/http/api/action_items.dart' as tasks;
import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/integrations/apple_reminders_service.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// EventKit permission is not a choice of export destination. Deliberate
/// exports and updates to already-linked reminders retain their existing paths.
class AutomaticAppleRemindersExport {
  AutomaticAppleRemindersExport({
    bool Function()? available,
    AuthSessionSnapshot? Function()? capture,
    bool Function(AuthSessionSnapshot)? isCurrent,
    Future<TaskIntegrationsResponse?> Function(bool Function())? status,
    Future<bool> Function()? permission,
    Future<String?> Function(ActionItemWithMetadata)? create,
    Future<bool> Function(String, String, bool Function())? acknowledge,
  })  : _available = available ?? (() => PlatformService.isApple),
        _capture = capture ?? (() => AuthService.instance.captureSessionSnapshot()),
        _isCurrent = isCurrent ?? ((owner) => AuthService.instance.isSessionSnapshotCurrent(owner)),
        _status = status ?? ((current) => getTaskIntegrations(canSend: current)),
        _permission = permission ?? (() => AppleRemindersService().hasPermission()),
        _create = create ??
            ((item) => AppleRemindersService().addReminder(
                  title: item.description,
                  notes: 'From Omi',
                  dueDate: item.dueAt,
                )),
        _acknowledge = acknowledge ??
            ((id, reminder, current) async =>
                await tasks.updateActionItem(id,
                    exported: true, exportPlatform: 'apple_reminders', appleReminderId: reminder, canSend: current) !=
                null);

  final bool Function() _available;
  final AuthSessionSnapshot? Function() _capture;
  final bool Function(AuthSessionSnapshot) _isCurrent;
  final Future<TaskIntegrationsResponse?> Function(bool Function()) _status;
  final Future<bool> Function() _permission;
  final Future<String?> Function(ActionItemWithMetadata) _create;
  final Future<bool> Function(String, String, bool Function()) _acknowledge;

  Future<bool> export(ActionItemWithMetadata item, {required bool Function() canContinue}) async {
    if (!_available() ||
        item.completed ||
        item.exported ||
        item.appleReminderId?.isNotEmpty == true ||
        item.status != 'active') {
      return false;
    }
    final owner = _capture();
    if (owner == null) return false;
    bool current() => canContinue() && _isCurrent(owner);
    try {
      if (!current()) return false;
      final status = await _status(current);
      if (!current() ||
          status?.defaultApp != 'apple_reminders' ||
          status?.integrations['apple_reminders'] is! Map ||
          status?.integrations['apple_reminders']['connected'] != true) {
        return false;
      }
      if (!await _permission() || !current()) return false;
      final reminder = await _create(item);
      if (reminder == null || !current()) return false;
      return await _acknowledge(item.id, reminder, current) && current();
    } catch (error) {
      // A failed read never selects a fallback destination or logs task text.
      Logger.debug('Automatic Apple Reminders export deferred: ${error.runtimeType}');
      return false;
    }
  }
}
