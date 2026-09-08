import 'package:flutter/material.dart';

import 'package:collection/collection.dart';

import 'package:omi/backend/http/api/folders.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/utils/logger.dart';

typedef FoldersFetcher = Future<List<Folder>> Function();

class FolderProvider extends ChangeNotifier {
  List<Folder> _folders = [];
  String? _selectedFolderId;
  bool _isLoading = false;
  String? _error;
  int _sessionGeneration = 0;
  final FoldersFetcher _foldersFetcher;

  FolderProvider({FoldersFetcher? foldersFetcher}) : _foldersFetcher = foldersFetcher ?? getFolders;

  List<Folder> get folders => _folders;

  String? get selectedFolderId => _selectedFolderId;

  bool get isLoading => _isLoading;

  String? get error => _error;

  Folder? get selectedFolder => _folders.firstWhereOrNull((f) => f.id == _selectedFolderId);

  List<Folder> get systemFolders => _folders.where((f) => f.isSystem).toList();

  List<Folder> get customFolders => _folders.where((f) => !f.isSystem).toList();

  Future<void> loadFolders() async {
    final generation = _sessionGeneration;
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final folders = await _foldersFetcher();
      if (generation != _sessionGeneration) return;
      _folders = folders;
      _folders.sort((a, b) => a.order.compareTo(b.order));
    } catch (e) {
      if (generation != _sessionGeneration) return;
      Logger.debug('Error loading folders: $e');
      _error = 'Failed to load folders';
    }

    if (generation != _sessionGeneration) return;
    _isLoading = false;
    notifyListeners();
  }

  void selectFolder(String? folderId) {
    _selectedFolderId = folderId;
    notifyListeners();
  }

  void clearSelection() {
    _selectedFolderId = null;
    notifyListeners();
  }

  Future<Folder?> createFolder({required String name, String? description, String? color, String? icon}) async {
    final generation = _sessionGeneration;
    try {
      final folder = await createFolderApi(name: name, description: description, color: color, icon: icon);
      if (generation != _sessionGeneration) return null;
      if (folder != null) {
        _folders.add(folder);
        _folders.sort((a, b) => a.order.compareTo(b.order));
        notifyListeners();
        return folder;
      }
    } catch (e) {
      if (generation != _sessionGeneration) return null;
      Logger.debug('Error creating folder: $e');
      _error = 'Failed to create folder';
      notifyListeners();
    }
    return null;
  }

  Future<Folder?> updateFolder(
    String folderId, {
    String? name,
    String? description,
    String? color,
    String? icon,
  }) async {
    final generation = _sessionGeneration;
    try {
      final updatedFolder = await updateFolderApi(
        folderId,
        name: name,
        description: description,
        color: color,
        icon: icon,
      );
      if (generation != _sessionGeneration) return null;
      if (updatedFolder != null) {
        final index = _folders.indexWhere((f) => f.id == folderId);
        if (index >= 0) {
          _folders[index] = updatedFolder;
          notifyListeners();
        }
        return updatedFolder;
      }
    } catch (e) {
      if (generation != _sessionGeneration) return null;
      Logger.debug('Error updating folder: $e');
      _error = 'Failed to update folder';
      notifyListeners();
    }
    return null;
  }

  Future<bool> deleteFolder(String folderId, {String? moveToFolderId}) async {
    final generation = _sessionGeneration;
    _folders.removeWhere((f) => f.id == folderId);
    if (_selectedFolderId == folderId) {
      _selectedFolderId = moveToFolderId;
    }
    notifyListeners();
    try {
      final success = await deleteFolderApi(folderId, moveToFolderId: moveToFolderId);
      if (generation != _sessionGeneration) return false;
      if (success) {
        loadFolders();
        return true;
      } else {
        await loadFolders();
        _error = 'Failed to delete folder';
        notifyListeners();
      }
    } catch (e) {
      if (generation != _sessionGeneration) return false;
      Logger.debug('Error deleting folder: $e');
      await loadFolders();
      _error = 'Failed to delete folder';
      notifyListeners();
    }
    return false;
  }

  Future<bool> moveConversation(String conversationId, String? folderId) async {
    final generation = _sessionGeneration;
    try {
      final success = await moveConversationToFolderApi(conversationId, folderId);
      if (generation != _sessionGeneration) return false;
      if (success) {
        await loadFolders();
        return true;
      }
    } catch (e) {
      if (generation != _sessionGeneration) return false;
      Logger.debug('Error moving conversation: $e');
      _error = 'Failed to move conversation';
      notifyListeners();
    }
    return false;
  }

  Future<int> bulkMoveConversations(List<String> conversationIds, String folderId) async {
    final generation = _sessionGeneration;
    try {
      final movedCount = await bulkMoveConversationsToFolderApi(folderId, conversationIds);
      if (generation != _sessionGeneration) return 0;
      if (movedCount > 0) {
        await loadFolders();
      }
      return movedCount;
    } catch (e) {
      if (generation != _sessionGeneration) return 0;
      Logger.debug('Error bulk moving conversations: $e');
      _error = 'Failed to move conversations';
      notifyListeners();
    }
    return 0;
  }

  Future<bool> reorderFolders(List<String> folderIds) async {
    final generation = _sessionGeneration;
    try {
      final success = await reorderFoldersApi(folderIds);
      if (generation != _sessionGeneration) return false;
      if (success) {
        // Update local order
        for (int i = 0; i < folderIds.length; i++) {
          final index = _folders.indexWhere((f) => f.id == folderIds[i]);
          if (index >= 0) {
            _folders[index] = _folders[index].copyWith(order: i);
          }
        }
        _folders.sort((a, b) => a.order.compareTo(b.order));
        notifyListeners();
        return true;
      }
    } catch (e) {
      if (generation != _sessionGeneration) return false;
      Logger.debug('Error reordering folders: $e');
      _error = 'Failed to reorder folders';
      notifyListeners();
    }
    return false;
  }

  /// Get a folder by ID.
  Folder? getFolderById(String id) {
    return _folders.firstWhereOrNull((f) => f.id == id);
  }

  /// Get the default folder
  Folder? get defaultFolder => _folders.firstWhereOrNull((f) => f.isDefault);

  void clearUserData() {
    _sessionGeneration++;
    _folders = [];
    _selectedFolderId = null;
    _isLoading = false;
    _error = null;
    notifyListeners();
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }

  void updateFolderCount(String folderId, int delta) {
    final index = _folders.indexWhere((f) => f.id == folderId);
    if (index >= 0) {
      final folder = _folders[index];
      _folders[index] = folder.copyWith(
        conversationCount: (folder.conversationCount + delta).clamp(0, double.infinity).toInt(),
      );
      notifyListeners();
    }
  }
}
