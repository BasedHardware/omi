import 'dart:convert';

import 'package:flutter/material.dart';

dynamic saveChatHistory(
  dynamic chatHistory,
  dynamic newChat,
) {
  if (chatHistory is! List) {
    chatHistory = [chatHistory];
  }
  chatHistory.add(newChat);
  return chatHistory;
}

dynamic convertToJSONRole(
  String? prompt,
  String? role,
) {
  String? encodedPrompt = jsonEncodeString(prompt);
  return json.decode('{"role": "$role", "content": "$encodedPrompt"}');
}

String? jsonEncodeString(String? regularString) {
  if (regularString == null) return null;
  if (regularString.isEmpty | (regularString.length == 1)) return regularString;

  String encodedString = jsonEncode(regularString);
  debugPrint("jsonEncodeString: $encodedString");
  return encodedString.substring(1, encodedString.length - 1);
}

bool? stringContainsString(
  String? string,
  String? substring,
) {
  return string!.contains(substring!);
}

// TODO: truncate to certain token length instead of messages count
List<dynamic> retrieveMostRecentMessages(List<dynamic> ogChatHistory, {int count = 5}) {
  if (ogChatHistory.length > count) {
    return ogChatHistory.sublist(ogChatHistory.length - count);
  }
  return ogChatHistory;
}

dynamic appendToChatHistoryAtIndex(
  dynamic messageWithRole,
  int index,
  dynamic chatHistory,
) {
  // take the chat history message at index, and append content to it
  dynamic newChatHistory;

  // updates the chat history at a certain index
  if (chatHistory is List) {
    chatHistory[index]['content'] += messageWithRole['content'];
    newChatHistory = chatHistory;
  } else {
    newChatHistory = [messageWithRole];
  }
  return newChatHistory;
}
