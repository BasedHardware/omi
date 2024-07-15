import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/llm.dart';
import 'package:friend_private/backend/api_requests/api/shared.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/env.dart';

Future<dynamic> pineconeApiCall({required String urlSuffix, required String body}) async {
  var url = '${Env.pineconeIndexUrl}/$urlSuffix';
  final headers = {
    'Api-Key': Env.pineconeApiKey,
    'Content-Type': 'application/json',
  };
  var response = await makeApiCall(url: url, headers: headers, body: body, method: 'POST');
  var responseBody = jsonDecode(response?.body ?? '{}');
  return responseBody;
}

Future<void> updatePineconeMemoryId(String memoryId, int newId) {
  return pineconeApiCall(
      urlSuffix: 'vectors/update',
      body: jsonEncode({
        'id': memoryId,
        'setMetadata': {'memory_id': newId.toString()},
        'namespace': Env.pineconeIndexNamespace,
      }));
}

Future<bool> upsertPineconeVector(String memoryId, List<double> vectorList, DateTime createdAt) async {
  var body = jsonEncode({
    'vectors': [
      {
        'id': '${SharedPreferencesUtil().uid}-$memoryId',
        'values': vectorList,
        'metadata': {
          'created_at': createdAt.millisecondsSinceEpoch ~/ 1000,
          'memory_id': memoryId,
          'uid': SharedPreferencesUtil().uid,
        }
      }
    ],
    'namespace': Env.pineconeIndexNamespace
  });
  var responseBody = await pineconeApiCall(urlSuffix: 'vectors/upsert', body: body);
  debugPrint('upsertPineconeVector response: $responseBody');
  return (responseBody['upserted_count'] ?? 0) > 0;
}

/// Queries Pinecone vectors and optionally filters results based on a date range.
/// The startTimestamp and endTimestamp should be provided as UNIX epoch timestamps in seconds.
/// For example: 1622520000 represents Jun 01 2021 10:00:00 UTC.

Future<List<String>> queryPineconeVectors(
  List<double> vectorList, {
  int? startTimestamp,
  int? endTimestamp,
  int count = 5,
}) async {
  // Constructing the filter condition based on optional timestamp parameters
  // 2024-06-01 00:00:00.000, 2024-06-28 16:41:05.456149
  Map<String, dynamic> filter = {
    'uid': {'\$eq': SharedPreferencesUtil().uid},
  };

  // Add date filtering if startTimestamp or endTimestamp is provided
  if (startTimestamp != null || endTimestamp != null) filter['created_at'] = {};
  if (startTimestamp != null) filter['created_at']['\$gte'] = startTimestamp;
  if (endTimestamp != null) filter['created_at']['\$lte'] = endTimestamp;

  debugPrint('queryPineconeVectors filter: $filter');

  var body = jsonEncode({
    'namespace': Env.pineconeIndexNamespace,
    'vector': vectorList,
    'topK': count,
    'includeValues': false,
    'includeMetadata': true,
    'filter': filter,
  });
  var responseBody = await pineconeApiCall(urlSuffix: 'query', body: body);
  debugPrint(responseBody.toString());
  return (responseBody['matches'])?.map<String>((e) => e['metadata']['memory_id'].toString()).toList() ?? [];
}

Future<bool> deleteVector(String memoryId) async {
  var body = jsonEncode({
    'ids': [memoryId],
    'namespace': Env.pineconeIndexNamespace
  });
  var response = await pineconeApiCall(urlSuffix: 'vectors/delete', body: body);
  debugPrint(response.toString());
  return true;
}
// TODO: update vectors when fields updated

Future<List<double>> getEmbeddingsFromInput(String input) async {
  var vector = await gptApiCall(
    model: 'text-embedding-3-large',
    urlSuffix: 'embeddings',
    contentToEmbed: input,
  );
  return vector.map<double>((item) => double.tryParse(item.toString()) ?? 0.0).toList();
}
