import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/privacy.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/logger.dart';

class UserProvider with ChangeNotifier {
  static const int _migrationNotificationId = 1337;

  String _dataProtectionLevel = 'standard';
  bool _isLoading = false;

  bool _isMigrating = false;
  List<MigrationRequest> _migrationQueue = [];
  int _processedCount = 0;
  String _migrationMessage = '';

  // New properties for enhanced UX
  String _sourceLevel = '';
  String _targetLevel = '';
  DateTime? _startTime;

  String get dataProtectionLevel => _dataProtectionLevel;
  bool get isLoading => _isLoading;
  bool get isMigrating => _isMigrating;
  int get migrationTotalCount => _migrationQueue.length;
  int get migrationProcessedCount => _processedCount;
  String get migrationMessage => _migrationMessage;
  String get sourceLevel => _sourceLevel;
  String get targetLevel => _targetLevel;

  String get migrationETA {
    if (_processedCount == 0 || _startTime == null || migrationTotalCount == 0) {
      return 'Calculating...';
    }
    final elapsed = DateTime.now().difference(_startTime!);
    if (elapsed.inSeconds < 2) {
      return 'Calculating...';
    }
    final timePerObject = elapsed.inMilliseconds / _processedCount;
    final remainingObjects = migrationTotalCount - _processedCount;
    final remainingMilliseconds = (timePerObject * remainingObjects).round();
    final remainingDuration = Duration(milliseconds: remainingMilliseconds);

    if (remainingDuration.inMinutes > 1) {
      return 'About ${remainingDuration.inMinutes} minutes remaining';
    } else if (remainingDuration.inSeconds > 10) {
      return 'About a minute remaining';
    } else if (remainingObjects > 0) {
      return 'Almost done...';
    }
    return '';
  }

  Future<void> initialize() async {
    _isLoading = true;
    notifyListeners();
    try {
      final userProfile = await PrivacyApi.getUserProfile();
      _dataProtectionLevel = userProfile['data_protection_level'] ?? 'standard';
      SharedPreferencesUtil().dataProtectionLevel = _dataProtectionLevel;

      final migrationStatus = userProfile['migration_status'];
      if (migrationStatus != null && migrationStatus['status'] == 'in_progress') {
        final targetLevel = migrationStatus['target_level'];
        if (targetLevel != null) {
          Future.microtask(() => updateDataProtectionLevel(targetLevel));
        }
      }
    } catch (e, stackTrace) {
      Logger.error('Failed to initialize UserProvider: $e\n$stackTrace');
      // Fallback to local cache if server fails
      _dataProtectionLevel = SharedPreferencesUtil().dataProtectionLevel;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<int> getMigrationCountFor(String targetLevel) async {
    if (dataProtectionLevel == targetLevel) return 0;
    try {
      final objects = await PrivacyApi.checkMigration(targetLevel);
      return objects.length;
    } catch (e) {
      return 0;
    }
  }

  Future<void> updateDataProtectionLevel(String targetLevel) async {
    if (_isMigrating) return;

    _isMigrating = true;
    _sourceLevel = _dataProtectionLevel;
    _targetLevel = targetLevel;
    _startTime = DateTime.now();
    _migrationMessage = 'Analyzing your data...';
    notifyListeners();

    try {
      await PrivacyApi.startMigration(targetLevel);

      NotificationService.instance.showNotification(
        id: _migrationNotificationId,
        title: 'Data Migration in Progress',
        body: 'Starting migration to $targetLevel protection...',
        layout: NotificationLayout.ProgressBar,
        payload: {'navigate_to': '/settings/data-privacy', 'progress': '0'},
      );

      _migrationQueue = await PrivacyApi.checkMigration(targetLevel);
      _processedCount = 0;

      if (_migrationQueue.isEmpty) {
        _migrationMessage = 'No data to migrate. Finalizing...';
        notifyListeners();
        await _finalize(targetLevel);
        return;
      }

      const batchSize = 5;
      for (var i = 0; i < _migrationQueue.length; i += batchSize) {
        final end = (i + batchSize > _migrationQueue.length) ? _migrationQueue.length : i + batchSize;
        final batch = _migrationQueue.sublist(i, end);

        await PrivacyApi.migrateObjectsBatch(batch);

        _processedCount += batch.length;
        final percentage = ((_processedCount / migrationTotalCount) * 100).toInt();
        _migrationMessage = 'Migrating... $percentage%';

        NotificationService.instance.showNotification(
          id: _migrationNotificationId,
          title: 'Data Migration in Progress',
          body: '$_processedCount of $migrationTotalCount objects migrated ($percentage%)',
          layout: NotificationLayout.ProgressBar,
          payload: {'navigate_to': '/settings/data-privacy', 'progress': percentage.toString()},
        );

        notifyListeners();
      }

      _migrationMessage = 'All objects migrated. Finalizing...';
      notifyListeners();
      await _finalize(targetLevel);
    } catch (e, stackTrace) {
      Logger.error('Failed to update data protection level: $e\n$stackTrace');
      _isMigrating = false;
      _migrationMessage = 'An error occurred during migration. Please try again.';

      NotificationService.instance.showNotification(
        id: _migrationNotificationId,
        title: 'Migration Failed',
        body: 'An error occurred during data migration. Please try again.',
        layout: NotificationLayout.Default,
        payload: {'navigate_to': '/settings/data-privacy'},
      );

      notifyListeners();
      rethrow;
    }
  }

  Future<void> _finalize(String targetLevel) async {
    await PrivacyApi.finalizeMigration(targetLevel);
    _dataProtectionLevel = targetLevel;
    SharedPreferencesUtil().dataProtectionLevel = targetLevel;
    _isMigrating = false;
    _migrationMessage = 'Migration complete!';
    _startTime = null;

    NotificationService.instance.showNotification(
      id: _migrationNotificationId,
      title: 'Migration Complete',
      body: 'Your data is now protected with the new $targetLevel settings.',
      layout: NotificationLayout.Default,
      payload: {'navigate_to': '/settings/data-privacy'},
    );
    // Clear the notification after a few seconds
    Future.delayed(const Duration(seconds: 5), () {
      NotificationService.instance.clearNotification(_migrationNotificationId);
    });

    notifyListeners();
  }
}
