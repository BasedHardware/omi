import 'package:flutter/material.dart';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:geolocator/geolocator.dart';

import 'package:omi/backend/http/api/privacy.dart';
import 'package:omi/backend/http/api/users.dart' as users_api;
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/logger.dart';

class UserProvider with ChangeNotifier {
  static const int _migrationNotificationId = 1337;

  String _dataProtectionLevel = 'standard';
  bool _isLoading = false;
  bool _privateCloudSyncEnabled = false;
  bool _trainingDataOptedIn = false;
  String? _trainingDataStatus;

  bool _isMigrating = false;
  bool _migrationFailed = false;
  List<MigrationRequest> _migrationQueue = [];
  int _processedCount = 0;
  String _migrationMessage = '';

  // New properties for enhanced UX
  String _sourceLevel = '';
  String _targetLevel = '';
  DateTime? _startTime;

  Geolocation? _lastKnownLocation;

  // Transcription preferences
  bool _singleLanguageMode = false;
  List<String> _transcriptionVocabulary = [];

  // Loading states for transcription settings
  bool _isUpdatingSingleLanguageMode = false;
  bool _isUpdatingVocabulary = false;

  // Transcription preferences getters
  bool get singleLanguageMode => _singleLanguageMode;
  List<String> get transcriptionVocabulary => _transcriptionVocabulary;
  bool get isUpdatingSingleLanguageMode => _isUpdatingSingleLanguageMode;
  bool get isUpdatingVocabulary => _isUpdatingVocabulary;

  String get dataProtectionLevel => _dataProtectionLevel;
  bool get isLoading => _isLoading;
  bool get privateCloudSyncEnabled => _privateCloudSyncEnabled;
  bool get trainingDataOptedIn => _trainingDataOptedIn;
  String? get trainingDataStatus => _trainingDataStatus;
  bool get isMigrating => _isMigrating;
  bool get migrationFailed => _migrationFailed;
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

  String _getMigrationItemName(String type) {
    switch (type) {
      case 'conversation':
        return 'conversations';
      case 'memory':
        return 'memories';
      case 'chat':
        return 'chats';
      default:
        return 'data';
    }
  }

  Future<void> initialize() async {
    _isLoading = true;

    // Preload from SharedPreferences for instant UI
    _preloadFromCache();
    notifyListeners();

    try {
      final userProfile = await PrivacyApi.getUserProfile();
      _dataProtectionLevel = userProfile['data_protection_level'] ?? 'standard';

      // Load private cloud sync status
      await _loadPrivateCloudSyncStatus();

      // Load training data opt-in status
      await _loadTrainingDataOptIn();

      // Load transcription preferences (will sync with API and update cache)
      await _loadTranscriptionPreferences();

      final migrationStatus = userProfile['migration_status'];
      if (migrationStatus != null && migrationStatus['status'] == 'in_progress') {
        final targetLevel = migrationStatus['target_level'];
        if (targetLevel != null) {
          Future.microtask(() => updateDataProtectionLevel(targetLevel));
        }
      }
    } catch (e, stackTrace) {
      Logger.error('Failed to initialize UserProvider: $e\n$stackTrace');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void _preloadFromCache() {
    final prefs = SharedPreferencesUtil();
    _singleLanguageMode = prefs.cachedSingleLanguageMode;
    _transcriptionVocabulary = prefs.cachedTranscriptionVocabulary;
  }

  void _syncToCache() {
    final prefs = SharedPreferencesUtil();
    prefs.cachedSingleLanguageMode = _singleLanguageMode;
    prefs.cachedTranscriptionVocabulary = _transcriptionVocabulary;
  }

  Future<void> _loadPrivateCloudSyncStatus() async {
    try {
      _privateCloudSyncEnabled = await getPrivateCloudSyncEnabled();
    } catch (e) {
      Logger.error('Failed to load private cloud sync status: $e');
      _privateCloudSyncEnabled = false;
    }
  }

  Future<void> _loadTranscriptionPreferences() async {
    try {
      final prefs = await getTranscriptionPreferences();
      if (prefs != null) {
        _singleLanguageMode = prefs['single_language_mode'] ?? false;
        _transcriptionVocabulary = List<String>.from(prefs['vocabulary'] ?? []);
        _syncToCache();
        notifyListeners();
      }
    } catch (e) {
      Logger.error('Failed to load transcription preferences: $e');
      // Keep cached values on error, don't reset
    }
  }

  Future<void> _loadTrainingDataOptIn() async {
    try {
      final data = await getTrainingDataOptIn();
      _trainingDataOptedIn = data['opted_in'] ?? false;
      _trainingDataStatus = data['status'];
    } catch (e) {
      Logger.error('Failed to load training data opt-in status: $e');
      _trainingDataOptedIn = false;
      _trainingDataStatus = null;
    }
  }

  Future<void> optInForTrainingData() async {
    try {
      final success = await setTrainingDataOptIn();
      if (success) {
        _trainingDataOptedIn = true;
        _trainingDataStatus = 'pending_review';
        notifyListeners();
      }
    } catch (e, stackTrace) {
      Logger.error('Failed to opt-in for training data: $e\n$stackTrace');
      rethrow;
    }
  }

  Future<bool> setSingleLanguageMode(bool value) async {
    if (_isUpdatingSingleLanguageMode) return false;

    _isUpdatingSingleLanguageMode = true;
    notifyListeners();

    try {
      final success = await setTranscriptionPreferences(singleLanguageMode: value);
      if (success) {
        _singleLanguageMode = value;
        _syncToCache();
      }
      return success;
    } catch (e, stackTrace) {
      Logger.error('Failed to set single language mode: $e\n$stackTrace');
      return false;
    } finally {
      _isUpdatingSingleLanguageMode = false;
      notifyListeners();
    }
  }

  Future<bool> updateTranscriptionVocabulary(List<String> vocabulary) async {
    if (_isUpdatingVocabulary) return false;

    _isUpdatingVocabulary = true;
    notifyListeners();

    try {
      final success = await setTranscriptionPreferences(vocabulary: vocabulary);
      if (success) {
        _transcriptionVocabulary = vocabulary;
        _syncToCache();
      }
      return success;
    } catch (e, stackTrace) {
      Logger.error('Failed to update transcription vocabulary: $e\n$stackTrace');
      return false;
    } finally {
      _isUpdatingVocabulary = false;
      notifyListeners();
    }
  }

  Future<bool> addVocabularyWords(List<String> words) async {
    if (words.isEmpty) return false;
    final trimingWords = words.map((w) => w.trim()).where((w) => !_transcriptionVocabulary.contains(w));
    if (trimingWords.isEmpty) {
      return false;
    }
    final newVocabulary = [..._transcriptionVocabulary, ...trimingWords];
    return updateTranscriptionVocabulary(newVocabulary);
  }

  Future<bool> removeVocabularyWord(String word) async {
    final newVocabulary = _transcriptionVocabulary.where((w) => w != word).toList();
    return updateTranscriptionVocabulary(newVocabulary);
  }

  Future<void> setPrivateCloudSync(bool value) async {
    try {
      final success = await setPrivateCloudSyncEnabled(value);
      if (success) {
        _privateCloudSyncEnabled = value;
        notifyListeners();
      }
    } catch (e, stackTrace) {
      Logger.error('Failed to set private cloud sync: $e\n$stackTrace');
      rethrow;
    }
  }

  Future<void> updateUserGeolocationIfNeeded(Map<String, dynamic> data) async {
    try {
      final newLocation = Geolocation(
        latitude: data['latitude'],
        longitude: data['longitude'],
        accuracy: data['accuracy'],
        altitude: data['altitude'],
        time: DateTime.parse(data['time']).toUtc(),
      );

      // Ensure new location has valid coordinates before proceeding.
      if (newLocation.latitude == null || newLocation.longitude == null) {
        Logger.log('Received location update with null coordinates, skipping.');
        return;
      }

      if (_lastKnownLocation != null && _lastKnownLocation!.latitude != null && _lastKnownLocation!.longitude != null) {
        // Truncate to 4 decimal places for comparison
        final lastLat = double.parse(_lastKnownLocation!.latitude!.toStringAsFixed(4));
        final lastLon = double.parse(_lastKnownLocation!.longitude!.toStringAsFixed(4));
        final newLat = double.parse(newLocation.latitude!.toStringAsFixed(4));
        final newLon = double.parse(newLocation.longitude!.toStringAsFixed(4));

        // Only update if location has changed up to 4 decimal places
        if (lastLat == newLat && lastLon == newLon) {
          Logger.log('User has not moved significantly (based on 4 decimal places), skipping geolocation update.');
          return;
        }
      }

      Logger.log('Updating user geolocation.');
      await updateUserGeolocation(geolocation: newLocation);
      _lastKnownLocation = newLocation;
    } catch (e, stackTrace) {
      Logger.error('Failed to update user geolocation: $e\n$stackTrace');
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
    _migrationFailed = false;
    _sourceLevel = _dataProtectionLevel;
    _targetLevel = targetLevel;
    _startTime = DateTime.now();
    _migrationMessage = 'Analyzing your data...';
    notifyListeners();

    try {
      await PrivacyApi.startMigration(targetLevel);

      NotificationService.instance.showNotification(
        id: _migrationNotificationId,
        title: 'omi says',
        body: 'Migrating to $targetLevel protection...',
        layout: NotificationLayout.Default,
        payload: {'navigate_to': '/settings/data-privacy'},
      );

      _migrationQueue = await PrivacyApi.checkMigration(targetLevel);
      _processedCount = 0;

      if (_migrationQueue.isEmpty) {
        _migrationMessage = 'No data to migrate. Finalizing...';
        notifyListeners();
        await _finalize(targetLevel);
        return;
      }

      const batchSize = 100;
      for (var i = 0; i < _migrationQueue.length; i += batchSize) {
        final end = (i + batchSize > _migrationQueue.length) ? _migrationQueue.length : i + batchSize;
        final batch = _migrationQueue.sublist(i, end);
        final itemType = _getMigrationItemName(batch.first.type);

        await PrivacyApi.migrateObjectsBatch(batch);

        _processedCount += batch.length;
        final percentage = ((_processedCount / migrationTotalCount) * 100).toInt();
        _migrationMessage = 'Migrating $itemType... $percentage%';

        notifyListeners();
      }

      _migrationMessage = 'All objects migrated. Finalizing...';
      notifyListeners();
      await _finalize(targetLevel);
    } catch (e, stackTrace) {
      Logger.error('Failed to update data protection level: $e\n$stackTrace');
      _isMigrating = false;
      _migrationFailed = true;
      _migrationMessage = 'An error occurred during migration. Please try again.';

      NotificationService.instance.showNotification(
        id: _migrationNotificationId,
        title: 'omi says',
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
    _isMigrating = false;
    _migrationFailed = false;
    _migrationMessage = 'Migration complete!';
    _startTime = null;
    _processedCount = 0;
    _migrationQueue = [];

    NotificationService.instance.showNotification(
      id: _migrationNotificationId,
      title: 'omi says',
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
