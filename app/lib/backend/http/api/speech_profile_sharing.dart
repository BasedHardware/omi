import 'dart:convert';
import 'package:omi/env/env.dart';
import 'package:omi/backend/http/shared.dart';

Future<bool> shareSpeechProfile(String targetUid) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile/share',
    headers: {},
    method: 'POST',
    body: jsonEncode({'target_uid': targetUid}),
  );
  return response != null && response.statusCode == 200;
}

Future<bool> revokeSpeechProfile(String targetUid) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile/revoke',
    headers: {},
    method: 'POST',
    body: jsonEncode({'target_uid': targetUid}),
  );
  return response != null && response.statusCode == 200;
}

Future<List<String>> getProfilesSharedWithMe() async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile/shared-with-me',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response != null && response.statusCode == 200) {
    final data = jsonDecode(response.body);
    return List<String>.from(data['shared_with_me'] ?? []);
  }
  return [];
}

Future<List<String>> getUsersIHaveSharedWith() async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/speech-profile/i-have-shared',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response != null && response.statusCode == 200) {
    final data = jsonDecode(response.body);
    return List<String>.from(data['i_have_shared_with'] ?? []);
  }
  return [];
}
