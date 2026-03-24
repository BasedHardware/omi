import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/note.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

Future<Note?> createNoteServer({
  required String content,
  String? title,
  required NoteType type,
  NoteVisibility visibility = NoteVisibility.private_,
  double? duration,
  String? transcription,
}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/notes',
    headers: {},
    method: 'POST',
    body: json.encode({
      'content': content,
      'title': title,
      'type': type.toString().split('.').last,
      'visibility': visibility.name,
      'duration': duration,
      'transcription': transcription,
    }),
  );
  if (response == null) return null;
  Logger.debug('createNote response: ${response.body}');
  if (response.statusCode == 200) {
    return Note.fromJson(json.decode(response.body));
  }
  return null;
}

Future<List<Note>> getNotes({int limit = 100, int offset = 0, NoteType? type}) async {
  String url = '${Env.apiBaseUrl}v3/notes?limit=$limit&offset=$offset';
  if (type != null) {
    url += '&type=${type.toString().split('.').last}';
  }
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    if (decoded is List) {
      return decoded.map((e) => Note.fromJson(e)).toList();
    }
  }
  return [];
}

Future<Note?> getNoteById(String noteId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/notes/$noteId',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  if (response.statusCode == 200) {
    return Note.fromJson(json.decode(response.body));
  }
  return null;
}

Future<bool> updateNoteServer(
  String noteId, {
  String? content,
  String? title,
  NoteVisibility? visibility,
  double? duration,
  String? transcription,
}) async {
  final body = <String, dynamic>{};
  if (content != null) body['content'] = content;
  if (title != null) body['title'] = title;
  if (visibility != null) body['visibility'] = visibility.name;
  if (duration != null) body['duration'] = duration;
  if (transcription != null) body['transcription'] = transcription;

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/notes/$noteId',
    headers: {},
    method: 'PATCH',
    body: json.encode(body),
  );
  if (response == null) return false;
  Logger.debug('updateNote response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> deleteNoteServer(String noteId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/notes/$noteId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  Logger.debug('deleteNote response: ${response.body}');
  return response.statusCode == 200;
}

Future<List<Note>> searchNotes(String query) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v3/notes/search?q=${Uri.encodeComponent(query)}',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    if (decoded is List) {
      return decoded.map((e) => Note.fromJson(e)).toList();
    }
  }
  return [];
}
