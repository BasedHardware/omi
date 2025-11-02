import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:url_launcher/url_launcher.dart';

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
  Future<bool> authenticate() async {
    try {
      final authUrl = await getOAuthUrl('google_tasks');
      if (authUrl == null) {
        debugPrint('Failed to get Google Tasks OAuth URL from backend');
        return false;
      }

      final authUri = Uri.parse(authUrl);
      debugPrint('Opening Google Tasks auth URL');

      final canLaunch = await canLaunchUrl(authUri);
      if (!canLaunch) {
        debugPrint('Cannot launch auth URL');
        return false;
      }

      await launchUrl(
        authUri,
        mode: LaunchMode.externalApplication,
      );

      return true;
    } catch (e) {
      debugPrint('Error starting Google Tasks authentication: $e');
      return false;
    }
  }

  /// Handle OAuth callback (tokens stored in backend Firebase)
  Future<bool> handleCallback() async {
    _isAuthenticated = true;
    debugPrint('Google Tasks authentication successful');
    return true;
  }

  /// Create a task in Google Tasks (via backend API)
  Future<bool> createTask({
    required String title,
    String? notes,
    DateTime? dueDate,
  }) async {
    try {
      final result = await createTaskViaIntegration(
        'google_tasks',
        title: title,
        description: notes,
        dueDate: dueDate,
      );

      if (result != null && result['success'] == true) {
        debugPrint('Task created successfully in Google Tasks');
        return true;
      }

      debugPrint('Failed to create task in Google Tasks: ${result?['error']}');
      return false;
    } catch (e) {
      debugPrint('Error creating task in Google Tasks: $e');
      return false;
    }
  }

  /// Disconnect from Google Tasks (remove from Firebase)
  Future<void> disconnect() async {
    try {
      await deleteTaskIntegration('google_tasks');
      _isAuthenticated = false;
      debugPrint('✓ Disconnected from Google Tasks');
    } catch (e) {
      debugPrint('Error disconnecting from Google Tasks: $e');
    }
  }
}
