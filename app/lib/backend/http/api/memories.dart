import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/env/env.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:tuple/tuple.dart';

Future<bool> migrateMemoriesToBackend(List<dynamic> memories) async {
  // Log the request data
  final requestBody = jsonEncode(memories);
  final requestUrl = '${Env.apiBaseUrl}v1/migration/memories';

  print('migrateMemoriesToBackend Request URL: $requestUrl');
  print('migrateMemoriesToBackend Request Method: POST');
  print('migrateMemoriesToBackend Request Headers: {Content-Type: application/json}');
  print('migrateMemoriesToBackend Request Body: $requestBody');

  // Make the API call
  var response = await makeApiCall(
    url: requestUrl,
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: requestBody,
  );

  // Check if response is null
  if (response == null) {
    print('migrateMemoriesToBackend: No response received.');
    return false;
  }

  // Log the response status code and body
  print('migrateMemoriesToBackend Response Status Code: ${response.statusCode}');
  print('migrateMemoriesToBackend Response Body: ${response.body}');

  // Return true if the status code is 200, else false
  return response.statusCode == 200;
}

Future<CreateMemoryResponse?> createMemoryServer({
  required DateTime startedAt,
  required DateTime finishedAt,
  required List<TranscriptSegment> transcriptSegments,
  Geolocation? geolocation,
  List<Tuple2<String, String>> photos = const [],
  bool triggerIntegrations = true,
  String? language,
}) async {
  // Construct the request body
  final requestBody = jsonEncode({
    'started_at': startedAt.toIso8601String(),
    'finished_at': finishedAt.toIso8601String(),
    'transcript_segments':
    transcriptSegments.map((segment) => segment.toJson()).toList(),
    'geolocation': geolocation?.toJson(),
    'photos': photos
        .map((photo) => {'base64': photo.item1, 'description': photo.item2})
        .toList(),
    'source': transcriptSegments.isNotEmpty ? 'friend' : 'openglass',
    'language': language, // maybe determine auto?
  });

  // Log the request details
  final url = '${Env.apiBaseUrl}v1/memories?trigger_integrations=$triggerIntegrations';
  print('createMemoryServer Request URL: $url');
  print('createMemoryServer Request Method: POST');
  print('createMemoryServer Request Headers: {}');  // Replace with actual headers if needed
  print('createMemoryServer Request Body: $requestBody');

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'POST',
    body: requestBody,
  );

  // Check if response is null
  if (response == null) {
    print('createMemoryServer: No response received.');
    return null;
  }

  // Log the response status code and body
  print('createMemoryServer Response Status Code: ${response.statusCode}');
  print('createMemoryServer Response Body: ${response.body}');

  // Handle the response
  if (response.statusCode == 200) {
    return CreateMemoryResponse.fromJson(jsonDecode(response.body));
  } else {
    // Report an error
    CrashReporting.reportHandledCrash(
      Exception('Failed to create memory'),
      StackTrace.current,
      level: NonFatalExceptionLevel.info,
      userAttributes: {
        'response': response.body,
        'transcriptSegments': TranscriptSegment.segmentsAsString(transcriptSegments),
      },
    );
  }

  return null;
}

Future<List<ServerMemory>> getMemories({int limit = 50, int offset = 0}) async {
  // Construct the request URL
  final url = '${Env.apiBaseUrl}v1/memories?limit=$limit&offset=$offset';

  // Log the request details
  print('getMemories Request URL: $url');
  print('getMemories Request Method: GET'); // No headers in this case
  print('getMemories Request Body: ');  // Empty body for GET request

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'GET',
    body: '',
  );

  // Log the response details
  print('getMemories Response Status Code: ${response?.statusCode}');
  print('getMemories Response Body: ${response?.body}');

  // Check if response is null and handle the response
  if (response == null) {
    print('getMemories: No response received.');
    return [];
  }

  // Handle the response
  if (response.statusCode == 200) {
    try {
      var memories = (jsonDecode(response.body) as List<dynamic>)
          .map((memory) => ServerMemory.fromJson(memory))
          .toList();
      print('getMemories length: ${memories.length}');
      return memories;
    } catch (e) {
      print('getMemories: Error decoding JSON - $e');
    }
  } else {
    print('getMemories: Error with status code ${response.statusCode}');
  }

  return [];
}

Future<ServerMemory?> reProcessMemoryServer(String memoryId) async {
  // Construct the request URL
  final url = '${Env.apiBaseUrl}v1/memories/$memoryId/reprocess';

  // Log the request details
  print('reProcessMemoryServer Request URL: $url');
  print('reProcessMemoryServer Request Method: POST');
  print('reProcessMemoryServer Request Headers: {}');  // No headers in this case
  print('reProcessMemoryServer Request Body: ');  // Empty body for this request

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'POST',
    body: '',
  );

  // Check if response is null
  if (response == null) {
    print('reProcessMemoryServer: No response received.');
    return null;
  }

  // Log the response status code and body
  print('reProcessMemoryServer Response Status Code: ${response.statusCode}');
  print('reProcessMemoryServer Response Body: ${response.body}');

  // Handle the response
  if (response.statusCode == 200) {
    try {
      return ServerMemory.fromJson(jsonDecode(response.body));
    } catch (e) {
      print('reProcessMemoryServer: Error decoding JSON - $e');
    }
  }

  return null;
}

Future<bool> deleteMemoryServer(String memoryId) async {
  // Construct the request URL
  final url = '${Env.apiBaseUrl}v1/memories/$memoryId';

  // Log the request details
  print('deleteMemoryServer Request URL: $url');
  print('deleteMemoryServer Request Method: DELETE');
  print('deleteMemoryServer Request Headers: {}');  // No headers in this case
  print('deleteMemoryServer Request Body: ');  // Empty body for this request

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'DELETE',
    body: '',
  );

  // Check if response is null
  if (response == null) {
    print('deleteMemoryServer: No response received.');
    return false;
  }

  // Log the response status code
  print('deleteMemoryServer Response Status Code: ${response.statusCode}');

  // Return true if the status code is 204 (No Content), else false
  return response.statusCode == 204;
}

Future<ServerMemory?> getMemoryById(String memoryId) async {
  // Construct the request URL
  final url = '${Env.apiBaseUrl}v1/memories/$memoryId';

  // Log the request details
  print('getMemoryById Request URL: $url');
  print('getMemoryById Request Method: GET');
  print('getMemoryById Request Headers: {}');  // No headers in this case
  print('getMemoryById Request Body: ');  // Empty body for this request

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'GET',
    body: '',
  );

  // Check if response is null
  if (response == null) {
    print('getMemoryById: No response received.');
    return null;
  }

  // Log the response status code and body
  print('getMemoryById Response Status Code: ${response.statusCode}');
  print('getMemoryById Response Body: ${response.body}');

  // Handle the response
  if (response.statusCode == 200) {
    try {
      return ServerMemory.fromJson(jsonDecode(response.body));
    } catch (e) {
      print('getMemoryById: Error decoding JSON - $e');
    }
  }

  return null;
}

Future<List<MemoryPhoto>> getMemoryPhotos(String memoryId) async {
  // Construct the request URL
  final url = '${Env.apiBaseUrl}v1/memories/$memoryId/photos';

  // Log the request details
  print('getMemoryPhotos Request URL: $url');
  print('getMemoryPhotos Request Method: GET');
  print('getMemoryPhotos Request Headers: {}');  // No headers in this case
  print('getMemoryPhotos Request Body: ');  // Empty body for this request

  // Make the API call
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'GET',
    body: '',
  );

  // Check if response is null
  if (response == null) {
    print('getMemoryPhotos: No response received.');
    return [];
  }

  // Log the response status code and body
  print('getMemoryPhotos Response Status Code: ${response.statusCode}');
  print('getMemoryPhotos Response Body: ${response.body}');

  // Handle the response
  if (response.statusCode == 200) {
    try {
      return (jsonDecode(response.body) as List<dynamic>)
          .map((photo) => MemoryPhoto.fromJson(photo))
          .toList();
    } catch (e) {
      print('getMemoryPhotos: Error decoding JSON - $e');
    }
  }

  return [];
}
