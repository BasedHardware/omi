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
  var structuredMemory = await structureMemory();
  debugPrint('Structured Memory: $structuredMemory');
  if (functions.memoryContainsNA(structuredMemory)) {
    await saveFailureMemory(structuredMemory);
  } else {
    await processStructuredMemory(structuredMemory);
  }
}

// Call to the API to get structured memory
Future<String> structureMemory() async {
  logFirebaseEvent('memoryCreationBlock_StructureMemoryAPI');
  return await fetchStructuredMemory(FFAppState().lastMemory);
}

// Save failure memory when structured memory contains NA
Future<void> saveFailureMemory(String structuredMemory) async {
  logFirebaseEvent('memoryCreationBlock_backend_call');
  await MemoriesRecord.collection.doc().set({
    ...createMemoriesRecordData(
      memory: FFAppState().lastMemory,
      user: currentUserReference,
      structuredMemory: structuredMemory,
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
Future<void> processStructuredMemory(String structuredMemory) async {
  debugPrint('processStructuredMemory: $structuredMemory');
  debugPrint('processStructuredMemory: ${functions.wordCount(FFAppState().lastMemory)}');

  logFirebaseEvent('memoryCreationBlock_backend_call', parameters: {
    'jsonBody': (structuredMemory),
    'memory': FFAppState().lastMemory,
    'user': currentUserReference,
  });
  changeAppStateMemoryCreating();
  await finalizeMemoryRecord(structuredMemory);
  changeAppStateMemoryCreating();
}

// Update app state when starting memory processing
void changeAppStateMemoryCreating() {
  logFirebaseEvent('memoryCreationBlock_update_app_state');
  FFAppState().update(() {
    FFAppState().memoryCreationProcessing = !FFAppState().memoryCreationProcessing;
  });
}

// Finalize memory record after processing feedback
Future<void> finalizeMemoryRecord(String structuredMemory) async {
  var vector = await vectorizeMemory(structuredMemory);
  logFirebaseEvent('memoryCreationBlock_backend_call');
  var memoryRecord = await createMemoryRecord(structuredMemory, vector);
  logFirebaseEvent('memoryCreationBlock_backend_call');
  await storeVectorData(memoryRecord, vector);
}

// Call vectorization API for structured memory
Future<List<double>> vectorizeMemory(String structuredMemory) async {
  return await getEmbeddingsFromInput(structuredMemory);
}

// Create memory record
Future<MemoriesRecord> createMemoryRecord(String structuredMemory, List<double> vector) async {
  var recordRef = MemoriesRecord.collection.doc();
  await recordRef.set({
    ...createMemoriesRecordData(
      memory: FFAppState().lastMemory,
      user: currentUserReference,
      structuredMemory: structuredMemory,
      feedback: '',

      toShowToUserShowHide: FFAppState().isFeedbackUseful,
      emptyMemory: FFAppState().lastMemory == '',
      isUselessMemory: functions.memoryContainsNA(structuredMemory),
    ),
    ...mapToFirestore({
      'date': FieldValue.serverTimestamp(),
      'vector': vector,
    }),
  });
  return MemoriesRecord.getDocumentOnce(recordRef);
}

// Store vector data after memory record creation
Future<void> storeVectorData(MemoriesRecord memoryRecord, List<double> vector) async {
  debugPrint('storeVectorData: memoryRecord -> $memoryRecord');
  // debugPrint('storeVectorData: vectorResponse -> ${vectorResponse.jsonBody}');

  await createPineconeVector(
    vector,
    memoryRecord.structuredMemory,
    memoryRecord.reference.id,
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
  var result = await voiceCommandRequest(functions.limitTranscript(FFAppState().stt, 12000),
      functions.jsonEncodeString(functions.documentsToText(memories.toList())));
  updateAppStateForVoiceResult();
  if (result != '') {
    triggerVoiceCommandNotification(result);
    await saveVoiceCommandMemory(result);
  }
}

// Update app state after voice command results are processed
void updateAppStateForVoiceResult() {
  FFAppState().commandState = 'Query';
}

// Trigger notifications based on voice command results
void triggerVoiceCommandNotification(String result) {
  logFirebaseEvent('voiceCommandBlock_trigger_push_notification');
  if (currentUserReference != null) {
    triggerPushNotification(
      notificationTitle: 'Sama',
      notificationText: result,
      notificationSound: 'default',
      userRefs: [currentUserReference!],
      initialPageName: 'chat',
      parameterData: {},
    );
  }
}

// Save the memory from a voice command
Future<void> saveVoiceCommandMemory(String result) async {
  await MemoriesRecord.collection.doc().set({
    ...createMemoriesRecordData(
      user: currentUserReference,
      feedback: result,
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
  debugPrint('LAST WORDS FINISH: $lastWordsOnFinishAction');

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
