import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/database/message_provider.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:tuple/tuple.dart';

Future<List<dynamic>> retrieveRAGContext(String message, {String? prevMessagesPluginId}) async {
  var prevMessages = await MessageProvider().retrieveMostRecentMessages(limit: 10, pluginId: prevMessagesPluginId);
  Tuple2<List<String>, List<DateTime>>? ragContext = await determineRequiresContext(prevMessages);
  debugPrint('_retrieveRAGContext betterContextQuestion: $ragContext');
  if (ragContext == null || (ragContext.item1.isEmpty && ragContext.item2.isEmpty)) {
    return ['', []];
  }
  List<String> topics = ragContext.item1;
  List<DateTime> datesRange = ragContext.item2;
  var startTimestamp = datesRange.isNotEmpty ? datesRange[0].millisecondsSinceEpoch ~/ 1000 : null;
  var endTimestamp = datesRange.isNotEmpty ? datesRange[1].millisecondsSinceEpoch ~/ 1000 : null;

  // TODO: how to show all the memories used in the chat, maybe a expand toggle?
  Future<List<List<String>>> memoriesByTopic = _retrieveMemoriesByTopic(topics, startTimestamp, endTimestamp, message);
  List<Memory> memories = [];
  if (topics.isNotEmpty) {
    List<List<String>> memoriesIdList = await memoriesByTopic;
    List<String> memoriesId = memoriesIdList.reduce((value, element) => value + element).toSet().toList();
    debugPrint('queryPineconeVectors memories from topics: ${memoriesId.length}');
    List<int> memoriesIdAsInt = memoriesId.map((e) => int.tryParse(e) ?? -1).where((e) => e != -1).toList();
    memories = MemoryProvider().getMemoriesById(memoriesIdAsInt);
  }

  if (topics.isEmpty && datesRange.isNotEmpty) {
    memories = MemoryProvider().retrieveMemoriesWithinDates(datesRange[0], datesRange[1]);
    debugPrint('queryPineconeVectors memories from dates: ${memories.length}');
  }

  // String context = '';
  // for (var memory in memories) {
  //   String transcript = memory.transcript;
  //   if (transcript.split(' ').length > 2000) {
  //     transcript = transcript.substring(0, 2000); // SHORTER GPT VERSION
  //   }
  //   context += '''
  //     ${memory.createdAt.toIso8601String().split('.')[0]}
  //     Transcript: $transcript
  //     ''';
  // }

  return [Memory.memoriesToString(memories), memories];
}

Future<List<List<String>>> _retrieveMemoriesByTopic(
  List<String> topics,
  int? startTimestamp,
  int? endTimestamp,
  String message,
) {
  return Future.wait(topics.map((topic) async {
    try {
      List<double> vectorizedMessage = await getEmbeddingsFromInput(topic);
      List<String> memoriesId = await queryPineconeVectors(
        vectorizedMessage,
        startTimestamp: startTimestamp,
        endTimestamp: endTimestamp,
        count: 5,
      );
      debugPrint('queryPineconeVectors memories retrieved for topic $topic: ${memoriesId.length}');
      return memoriesId;
    } catch (e, stacktrace) {
      CrashReporting.reportHandledCrash(e, stacktrace, level: NonFatalExceptionLevel.error, userAttributes: {
        'message_length': message.length.toString(),
        'topics_count': topics.length.toString(),
        // 'topic_failed': topic,
        // TODO: would it be okay to the vectorizedMessage instead? so we can replicate without knowing the message
      });
      return [];
    }
  }));
}
