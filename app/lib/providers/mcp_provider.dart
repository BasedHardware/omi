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

  Future<void> fetchKeys() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _keys = await McpApi.getMcpApiKeys();
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<McpApiKeyCreated?> createKey(String name) async {
    // The dialog handles its own loading state. We don't set _isLoading here
    // to avoid a loading indicator on the main list view while creating.
    _error = null;

    McpApiKeyCreated? newKey;
    try {
      newKey = await McpApi.createMcpApiKey(name);
      if (newKey != null) {
        // Add the new key to the top of the list, as the API returns keys sorted by creation date.
        _keys.insert(0, newKey);
      }
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
      await McpApi.deleteMcpApiKey(keyId);
    } catch (e) {
      // If deletion fails, add the key back and show an error
      _keys.insert(keyIndex, keyToRemove);
      _error = e.toString();
      notifyListeners();
    }
  }
}
