import 'package:omi/services/integrations/integration_oauth.dart';

import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/utils/logger.dart';

class TodoistService {
  static final TodoistService _instance = TodoistService._internal();
  factory TodoistService() => _instance;
  TodoistService._internal();

  bool _isAuthenticated = false;

  /// Check if user is authenticated (updated by provider from Firebase)
  bool get isAuthenticated => _isAuthenticated;

  void setAuthenticated(bool value) {
    _isAuthenticated = value;
  }

  /// Start OAuth authentication flow (get URL from backend)
  Future<bool> authenticate({bool Function()? isCurrent}) =>
      launchIntegrationOAuth(() => getOAuthUrl('todoist'), isCurrent: isCurrent);

  /// Handle OAuth callback (tokens stored in backend Firebase)
  Future<bool> handleCallback() async {
    _isAuthenticated = true;
    Logger.debug('Todoist authentication successful');
    return true;
  }

  /// Create a task in Todoist (via backend API)
  Future<bool> createTask({required String content, String? description, DateTime? dueDate}) async {
    try {
      final result = await createTaskViaIntegration(
        'todoist',
        title: content,
        description: description,
        dueDate: dueDate,
      );

      if (result != null && result['success'] == true) {
        Logger.debug('Task created successfully in Todoist');
        return true;
      }

      Logger.debug('Failed to create task in Todoist: ${result?['error']}');
      return false;
    } catch (e) {
      Logger.debug('Error creating task in Todoist: $e');
      return false;
    }
  }

  /// Disconnect from Todoist (remove from Firebase)
  Future<void> disconnect() async {
    try {
      await deleteTaskIntegration('todoist');
      _isAuthenticated = false;
      Logger.debug('✓ Disconnected from Todoist');
    } catch (e) {
      Logger.debug('Error disconnecting from Todoist: $e');
    }
  }
}
