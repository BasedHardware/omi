import 'package:flutter/material.dart';
import '/auth/firebase_auth/auth_util.dart';
import '/backend/api_requests/api_calls.dart';
import '/backend/backend.dart';
import '/backend/push_notifications/push_notifications_util.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/actions/actions.dart' as action_blocks;
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/custom_functions.dart' as functions;

// Process the creation of memory records
Future<void> memoryCreationBlock(BuildContext context) async {
  var structuredMemoryResponse = await structureMemory();
  if (functions.memoryContainsNA(extractContent(structuredMemoryResponse))) {
    await saveFailureMemory(structuredMemoryResponse);
  } else {
    await processStructuredMemory(structuredMemoryResponse);
  }
}

// Call to the API to get structured memory
Future<ApiCallResponse> structureMemory() async {
  logFirebaseEvent('memoryCreationBlock_StructureMemoryAPI');
  return await StructuredMemoryCall.call(
    memory: functions.jsonEncodeString(FFAppState().lastMemory),
  );
}

// Extract content from API response
String extractContent(ApiCallResponse response) {
  return getJsonField(
    (response.jsonBody ?? ''),
    r'''$.choices[0].message.content''',
  ).toString();
}

// Save failure memory when structured memory contains NA
Future<void> saveFailureMemory(ApiCallResponse response) async {
  logFirebaseEvent('memoryCreationBlock_backend_call');
  await MemoriesRecord.collection.doc().set({
    ...createMemoriesRecordData(
      memory: FFAppState().lastMemory,
      user: currentUserReference,
      structuredMemory: extractContent(response),
      feedback: '',
      toShowToUserShowHide: 'Hide',
      emptyMemory: FFAppState().lastMemory == '',
      isUselessMemory: true,
    ),
    ...mapToFirestore({
      'date': FieldValue.serverTimestamp(),
    }),
  });
}

// Process structured memory when it's valid
Future<void> processStructuredMemory(ApiCallResponse response) async {
  if (functions.xGreaterThany(functions.wordCount(FFAppState().lastMemory), 1)!) {
    updateAppStateForProcessing();
    var feedbackResponse = await requestFeedback(response);
    await evaluateFeedback(feedbackResponse);
    updateFinalAppState(feedbackResponse);
  } else {
    updateAppStateForEmptyFeedback();
  }
  logFirebaseEvent('memoryCreationBlock_backend_call', parameters: buildLogParameters(response));
  await finalizeMemoryRecord(response);
}

// Update app state when starting memory processing
void updateAppStateForProcessing() {
  logFirebaseEvent('memoryCreationBlock_update_app_state');
  FFAppState().update(() {
    FFAppState().memoryCreationProcessing = true;
  });
}

// Request feedback for the given memory
Future<ApiCallResponse> requestFeedback(ApiCallResponse structuredMemoryResponse) async {
  logFirebaseEvent('memoryCreationBlock_FEEDBACKapi');
  return await ChatGPTFeedbackCall.call(
    memory: functions.jsonEncodeString(FFAppState().lastMemory),
    structuredMemory: functions.jsonEncodeString(extractContent(structuredMemoryResponse)),
  );
}

// Evaluate feedback usefulness
Future<void> evaluateFeedback(ApiCallResponse feedbackResponse) async {
  logFirebaseEvent('memoryCreationBlock_custom_action');
  await actions.debugLog(extractContent(feedbackResponse));
  logFirebaseEvent('memoryCreationBlock_backend_call');
  await IsFeeedbackUsefulCall.call(
    memory: FFAppState().lastMemory,
    feedback: extractContent(feedbackResponse),
  );
}

// Update app state after processing feedback
void updateFinalAppState(ApiCallResponse feedbackResponse) {
  logFirebaseEvent('memoryCreationBlock_update_app_state');
  FFAppState().update(() {
    FFAppState().feedback = functions.jsonEncodeString(extractContent(feedbackResponse))!;
    FFAppState().isFeedbackUseful = functions.jsonEncodeString(extractContent(feedbackResponse))!;
    FFAppState().chatHistory = functions.saveChatHistory(
        FFAppState().chatHistory, functions.convertToJSONRole(extractContent(feedbackResponse), 'assistant'));
    FFAppState().memoryCreationProcessing = false;
  });
}

// Update app state when feedback is empty
void updateAppStateForEmptyFeedback() {
  logFirebaseEvent('memoryCreationBlock_update_app_state');
  FFAppState().update(() {
    FFAppState().feedback = '';
    FFAppState().isFeedbackUseful = 'Hide';
  });
}

// Build log parameters for structured memory processing
Map<String, dynamic> buildLogParameters(ApiCallResponse response) {
  return {
    'jsonBody': (response.jsonBody ?? ''),
    'memory': FFAppState().lastMemory,
    'user': currentUserReference,
  };
}

// Finalize memory record after processing feedback
Future<void> finalizeMemoryRecord(ApiCallResponse structuredMemoryResponse) async {
  var vectorResponse = await vectorizeMemory(structuredMemoryResponse);
  logFirebaseEvent('memoryCreationBlock_backend_call');
  var memoryRecord = await createMemoryRecord(structuredMemoryResponse, vectorResponse);
  logFirebaseEvent('memoryCreationBlock_backend_call');
  await storeVectorData(memoryRecord, vectorResponse);
}

// Call vectorization API for structured memory
Future<ApiCallResponse> vectorizeMemory(ApiCallResponse structuredMemoryResponse) async {
  // debugPrint('vectorizeMemory ${structuredMemoryResponse.jsonBody}');
  var input = StructuredMemoryCall.responsegpt(
    (structuredMemoryResponse.jsonBody ?? ''),
  );
  return await VectorizeCall.call(input: input?.toString());
}

// Create memory record
Future<MemoriesRecord> createMemoryRecord(
    ApiCallResponse structuredMemoryResponse, ApiCallResponse vectorResponse) async {
  var recordRef = MemoriesRecord.collection.doc();
  await recordRef.set({
    ...createMemoriesRecordData(
      memory: FFAppState().lastMemory,
      user: currentUserReference,
      structuredMemory: extractContent(structuredMemoryResponse),
      feedback: FFAppState().feedback,
      toShowToUserShowHide: FFAppState().isFeedbackUseful,
      emptyMemory: FFAppState().lastMemory == '',
      isUselessMemory: functions.memoryContainsNA(extractContent(structuredMemoryResponse)),
    ),
    ...mapToFirestore({
      'date': FieldValue.serverTimestamp(),
      'vector': VectorizeCall.embedding((vectorResponse.jsonBody ?? '')),
    }),
  });
  return MemoriesRecord.getDocumentFromData({
    ...createMemoriesRecordData(
      memory: FFAppState().lastMemory,
      user: currentUserReference,
      structuredMemory: extractContent(structuredMemoryResponse),
      feedback: FFAppState().feedback,
      toShowToUserShowHide: FFAppState().isFeedbackUseful,
      emptyMemory: FFAppState().lastMemory == '',
      isUselessMemory: functions.memoryContainsNA(extractContent(structuredMemoryResponse)),
    ),
    ...mapToFirestore({
      'date': DateTime.now(),
      'vector': VectorizeCall.embedding((vectorResponse.jsonBody ?? '')),
    }),
  }, recordRef);
}

// Store vector data after memory record creation
Future<void> storeVectorData(MemoriesRecord memoryRecord, ApiCallResponse vectorResponse) async {
  // debugPrint('storeVectorData: memoryRecord -> $memoryRecord');
  // debugPrint('storeVectorData: vectorResponse -> ${vectorResponse.jsonBody}');

  var vectorAdded = await CreateVectorPineconeCall.call(
    vectorList: VectorizeCall.embedding((vectorResponse.jsonBody ?? '')),
    id: memoryRecord.reference.id,
    structuredMemory: memoryRecord.structuredMemory,
  );
  // debugPrint('storeVectorData VectorAdded: ${vectorAdded.statusCode} ${vectorAdded.jsonBody}');
  if (memoryRecord.toShowToUserShowHide == 'Show' && !memoryRecord.emptyMemory && !memoryRecord.isUselessMemory) {
    logFirebaseEvent('memoryCreationBlock_trigger_push_notific');
    if (currentUserReference != null) {
      triggerPushNotification(
        notificationTitle: 'Sama',
        notificationText: FFAppState().feedback,
        userRefs: [currentUserReference!],
        initialPageName: 'chat',
        parameterData: {},
      );
    }
  }
}

// Process voice commands
Future<void> voiceCommandBlock(BuildContext context) async {
  if (!FFAppState().commandIsProcessing) {
    startProcessingCommand();
    var latestMemories = await fetchLatestMemories();
    await processVoiceCommand(latestMemories);
    FFAppState().commandIsProcessing = false;
  }
}

// Start processing a voice command
void startProcessingCommand() {
  logFirebaseEvent('voiceCommandBlock_update_app_state');
  FFAppState().update(() {
    FFAppState().commandIsProcessing = true;
    FFAppState().commandState = 'Listening...';
  });
}

// Fetch latest valid memories
Future<List<MemoriesRecord>> fetchLatestMemories() async {
  logFirebaseEvent('voiceCommandBlock_firestore_query');
  return await queryMemoriesRecordOnce(
    queryBuilder: (memoriesRecord) => memoriesRecord
        .where('user', isEqualTo: currentUserReference)
        .where('isUselessMemory', isEqualTo: false)
        .where('emptyMemory', isEqualTo: false)
        .orderBy('date', descending: true),
    limit: 30,
  );
}

// Process the voice command with potential delays and updates
Future<void> processVoiceCommand(List<MemoriesRecord> memories) async {
  await Future.delayed(const Duration(milliseconds: 6000));
  logFirebaseEvent('voiceCommandBlock_update_app_state');
  FFAppState().update(() {
    FFAppState().commandState = 'Thinking...';
  });

  var result = await VoiceCommandRespondCall.call(
    memory: functions.limitTranscript(FFAppState().stt, 12000),
    longTermMemory: functions.jsonEncodeString(functions.documentsToText(memories.toList())),
  );

  updateAppStateForVoiceResult(result);
  if (result.succeeded ?? true) {
    triggerVoiceCommandNotification(result);
    await saveVoiceCommandMemory(result);
  }
}

// Update app state after voice command results are processed
void updateAppStateForVoiceResult(ApiCallResponse result) {
  FFAppState().commandState = 'Query';
}

// Trigger notifications based on voice command results
void triggerVoiceCommandNotification(ApiCallResponse result) {
  logFirebaseEvent('voiceCommandBlock_trigger_push_notification');
  if (currentUserReference != null) {
    triggerPushNotification(
      notificationTitle: 'Sama',
      notificationText: extractContent(result),
      notificationSound: 'default',
      userRefs: [currentUserReference!],
      initialPageName: 'chat',
      parameterData: {},
    );
  }
}

// Save the memory from a voice command
Future<void> saveVoiceCommandMemory(ApiCallResponse result) async {
  await MemoriesRecord.collection.doc().set({
    ...createMemoriesRecordData(
      user: currentUserReference,
      feedback: extractContent(result),
      toShowToUserShowHide: 'Show',
      emptyMemory: true,
      isUselessMemory: false,
    ),
    ...mapToFirestore({
      'date': FieldValue.serverTimestamp(),
    }),
  });
}

// Perform actions periodically
Future<void> periodicAction(BuildContext context) async {
  String lastWords = await actions.getLastWords();
  updateLastMemory(lastWords);
  if (lastWords.isNotEmpty) {
    logFirebaseEvent('periodicAction_addlastwordstomemory');
    await action_blocks.memoryCreationBlock(context);
  }
}

// Update last memory based on the last words
void updateLastMemory(String lastWords) {
  logFirebaseEvent('periodicAction_update_app_state');
  FFAppState().lastMemory = '${FFAppState().lastMemory} $lastWords';
}

// Perform final actions on finish
Future<void> onFinishAction(BuildContext context) async {
  String lastWordsOnFinishAction = await actions.getLastWords();
  logFirebaseEvent('OnFinishAction_custom_action');
  await actions.debugLog('LAST WORDS FINISH: $lastWordsOnFinishAction');

  updateMemoryOnFinish(lastWordsOnFinishAction);
  logFirebaseEvent('OnFinishAction_action_block');
  await action_blocks.memoryCreationBlock(context);

  triggerFinishNotification();
}

// Update memory when finishing an action
void updateMemoryOnFinish(String lastWords) {
  FFAppState().lastMemory = '${FFAppState().lastMemory} $lastWords';
}

// Trigger notification to indicate recording is disabled
void triggerFinishNotification() {
  logFirebaseEvent('OnFinishAction_trigger_push_notification');
  if (currentUserReference != null) {
    triggerPushNotification(
      notificationTitle: 'Sama',
      notificationText: 'Recording is disabled! Please restart audio recording',
      userRefs: [currentUserReference!],
      initialPageName: 'chat',
      parameterData: {},
    );
  }
}

// Start recording function placeholder
Future<void> startRecording(BuildContext context) async {
  // Implement recording start logic here
}
