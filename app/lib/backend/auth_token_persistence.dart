import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/utils/logger.dart';

abstract interface class AuthTokenStorage {
  Future<String?> read();

  Future<void> write(String value);

  Future<void> delete();
}

final class _FlutterSecureAuthTokenStorage implements AuthTokenStorage {
  const _FlutterSecureAuthTokenStorage(this._storage);

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read() => _storage.read(key: 'authToken');

  @override
  Future<void> write(String value) => _storage.write(key: 'authToken', value: value);

  @override
  Future<void> delete() => _storage.delete(key: 'authToken');
}

final class AuthTokenPersistence {
  AuthTokenPersistence({required SharedPreferences preferences, required AuthTokenStorage storage})
      : _preferences = preferences,
        _storage = storage;

  final SharedPreferences _preferences;
  final AuthTokenStorage _storage;

  static const _authTokenKey = 'authToken';
  static const _nativeAuthTokenKey = 'nativeAuthToken';
  static const _authTokenDeletePendingKey = 'authTokenDeletePending';

  static AuthTokenStorage createDefaultStorage() {
    return const _FlutterSecureAuthTokenStorage(FlutterSecureStorage());
  }

  Future<T> _withRetry<T>(Future<T> Function() operation, String label, {int maxAttempts = 3}) async {
    for (var attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        return await operation().timeout(const Duration(seconds: 1));
      } catch (e) {
        if (attempt == maxAttempts) rethrow;
        await Future.delayed(Duration(milliseconds: 100 * attempt));
      }
    }
    throw StateError('unreachable');
  }

  Future<String?> readSecureAuthToken() async {
    try {
      return await _withRetry(() => _storage.read(), 'readAuthToken from secure storage');
    } catch (e) {
      Logger.error('Failed to read authToken from secure storage: ${e.runtimeType}');
      return null;
    }
  }

  Future<bool> writeSecureAuthToken(String value) async {
    try {
      return await _withRetry(() async {
        await _storage.write(value);
        if (await _storage.read() == value) return true;
        throw StateError('secure authToken verification failed');
      }, 'writeAuthToken to secure storage');
    } catch (e) {
      Logger.error('Failed to write authToken to secure storage: ${e.runtimeType}');
      return false;
    }
  }

  Future<bool> deleteSecureAuthToken() async {
    try {
      return await _withRetry(() async {
        await _storage.delete();
        if (await _storage.read() == null) return true;
        throw StateError('secure authToken deletion verification failed');
      }, 'deleteAuthToken from secure storage');
    } catch (e) {
      Logger.error('Failed to delete authToken from secure storage: ${e.runtimeType}');
      return false;
    }
  }

  Future<bool> removeLegacyAuthToken() async {
    try {
      return await _withRetry(() async {
        if (!_preferences.containsKey(_authTokenKey)) return true;
        final removed = await _preferences.remove(_authTokenKey);
        if (removed) return true;
        throw StateError('legacy authToken removal was not committed');
      }, 'removeLegacyAuthToken');
    } catch (e) {
      Logger.error('Failed to remove legacy authToken: ${e.runtimeType}');
      return false;
    }
  }

  Future<bool> writeNativeAuthToken(String value) async {
    if (defaultTargetPlatform != TargetPlatform.android) return true;
    try {
      return await _withRetry(() async {
        final saved = await _preferences.setString(_nativeAuthTokenKey, value);
        if (saved) return true;
        throw StateError('native authToken mirror was not committed');
      }, 'writeNativeAuthToken');
    } catch (e) {
      Logger.error('Failed to mirror authToken for native Android audio: ${e.runtimeType}');
      return false;
    }
  }

  Future<bool> removeNativeAuthToken() async {
    if (defaultTargetPlatform != TargetPlatform.android) return true;
    try {
      return await _withRetry(() async {
        if (!_preferences.containsKey(_nativeAuthTokenKey)) return true;
        final removed = await _preferences.remove(_nativeAuthTokenKey);
        if (removed) return true;
        throw StateError('native authToken mirror removal was not committed');
      }, 'removeNativeAuthToken');
    } catch (e) {
      Logger.error('Failed to remove native authToken mirror: ${e.runtimeType}');
      return false;
    }
  }

  Future<bool> markAuthTokenDeletePending() async {
    try {
      return await _withRetry(() async {
        final saved = await _preferences.setBool(_authTokenDeletePendingKey, true);
        if (saved) return true;
        throw StateError('authToken deletion marker was not committed');
      }, 'markAuthTokenDeletePending');
    } catch (e) {
      Logger.error('Failed to mark authToken deletion pending: ${e.runtimeType}');
      return false;
    }
  }

  Future<bool> clearAuthTokenDeletePending() async {
    if (!_preferences.containsKey(_authTokenDeletePendingKey)) return true;
    try {
      final removed = await _preferences.remove(_authTokenDeletePendingKey);
      if (removed) return true;
      throw StateError('authToken deletion marker removal was not committed');
    } catch (e) {
      Logger.error('Failed to clear authToken deletion pending: ${e.runtimeType}');
      return false;
    }
  }

  Future<bool> persist(String value) async {
    try {
      if (value.isEmpty) {
        await markAuthTokenDeletePending();
        final deleted = await deleteSecureAuthToken();
        final nativeRemoved = await removeNativeAuthToken();
        final legacyRemoved = await removeLegacyAuthToken();
        if (deleted && nativeRemoved && legacyRemoved) {
          await clearAuthTokenDeletePending();
        }
        return deleted && nativeRemoved && legacyRemoved;
      }

      if (!await clearAuthTokenDeletePending()) return false;

      final stored = await writeSecureAuthToken(value);
      if (!stored) return false;
      final nativeStored = await writeNativeAuthToken(value);
      final legacyRemoved = await removeLegacyAuthToken();
      return nativeStored && legacyRemoved;
    } catch (e) {
      Logger.error('Failed to persist authToken: ${e.runtimeType}');
      return false;
    }
  }
}
