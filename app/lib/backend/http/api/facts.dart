import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/fact.dart';
import 'package:omi/env/env.dart';

Future<bool> createFactServer(String content, String visibility) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/facts',
    headers: {},
    method: 'POST',
    body: json.encode({
      'content': content,
      'visibility': visibility,
    }),
  );
  if (response == null) return false;
  debugPrint('createFact response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> updateFactVisibilityServer(String factId, String visibility) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/facts/$factId/visibility?value=$visibility',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  debugPrint('updateFactVisibility response: ${response.body}');
  return response.statusCode == 200;
}

Future<List<Fact>> getFacts({int limit = 100, int offset = 0}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/facts?limit=$limit&offset=$offset',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  debugPrint('getFacts response: ${response.body}');
  List<dynamic> facts = json.decode(response.body);
  return facts.map((fact) => Fact.fromJson(fact)).toList();
}

Future<bool> deleteFactServer(String factId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/facts/$factId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  debugPrint('deleteFact response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> deleteAllFactServer() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/facts',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  debugPrint('deleteFact response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> reviewFactServer(String factId, bool value) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/facts/$factId/review?value=$value',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return false;
  debugPrint('reviewFact response: ${response.body}');
  return response.statusCode == 200;
}

Future<bool> editFactServer(String factId, String value) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/facts/$factId?value=$value',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return false;
  debugPrint('editFact response: ${response.body}');
  return response.statusCode == 200;
}
