import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import 'package:timeago/timeago.dart' as timeago;
import 'lat_lng.dart';
import 'place.dart';
import 'uploaded_file.dart';
import '/backend/backend.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '/backend/schema/structs/index.dart';
import '/backend/schema/enums/enums.dart';
import '/auth/firebase_auth/auth_util.dart';

dynamic chatGPTConverter(String? message) {
  // null safety
  message ??= '';

  List<dynamic> result = [];

  // add the role
  result.add({"role": "user", "content": message});
  print(result);
  return result;
}

String? jsonToText(String? json) {
  if (json == null) {
    return null;
  }
  print("[DEBUG]: $json");
  print(json);

  // Decode JSON
  Map<String, dynamic> jsonMap = jsonDecode(json);

  // Navigate to the 'content' field
  final String? content = jsonMap['choices']?[0]['message']['content'];

  if (content == null) {
    return null;
  }
  // Remove trailing spaces
  String trimmed = content.trim();

  // Remove punctuation except for slashes
  String stripped = trimmed.replaceAll(RegExp(r'[^\w\s/]'), '');

  return stripped;
}

DateTime? sinceLastMonth() {
  // function that returns DateTime of 24 hours ago from now
  DateTime now = DateTime.now();
  DateTime twentyFourHoursAgo = now.subtract(Duration(hours: 730));
  return twentyFourHoursAgo;
}

bool voiceCommand(
  String input,
  List<String> validCommands,
) {
  String lowerCaseInput = input.toLowerCase();
  // List<String> commands = ["hey sama", "hey sam"]; // Add your commands here

  for (String command in validCommands) {
    if (lowerCaseInput.contains(command)) {
      print("Command detected: " + command);

      // Remove the command from the transcript
      return true;
    }
  }

  // Optional: Handle the case where no command is found
  print("No command detected");
  return false;
}

DateTime? sinceYesterday() {
  // function that returns DateTime of 24 hours ago from now
  DateTime now = DateTime.now();
  DateTime twentyFourHoursAgo = now.subtract(Duration(hours: 24));
  return twentyFourHoursAgo;
}

String? limitTranscript(
  String transcript,
  int maxChars,
) {
  // const int maxChars = 12000; // abt 2000 words
  if (transcript.length > maxChars) {
    // If the transcript is longer than maxChars, return the last maxChars characters
    return transcript.substring(transcript.length - maxChars);
  }
  return transcript; // If the transcript is shorter than maxChars, return the whole transcript
}

DateTime? sinceLastWeek() {
  // function that returns DateTime of 24 hours ago from now
  DateTime now = DateTime.now();
  DateTime twentyFourHoursAgo = now.subtract(Duration(hours: 168));
  return twentyFourHoursAgo;
}

dynamic updateSystemPromptMemories(
  dynamic chatHistory,
  String memoriesString,
  String currentConversation,
) {
  memoriesString = limitTranscript(memoriesString, 400000)!; // for debug

  // Construct the system prompt as a Map
  Map<String, String> systemPrompt = {
    "role": "system",
    "content": '''
    Your name is Comind and you are a harsh, toxic, honest mentor. BELOW ARE MY MEMORIES. 
    My memories are interesting facts that I learned and everything that happened in my life. 
    Personalize your answers in a specific concise way based on my MEMORIES:    $memoriesString 
    \n\n and these are few last things I mentioned: $currentConversation \n\n We just had a conversation with you. 
    This is our previous CONVERSATION. Respond to my question in a direct specific and concise manner in the end. 
    Before answering the question, make sure you have all relevant context needed to answer the question . 
    If you don't have enough context, ask me more questions. Once you asked questions, check if it's enough to answer my question. 
    If enough, answer it, if not enough, ask more questions:  
    '''
  };
  debugPrint('updateSystemPromptMemories: $systemPrompt');
  var updatedChat = updateChatHistoryAtIndex(systemPrompt, 0, chatHistory);
  debugPrint('updateSystemPromptMemories: $updatedChat');
  return updatedChat;
}

String? jsonEncodeString(String? regularString) {
  if (regularString == null) return null;

  String encodedString = jsonEncode(regularString);
  print("DEBUGJSON: " + encodedString);

  // Remove the first and last character which are the double quotes
  if (encodedString.length > 1) {
    return encodedString.substring(1, encodedString.length - 1);
  }

  return regularString; // Return the original string if it's empty or just one character
}

DateTime? since18hoursago() {
  // function that returns DateTime of 24 hours ago from now
  DateTime now = DateTime.now();
  DateTime eighteenHoursAgo = now.subtract(Duration(hours: 24));
  return eighteenHoursAgo;
}

int wordCount(String? input) {
  // Check if the input is null or empty
  if (input == null || input.isEmpty) {
    return 0;
  }

  // Split the string by spaces and count the elements
  List<String> words = input.split(RegExp(r'\s+'));
  return words.length;
}

dynamic convertToJSONRole(
  String? prompt,
  String? role,
) {
  String? encodedPrompt = jsonEncodeString(prompt);

  return json.decode('{"role": "$role", "content": "$encodedPrompt"}');
}

dynamic saveChatHistory(
  dynamic chatHistory,
  dynamic newChat,
) {
  // Ensure chatHistory is a list
  if (chatHistory is! List) {
    chatHistory = [chatHistory];
  }
  // Add newChat to chatHistory
  chatHistory.add(newChat);
  return chatHistory;
}

bool? stringContainsString(
  String? string,
  String? substring,
) {
  return string!.contains(substring!);
}

List<dynamic> retrieveMostRecentMessages(List<dynamic> ogChatHistory, {int count = 5}) {
  // TODO: truncate to certain token length instead of messages count
  if (ogChatHistory is List) {
    if (ogChatHistory.length > count) {
      return ogChatHistory.sublist(ogChatHistory.length - count);
    }
  }
  return ogChatHistory;
}

dynamic updateChatHistoryAtIndex(
  dynamic messageWithRole,
  int index,
  dynamic chatHistory,
) {
  // dynamic chatHistory = FFAppState().chatHistory;
  dynamic newChatHistory;

  // updates the chat history at a certain index
  if (chatHistory is List) {
    chatHistory[index] = (messageWithRole);
    newChatHistory = chatHistory;
  } else {
    newChatHistory = [messageWithRole];
  }
  return newChatHistory;
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
