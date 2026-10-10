import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/http_pool_manager.dart';
import 'package:omi/backend/models/memories.dart';

/// Creates a new memory on the server.
///
/// The function first POSTs the memory payload to `/v3/memories`.  
/// After a successful POST, it attempts to GET the newly created memory
/// back from the server so that the client can work with the canonical
/// representation (e.g. the server‑generated `id`).  
/// If the GET fails (e.g. the server returns a 503), the original
/// [Memory] object that was POSTed is returned instead of `null`.  
/// This change ensures that the client treats the memory as *saved* even
/// when the read‑back fails, which fixes the issue where a memory was
/// written but the UI still considered it unsaved.
Future<Memory?> createMemoryServer(Memory memory) async {
  final uri = Uri.parse('https://api.example.com/v3/memories');
  final body = jsonEncode(memory.toJson());

  // POST the memory
  final postResponse = await HttpPoolManager.instance.post(
    uri,
    headers: {'Content-Type': 'application/json'},
    body: body,
  );

  if (postResponse.statusCode != 200 && postResponse.statusCode != 201) {
    // POST failed – nothing was written
    return null;
  }

  // Extract the ID from the POST response (the server may return it)
  final postData = jsonDecode(postResponse.body);
  final String? id = postData['id']?.toString();

  // If the server didn't return an ID, we cannot fetch it back
  if (id == null) {
    // Return the original memory – it was written successfully
    return memory;
  }

  // Attempt to GET the memory back
  final getUri = Uri.parse('https://api.example.com/v3/memories/$id');
  final getResponse = await HttpPoolManager.instance.get(getUri);

  if (getResponse.statusCode == 200) {
    final getData = jsonDecode(getResponse.body);
    return Memory.fromJson(getData);
  }

  // GET failed – return the original memory instead of null
  return memory;
}

/// Deletes a memory from the server.
Future<bool> deleteMemoryServer(String memoryId) async {
  final uri = Uri.parse('https://api.example.com/v3/memories/$memoryId');
  final response = await HttpPoolManager.instance.delete(uri);
  return response.statusCode == 200 || response.statusCode == 204;
}
