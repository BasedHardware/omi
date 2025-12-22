import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/env/env.dart';

/// Check if a question was answered based on the transcript
/// Returns true if answered, false if not, null if error
Future<bool?> checkQuestionAnswered(String question, String transcript) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/onboarding/check-answer',
    headers: {},
    method: 'POST',
    body: jsonEncode({
      'question': question,
      'transcript': transcript,
    }),
  );
  if (response == null) return null;
  debugPrint('checkQuestionAnswered: ${response.body}');
  if (response.statusCode == 200) {
    final data = jsonDecode(response.body);
    return data['answered'] == true;
  }
  return null;
}

/// Create onboarding conversation with memories from answered questions
Future<ServerConversation?> createOnboardingConversation(List<Map<String, dynamic>> answeredQuestions) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/onboarding/conversation',
    headers: {},
    method: 'POST',
    body: jsonEncode({
      'questions_answers': answeredQuestions,
    }),
  );
  if (response == null) return null;
  debugPrint('createOnboardingConversation: ${response.body}');
  if (response.statusCode == 200) {
    final data = jsonDecode(response.body);
    if (data['conversation'] != null) {
      return ServerConversation.fromJson(data['conversation']);
    }
  }
  return null;
}

