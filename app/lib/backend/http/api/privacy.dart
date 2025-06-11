import 'dart:convert';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/logger.dart';

class PrivacyApi {
  static Future<Map<String, dynamic>> getUserProfile() async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v1/users/profile',
        method: 'GET',
        headers: {},
        body: '',
      );

      if (response != null && response.statusCode == 200) {
        return jsonDecode(response.body);
      } else {
        Logger.error('Failed to get user profile: ${response?.statusCode} ${response?.body}');
        throw Exception('Failed to load user profile');
      }
    } catch (e, stackTrace) {
      Logger.error('Error getting user profile: $e\n$stackTrace');
      rethrow;
    }
  }

  static Future<void> startMigration(String targetLevel) async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v1/users/settings/privacy/start_migration',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'target_level': targetLevel}),
      );
      if (response == null || response.statusCode != 200) {
        Logger.error('Failed to start migration: ${response?.statusCode} ${response?.body}');
        throw Exception('Failed to start migration');
      }
    } catch (e, stackTrace) {
      Logger.error('Error starting migration: $e\n$stackTrace');
      rethrow;
    }
  }

  static Future<List<MigrationObject>> checkMigration(String targetLevel) async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v1/users/settings/privacy/migration_check?target_level=$targetLevel',
        method: 'GET',
        headers: {},
        body: '',
      );
      if (response != null && response.statusCode == 200) {
        final body = jsonDecode(response.body);
        final List<dynamic> objects = body['needs_migration'];
        return objects.map((obj) => MigrationObject.fromJson(obj)).toList();
      } else {
        Logger.error('Failed to check migration status: ${response?.statusCode} ${response?.body}');
        throw Exception('Failed to check migration status');
      }
    } catch (e, stackTrace) {
      Logger.error('Error checking migration status: $e\n$stackTrace');
      rethrow;
    }
  }

  static Future<void> migrateObject(MigrationObject object, String targetLevel) async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v1/users/settings/privacy/migrate_object',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'id': object.id,
          'type': object.type,
          'target_level': targetLevel,
        }),
      );
      if (response == null || response.statusCode != 200) {
        Logger.error('Failed to migrate object ${object.id}: ${response?.statusCode} ${response?.body}');
        throw Exception('Failed to migrate object');
      }
    } catch (e, stackTrace) {
      Logger.error('Error migrating object ${object.id}: $e\n$stackTrace');
      rethrow;
    }
  }

  static Future<void> finalizeMigration(String targetLevel) async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v1/users/settings/privacy/finalize_migration',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'target_level': targetLevel}),
      );
      if (response == null || response.statusCode != 200) {
        Logger.error('Failed to finalize migration: ${response?.statusCode} ${response?.body}');
        throw Exception('Failed to finalize migration');
      }
    } catch (e, stackTrace) {
      Logger.error('Error finalizing migration: $e\n$stackTrace');
      rethrow;
    }
  }
}
