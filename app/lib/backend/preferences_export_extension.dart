import 'package:omi/models/action_item_integration.dart';
import 'package:omi/backend/preferences.dart';

extension SharedPreferencesExportExtension on SharedPreferencesUtil {
  static const String _taskExportDestinationKey = 'task_export_destination';

  ActionItemIntegration getTaskExportDestination() {
    final destinationString = getString(_taskExportDestinationKey);
    if (destinationString == null) {
      return ActionItemIntegration.appleReminders;
    }
    try {
      return ActionItemIntegration.values.firstWhere(
        (integration) => integration.name == destinationString,
        orElse: () => ActionItemIntegration.appleReminders,
      );
    } catch (e) {
      return ActionItemIntegration.appleReminders;
    }
  }

  Future<void> setTaskExportDestination(ActionItemIntegration destination) async {
    await saveString(_taskExportDestinationKey, destination.name);
  }
}