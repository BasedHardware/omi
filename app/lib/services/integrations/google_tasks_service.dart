import 'package:omi/services/integrations/integration_oauth.dart';

import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/utils/logger.dart';

class GoogleTasksService {
  static final GoogleTasksService _instance = GoogleTasksService._internal();
  factory GoogleTasksService() => _instance;
  GoogleTasksService._internal();

  bool _isAuthenticated = false;

  /// Check if user is authenticated (updated by provider from Firebase)
  bool get isAuthenticated => _isAuthenticated;

  void setAuthenticated(bool value) {
    _isAuthenticated = value;
  }

  /// Start OAuth authentication flow (get URL from backend)
  Future<bool> authenticate({bool Function()? isCurrent}) =>
      launchIntegrationOAuth(() => getOAuthUrl('google_tasks'), isCurrent: isCurrent);

  /// Handle OAuth callback (tokens stored in backend Firebase)
  Future<bool> handleCallback() async {
    _isAuthenticated = true;
    Logger.debug('Google Tasks authentication successful');
    return true;
  }

  /// Create a task in Google Tasks (via backend API)
  Future<bool> createTask({required String title, String? notes, DateTime? dueDate}) async {
    try {
      final result = await createTaskViaIntegration('google_tasks', title: title, description: notes, dueDate: dueDate);

      if (result != null && result['success'] == true) {
        Logger.debug('Task created successfully in Google Tasks');
        return true;
      }

      Logger.debug('Failed to create task in Google Tasks: ${result?['error']}');
      return false;
    } catch (e) {
      Logger.debug('Error creating task in Google Tasks: $e');
      return false;
    }
  }

  /// Disconnect from Google Tasks (remove from Firebase)
  Future<void> disconnect() async {
    try {
      await deleteTaskIntegration('google_tasks');
      _isAuthenticated = false;
      Logger.debug('✓ Disconnected from Google Tasks');
    } catch (e) {
      Logger.debug('Error disconnecting from Google Tasks: $e');
    }
  }
}
