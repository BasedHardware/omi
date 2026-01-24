import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/dev_api.dart';
import 'package:omi/backend/schema/dev_api_key.dart';

class DevApiKeyProvider with ChangeNotifier {
  List<DevApiKey> _keys = [];
  List<DevApiKey> get keys => _keys;

  bool _isLoading = false;
  bool get isLoading => _isLoading;

  String? _error;
  String? get error => _error;

  Future<void> fetchKeys({bool force = false}) async {
    // Don't refetch if we already have keys and force is false
    if (!force && _keys.isNotEmpty && !_isLoading) {
      return;
    }

    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _keys = await DevApi.getDevApiKeys();
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<DevApiKeyCreated?> createKey(String name, {List<String>? scopes}) async {
    // The dialog handles its own loading state. We don't set _isLoading here
    // to avoid a loading indicator on the main list view while creating.
    _error = null;

    DevApiKeyCreated? newKey;
    try {
      newKey = await DevApi.createDevApiKey(name, scopes: scopes);
      // Add the new key to the top of the list, as the API returns keys sorted by creation date.
      _keys.insert(0, newKey);
    } catch (e) {
      _error = e.toString();
    } finally {
      // Notify listeners to rebuild the UI with the new key or to reflect an error state.
      notifyListeners();
    }
    return newKey;
  }

  Future<void> deleteKey(String keyId) async {
    // Optimistically remove the key from the UI
    final keyIndex = _keys.indexWhere((key) => key.id == keyId);
    if (keyIndex == -1) return;

    final keyToRemove = _keys[keyIndex];
    _keys.removeAt(keyIndex);
    notifyListeners();

    try {
      await DevApi.deleteDevApiKey(keyId);
    } catch (e) {
      // If deletion fails, add the key back and show an error
      _keys.insert(keyIndex, keyToRemove);
      _error = e.toString();
      notifyListeners();
    }
  }
}
