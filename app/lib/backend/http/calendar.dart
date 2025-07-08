import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/preferences.dart';

Future<String?> initiateGoogleCalendarAuth() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/calendar/auth',
    headers: {},
    method: 'GET',
  );
  
  if (response == null) return null;
  
  var data = jsonDecode(response.body);
  return data['auth_url'];
}

Future<Map<String, dynamic>?> getCalendarStatus() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/calendar/status',
    headers: {},
    method: 'GET',
  );
  
  if (response == null) return null;
  
  return jsonDecode(response.body);
}

Future<Map<String, dynamic>?> getCalendarConfig() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/calendar/config',
    headers: {},
    method: 'GET',
  );
  
  if (response == null) return null;
  
  return jsonDecode(response.body);
}

Future<bool> updateCalendarConfig(Map<String, dynamic> config) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/calendar/config',
    headers: {'Content-Type': 'application/json'},
    method: 'PUT',
    body: jsonEncode(config),
  );
  
  return response?.statusCode == 200;
}

Future<bool> disconnectCalendar() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/calendar/disconnect',
    headers: {},
    method: 'DELETE',
  );
  
  return response?.statusCode == 200;
}

Future<List<Map<String, dynamic>>> getUpcomingEvents({int daysAhead = 30}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/calendar/events?days_ahead=$daysAhead',
    headers: {},
    method: 'GET',
  );
  
  if (response == null) return [];
  
  var data = jsonDecode(response.body);
  return List<Map<String, dynamic>>.from(data['events'] ?? []);
}

Future<Map<String, dynamic>?> createCalendarEvent({
  required String summary,
  String? description,
  required DateTime startTime,
  required DateTime endTime,
  String timezone = 'UTC',
  List<String>? attendees,
  String? location,
}) async {
  var eventData = {
    'summary': summary,
    'description': description,
    'start_time': startTime.toIso8601String(),
    'end_time': endTime.toIso8601String(),
    'timezone': timezone,
    'attendees': attendees ?? [],
    'location': location,
  };
  
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/calendar/events',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode(eventData),
  );
  
  if (response == null) return null;
  
  return jsonDecode(response.body);
}

Future<Map<String, dynamic>?> testCalendarIntegration() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/calendar/test',
    headers: {},
    method: 'GET',
  );
  
  if (response == null) return null;
  
  return jsonDecode(response.body);
}