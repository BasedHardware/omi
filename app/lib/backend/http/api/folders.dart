import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/env/env.dart';

Future<List<Folder>> getFolders() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/folders',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    var folders = (jsonDecode(body) as List<dynamic>).map((folder) => Folder.fromJson(folder)).toList();
    debugPrint('getFolders length: ${folders.length}');
    return folders;
  } else {
    debugPrint('getFolders error ${response.statusCode}');
  }
  return [];
}

/// Create a new custom folder.
Future<Folder?> createFolderApi({
  required String name,
  String? description,
  String? color,
  String? icon,
}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/folders',
    headers: {},
    method: 'POST',
    body: jsonEncode({
      'name': name,
      if (description != null) 'description': description,
      if (color != null) 'color': color,
      if (icon != null) 'icon': icon,
    }),
  );
  if (response == null) return null;
  debugPrint('createFolderApi: ${response.body}');
  if (response.statusCode == 200) {
    return Folder.fromJson(jsonDecode(response.body));
  }
  return null;
}

/// Update folder metadata.
Future<Folder?> updateFolderApi(
  String folderId, {
  String? name,
  String? description,
  String? color,
  String? icon,
  int? order,
}) async {
  final Map<String, dynamic> body = {};
  if (name != null) body['name'] = name;
  if (description != null) body['description'] = description;
  if (color != null) body['color'] = color;
  if (icon != null) body['icon'] = icon;
  if (order != null) body['order'] = order;

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/folders/$folderId',
    headers: {},
    method: 'PATCH',
    body: jsonEncode(body),
  );
  if (response == null) return null;
  debugPrint('updateFolderApi: ${response.body}');
  if (response.statusCode == 200) {
    return Folder.fromJson(jsonDecode(response.body));
  }
  return null;
}

/// Delete a folder and move its conversations to another folder.
Future<bool> deleteFolderApi(String folderId, {String? moveToFolderId}) async {
  String url = '${Env.apiBaseUrl}v1/folders/$folderId';
  if (moveToFolderId != null) {
    url += '?move_to_folder_id=$moveToFolderId';
  }

  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  debugPrint('deleteFolderApi: ${response.statusCode}');
  return response.statusCode == 204;
}

/// Move a conversation to a different folder.
Future<bool> moveConversationToFolderApi(
  String conversationId,
  String? folderId,
) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/folder',
    headers: {},
    method: 'PATCH',
    body: jsonEncode({'folder_id': folderId}),
  );
  if (response == null) return false;
  debugPrint('moveConversationToFolderApi: ${response.body}');
  return response.statusCode == 200;
}

/// Bulk move multiple conversations to a folder.
Future<int> bulkMoveConversationsToFolderApi(
  String folderId,
  List<String> conversationIds,
) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/folders/$folderId/conversations/bulk-move',
    headers: {},
    method: 'POST',
    body: jsonEncode({'conversation_ids': conversationIds}),
  );
  if (response == null) return 0;
  debugPrint('bulkMoveConversationsToFolderApi: ${response.body}');
  if (response.statusCode == 200) {
    return jsonDecode(response.body)['moved_count'] ?? 0;
  }
  return 0;
}

/// Reorder folders by providing an ordered list of folder IDs.
Future<bool> reorderFoldersApi(List<String> folderIds) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/folders/reorder',
    headers: {},
    method: 'POST',
    body: jsonEncode({'folder_ids': folderIds}),
  );
  if (response == null) return false;
  debugPrint('reorderFoldersApi: ${response.body}');
  return response.statusCode == 200;
}
