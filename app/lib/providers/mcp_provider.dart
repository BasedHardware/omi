import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/mcp_api.dart';
import 'package:omi/backend/schema/mcp_api_key.dart';

class McpProvider with ChangeNotifier {
  List<McpApiKey> _keys = [];
  List<McpApiKey> get keys => _keys;

  bool _isLoading = false;
  bool get isLoading => _isLoading;

  String? _error;
  String? get error => _error;
  int _sessionGeneration = 0;

  Future<void> fetchKeys() async {
    final generation = _sessionGeneration;
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final keys = await McpApi.getMcpApiKeys();
      if (generation != _sessionGeneration) return;
      _keys = keys;
    } catch (e) {
      if (generation != _sessionGeneration) return;
      _error = e.toString();
    } finally {
      if (generation == _sessionGeneration) {
        _isLoading = false;
        notifyListeners();
      }
    }
  }

  Future<McpApiKeyCreated?> createKey(String name) async {
    final generation = _sessionGeneration;
    // The dialog handles its own loading state. We don't set _isLoading here
    // to avoid a loading indicator on the main list view while creating.
    _error = null;

    McpApiKeyCreated? newKey;
    try {
      newKey = await McpApi.createMcpApiKey(name);
      if (generation != _sessionGeneration) return null;
      // Add the new key to the top of the list, as the API returns keys sorted by creation date.
      _keys.insert(0, McpApiKey.fromJson(newKey.toJson()));
    } catch (e) {
      if (generation != _sessionGeneration) return null;
      _error = e.toString();
    } finally {
      // Notify listeners to rebuild the UI with the new key or to reflect an error state.
      if (generation == _sessionGeneration) notifyListeners();
    }
    return newKey;
  }

  Future<void> deleteKey(String keyId) async {
    final generation = _sessionGeneration;
    // Optimistically remove the key from the UI
    final keyIndex = _keys.indexWhere((key) => key.id == keyId);
    if (keyIndex == -1) return;

    final keyToRemove = _keys[keyIndex];
    _keys.removeAt(keyIndex);
    notifyListeners();

    try {
      await McpApi.deleteMcpApiKey(keyId);
      if (generation != _sessionGeneration) return;
    } catch (e) {
      if (generation != _sessionGeneration) return;
      // If deletion fails, add the key back and show an error
      _keys.insert(keyIndex, keyToRemove);
      _error = e.toString();
      notifyListeners();
    }
  }

  void clearUserData() {
    _sessionGeneration++;
    _keys = [];
    _isLoading = false;
    _error = null;
    notifyListeners();
  }
}
