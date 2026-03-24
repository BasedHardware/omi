import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/notes.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/note.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/logger.dart';

class NotesProvider extends ChangeNotifier {
  static NotesProvider? _instance;

  static NotesProvider get instance {
    _instance ??= NotesProvider();
    return _instance!;
  }

  static void setInstance(NotesProvider provider) {
    _instance = provider;
  }

  List<Note> _notes = [];
  bool _isLoading = false;
  bool _isFetching = false;
  bool _hasMore = true;
  String _searchQuery = '';
  NoteType? _filterType;

  // Track last deleted note for undo
  Note? _lastDeletedNote;

  // Getters
  List<Note> get notes => _notes;
  bool get isLoading => _isLoading;
  bool get isFetching => _isFetching;
  bool get hasMore => _hasMore;
  String get searchQuery => _searchQuery;
  NoteType? get filterType => _filterType;

  List<Note> get filteredNotes {
    return _notes.where((note) {
      // Apply type filter
      if (_filterType != null && note.type != _filterType) {
        return false;
      }
      // Apply search filter
      if (_searchQuery.isNotEmpty) {
        final matchesContent = note.content.toLowerCase().contains(_searchQuery.toLowerCase());
        final matchesTitle = note.title?.toLowerCase().contains(_searchQuery.toLowerCase()) ?? false;
        final matchesTranscription = note.transcription?.toLowerCase().contains(_searchQuery.toLowerCase()) ?? false;
        return matchesContent || matchesTitle || matchesTranscription;
      }
      return true;
    }).toList()
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
  }

  List<Note> get voiceNotes => filteredNotes.where((note) => note.type == NoteType.voice).toList();
  List<Note> get textNotes => filteredNotes.where((note) => note.type == NoteType.text).toList();

  NotesProvider() {
    _loadNotes();
  }

  Future<void> _loadNotes() async {
    await fetchNotes();
  }

  Future<void> fetchNotes({bool showShimmer = false}) async {
    if (showShimmer) {
      _isLoading = true;
      notifyListeners();
    } else {
      _isFetching = true;
      notifyListeners();
    }

    try {
      final fetchedNotes = await getNotes(limit: 100, offset: 0);
      _notes = fetchedNotes;
      _hasMore = fetchedNotes.length >= 100;
      MixpanelManager().notesFetched(count: fetchedNotes.length);
    } catch (e) {
      Logger.debug('Error fetching notes: $e');
    } finally {
      _isLoading = false;
      _isFetching = false;
      notifyListeners();
    }
  }

  Future<void> loadMoreNotes() async {
    if (_isFetching || !_hasMore) return;

    _isFetching = true;
    notifyListeners();

    try {
      final fetchedNotes = await getNotes(limit: 100, offset: _notes.length);
      _notes.addAll(fetchedNotes);
      _hasMore = fetchedNotes.length >= 100;
    } catch (e) {
      Logger.debug('Error loading more notes: $e');
    } finally {
      _isFetching = false;
      notifyListeners();
    }
  }

  Future<Note?> createNote({
    required String content,
    String? title,
    required NoteType type,
    double? duration,
    String? transcription,
  }) async {
    try {
      final note = await createNoteServer(
        content: content,
        title: title,
        type: type,
        duration: duration,
        transcription: transcription,
      );
      if (note != null) {
        _notes.insert(0, note);
        notifyListeners();
        MixpanelManager().noteCreated(type: type.toString());
        return note;
      }
    } catch (e) {
      Logger.debug('Error creating note: $e');
    }
    return null;
  }

  Future<bool> updateNote(
    String noteId, {
    String? content,
    String? title,
    double? duration,
    String? transcription,
  }) async {
    try {
      final success = await updateNoteServer(
        noteId,
        content: content,
        title: title,
        duration: duration,
        transcription: transcription,
      );
      if (success) {
        final index = _notes.indexWhere((n) => n.id == noteId);
        if (index != -1) {
          final oldNote = _notes[index];
          _notes[index] = oldNote.copyWith(
            content: content ?? oldNote.content,
            title: title ?? oldNote.title,
            duration: duration ?? oldNote.duration,
            transcription: transcription ?? oldNote.transcription,
            edited: true,
            updatedAt: DateTime.now(),
          );
          notifyListeners();
          MixpanelManager().noteUpdated(noteId: noteId);
        }
        return true;
      }
    } catch (e) {
      Logger.debug('Error updating note: $e');
    }
    return false;
  }

  Future<bool> deleteNote(String noteId) async {
    try {
      final success = await deleteNoteServer(noteId);
      if (success) {
        // Store for undo
        _lastDeletedNote = _notes.firstWhere((n) => n.id == noteId);
        _notes.removeWhere((n) => n.id == noteId);
        notifyListeners();
        MixpanelManager().noteDeleted(noteId: noteId);
        return true;
      }
    } catch (e) {
      Logger.debug('Error deleting note: $e');
    }
    return false;
  }

  Future<bool> restoreLastDeletedNote() async {
    if (_lastDeletedNote == null) return false;

    try {
      final note = await createNoteServer(
        content: _lastDeletedNote!.content,
        title: _lastDeletedNote!.title,
        type: _lastDeletedNote!.type,
        visibility: _lastDeletedNote!.visibility,
        duration: _lastDeletedNote!.duration,
        transcription: _lastDeletedNote!.transcription,
      );
      if (note != null) {
        _notes.insert(0, note);
        notifyListeners();
        _lastDeletedNote = null;
        return true;
      }
    } catch (e) {
      Logger.debug('Error restoring note: $e');
    }
    return false;
  }

  void setSearchQuery(String query) {
    _searchQuery = query;
    notifyListeners();
  }

  void setFilterType(NoteType? type) {
    _filterType = type;
    notifyListeners();
  }

  void clearFilters() {
    _searchQuery = '';
    _filterType = null;
    notifyListeners();
  }

  Future<void> refresh() async {
    await fetchNotes();
  }
}
