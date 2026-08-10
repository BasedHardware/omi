1. **Import `flutter_secure_storage` in `app/lib/backend/preferences.dart`**: Add `import 'package:flutter_secure_storage/flutter_secure_storage.dart';`
2. **Setup Secure Storage in `SharedPreferencesUtil`**:
    *   Add a static `FlutterSecureStorage? _secureStorage;` and a private variable `String _authToken = '';` for synchronous access.
    *   Initialize it in `SharedPreferencesUtil.init()`: `_secureStorage = const FlutterSecureStorage();`.
    *   Load the existing secure token in `init()`:
        ```dart
        _authToken = await _secureStorage?.read(key: 'authToken') ?? '';
        ```
    *   **Migration logic**:
        ```dart
        if (_authToken.isEmpty) {
          final legacyToken = _preferences?.getString('authToken') ?? '';
          if (legacyToken.isNotEmpty) {
            _authToken = legacyToken;
            await _secureStorage?.write(key: 'authToken', value: legacyToken);
            await _preferences?.remove('authToken');
          }
        }
        ```
3. **Migrate `authToken` properties**:
    *   Change the `authToken` getter to return the memory-cached `_authToken`:
        ```dart
        String get authToken => _authToken;
        ```
    *   Change the `authToken` setter to update the memory-cached token and write to secure storage async:
        ```dart
        set authToken(String value) {
          _authToken = value;
          _secureStorage?.write(key: 'authToken', value: value);
        }
        ```
    *   Update `clearUserDisplayCache` to also write to secure storage asynchronously or make it async if possible, but since it currently syncs we can just rely on the new setter.
    *   `tokenExpirationTime` might not be considered sensitive by itself without the token, but it's part of the auth. Let's keep it in SharedPreferences since it's just a timestamp, or we can migrate it as well. The task specifically says "Insecure Storage of Authentication Tokens" and lists `authToken` and `tokenExpirationTime`. Let's migrate both, or at least `authToken`. Let's just migrate `authToken` since it's a string and the real secret. Actually, I can also migrate `tokenExpirationTime` or leave it. Wait, the prompt lists `String get authToken => ...`, `set authToken`, `int get tokenExpirationTime...`. Let's migrate only `authToken` or keep the same logic. Let's stick to `authToken`.
4. **Complete pre commit steps**
5. **Submit the change.**
