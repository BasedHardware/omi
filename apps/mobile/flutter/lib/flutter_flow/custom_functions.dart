import 'dart:convert';

DateTime? sinceLastMonth() {
  // function that returns DateTime of 24 hours ago from now
  DateTime now = DateTime.now();
  DateTime twentyFourHoursAgo = now.subtract(Duration(hours: 730));
  return twentyFourHoursAgo;
}

DateTime? sinceYesterday() {
  // function that returns DateTime of 24 hours ago from now
  DateTime now = DateTime.now();
  DateTime twentyFourHoursAgo = now.subtract(Duration(hours: 24));
  return twentyFourHoursAgo;
}

DateTime? sinceLastWeek() {
  // function that returns DateTime of 24 hours ago from now
  DateTime now = DateTime.now();
  DateTime twentyFourHoursAgo = now.subtract(Duration(hours: 168));
  return twentyFourHoursAgo;
}

DateTime? since18hoursago() {
  // function that returns DateTime of 24 hours ago from now
  DateTime now = DateTime.now();
  DateTime eighteenHoursAgo = now.subtract(Duration(hours: 24));
  return eighteenHoursAgo;
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

dynamic updateSystemPromptMemories(
  dynamic chatHistory,
  List<String> memoriesString,
) {
  // memoriesString = limitTranscript(memoriesString, 400000)!;
  String memoriesContent = memoriesString.join(" ");

  // Construct the system prompt as a Map
  Map<String, String> systemPrompt = {
    "role": "system",
    "content":
        "\\n\\n Your name is Friend and you are my helpful assistant. BELOW ARE MY MEMORIES. My memories are facts about me and things I remmember. Use these memories in your answers. MEMORIES: " +
            memoriesContent +
            "END OF MEMORIES   \\n\\n We just had a conversation with you. This is our CONVERSATION. Respond to my question in a direct specific and concise manner in the end. Before answering the question, check all my memories above and make sure you have all relevant context needed to answer the question. If there are relevant memories, use them in the conversation " +
            memoriesContent
  };

  // Map<String, String> systemPrompt = {"role": "system", "content": "bruh"};

  // Construct the system prompt as a Map
  // Map<String, String> systemPrompt = {"role": "system", "content": "hello"};

  // if (chatHistory is List) {
  //   chatHistory[0] = (systemPrompt);
  //   return chatHistory;
  // } else {
  //   return [systemPrompt];
  // }
  return updateChatHistoryAtIndex(systemPrompt, 0, chatHistory);
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

  // // If chatHistory has more than 30 items, remove the item at index 1
  // if (chatHistory.length > 30) {
  //   chatHistory.removeAt(1);
  // }

  return chatHistory;
}

dynamic convertToJSONRole(
  String? prompt,
  String? role,
) {
  String? encodedPrompt = jsonEncodeString(prompt);

  return json.decode('{"role": "$role", "content": "$encodedPrompt"}');
}

dynamic updateChatHistoryAtIndex(
  dynamic messageWithRole,
  int index,
  dynamic chatHistory,
) {
  // dynamic chatHistory = FFAppState().chatHistory;
  dynamic newChatHistory;

  // updates the chat history at a certain indexx
  if (chatHistory is List) {
    chatHistory[index] = (messageWithRole);
    newChatHistory = chatHistory;
  } else {
    newChatHistory = [messageWithRole];
  }
  return newChatHistory;
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

dynamic truncateChatHistory(dynamic ogChatHistory) {
  // If chatHistory has more than 30 items, remove the item at index 1
  int chatLength = 3;
  if (ogChatHistory.length > chatLength) {
    // Keep the first item and the last 30 items
    var truncatedChatHistory = [ogChatHistory.first] +
        ogChatHistory.sublist(ogChatHistory.length - chatLength);
    return truncatedChatHistory;
  }
  return ogChatHistory;
}

bool? stringContainsString(
  String? string,
  String? substring,
) {
  return string!.contains(substring!);
}
