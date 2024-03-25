import '/auth/firebase_auth/auth_util.dart';
import '/backend/api_requests/api_calls.dart';
import '/backend/backend.dart';
import '/backend/push_notifications/push_notifications_util.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/actions/actions.dart' as action_blocks;
import '/custom_code/actions/index.dart' as actions;
import '/flutter_flow/custom_functions.dart' as functions;
import 'package:flutter/material.dart';

Future memoryCreationBlock(BuildContext context) async {
  ApiCallResponse? sMemory;
  ApiCallResponse? fMemory;
  ApiCallResponse? isFeedbackUsefulResult;
  ApiCallResponse? vectorFromOpenai;
  MemoriesRecord? memoryDone;
  ApiCallResponse? vectorAdded;

  // StructureMemoryAPI
  logFirebaseEvent('memoryCreationBlock_StructureMemoryAPI');
  sMemory = await StructuredMemoryCall.call(
    memory: functions.jsonEncodeString(FFAppState().lastMemory),
  );
  if (functions.memoryContainsNA(getJsonField(
        (sMemory.jsonBody ?? ''),
        r'''$.choices[0].message.content''',
      ).toString().toString()) ==
      true) {
    logFirebaseEvent('memoryCreationBlock_backend_call');

    await MemoriesRecord.collection.doc().set({
      ...createMemoriesRecordData(
        memory: FFAppState().lastMemory,
        user: currentUserReference,
        structuredMemory: getJsonField(
          (sMemory.jsonBody ?? ''),
          r'''$.choices[0].message.content''',
        ).toString().toString(),
        feedback: '',
        toShowToUserShowHide: 'Hide',
        emptyMemory:
            FFAppState().lastMemory == '',
        isUselessMemory: true,
      ),
      ...mapToFirestore(
        {
          'date': FieldValue.serverTimestamp(),
        },
      ),
    });
  } else {
    if (functions.xGreaterThany(
        functions.wordCount(FFAppState().lastMemory), 1)!) {
      logFirebaseEvent('memoryCreationBlock_update_app_state');
      FFAppState().update(() {
        FFAppState().memoryCreationProcessing = true;
      });
      // FEEDBACKapi
      logFirebaseEvent('memoryCreationBlock_FEEDBACKapi');
      fMemory = await ChatGPTFeedbackCall.call(
        memory: functions.jsonEncodeString(FFAppState().lastMemory),
        structuredMemory: functions.jsonEncodeString(getJsonField(
          (sMemory.jsonBody ?? ''),
          r'''$.choices[0].message.content''',
        ).toString().toString()),
      );
      logFirebaseEvent('memoryCreationBlock_custom_action');
      await actions.debugLog(
        getJsonField(
          (fMemory.jsonBody ?? ''),
          r'''$.choices[0].message.content''',
        ).toString().toString(),
      );
      logFirebaseEvent('memoryCreationBlock_backend_call');
      isFeedbackUsefulResult = await IsFeeedbackUsefulCall.call(
        memory: FFAppState().lastMemory,
        feedback: getJsonField(
          (fMemory.jsonBody ?? ''),
          r'''$.choices[0].message.content''',
        ).toString().toString(),
      );
      logFirebaseEvent('memoryCreationBlock_update_app_state');
      FFAppState().update(() {
        FFAppState().feedback = functions.jsonEncodeString(getJsonField(
          (fMemory?.jsonBody ?? ''),
          r'''$.choices[0].message.content''',
        ).toString().toString())!;
        FFAppState().isFeedbackUseful = functions.jsonEncodeString(getJsonField(
          (isFeedbackUsefulResult?.jsonBody ?? ''),
          r'''$.choices[0].message.content''',
        ).toString().toString())!;
        FFAppState().chatHistory = functions.saveChatHistory(
            FFAppState().chatHistory,
            functions.convertToJSONRole(
                getJsonField(
                  (fMemory?.jsonBody ?? ''),
                  r'''$.choices[0].message.content''',
                ).toString().toString(),
                'assistant')!)!;
        FFAppState().memoryCreationProcessing = false;
      });
    } else {
      logFirebaseEvent('memoryCreationBlock_update_app_state');
      FFAppState().update(() {
        FFAppState().feedback = '';
        FFAppState().isFeedbackUseful = 'Hide';
      });
    }

    logFirebaseEvent('memoryCreationBlock_backend_call');
    vectorFromOpenai = await VectorizeCall.call(
      input: StructuredMemoryCall.responsegpt(
        (sMemory.jsonBody ?? ''),
      ),
    );
    logFirebaseEvent('memoryCreationBlock_backend_call');

    var memoriesRecordReference2 = MemoriesRecord.collection.doc();
    await memoriesRecordReference2.set({
      ...createMemoriesRecordData(
        memory: FFAppState().lastMemory,
        user: currentUserReference,
        structuredMemory: getJsonField(
          (sMemory.jsonBody ?? ''),
          r'''$.choices[0].message.content''',
        ).toString().toString(),
        feedback: FFAppState().feedback,
        toShowToUserShowHide: FFAppState().isFeedbackUseful,
        emptyMemory:
            FFAppState().lastMemory == '',
        isUselessMemory: functions.memoryContainsNA(getJsonField(
          (sMemory.jsonBody ?? ''),
          r'''$.choices[0].message.content''',
        ).toString().toString()),
      ),
      ...mapToFirestore(
        {
          'date': FieldValue.serverTimestamp(),
          'vector': VectorizeCall.embedding(
            (vectorFromOpenai.jsonBody ?? ''),
          ),
        },
      ),
    });
    memoryDone = MemoriesRecord.getDocumentFromData({
      ...createMemoriesRecordData(
        memory: FFAppState().lastMemory,
        user: currentUserReference,
        structuredMemory: getJsonField(
          (sMemory.jsonBody ?? ''),
          r'''$.choices[0].message.content''',
        ).toString().toString(),
        feedback: FFAppState().feedback,
        toShowToUserShowHide: FFAppState().isFeedbackUseful,
        emptyMemory:
            FFAppState().lastMemory == '',
        isUselessMemory: functions.memoryContainsNA(getJsonField(
          (sMemory.jsonBody ?? ''),
          r'''$.choices[0].message.content''',
        ).toString().toString()),
      ),
      ...mapToFirestore(
        {
          'date': DateTime.now(),
          'vector': VectorizeCall.embedding(
            (vectorFromOpenai.jsonBody ?? ''),
          ),
        },
      ),
    }, memoriesRecordReference2);
    logFirebaseEvent('memoryCreationBlock_backend_call');
    vectorAdded = await CreateVectorPineconeCall.call(
      vectorList: VectorizeCall.embedding(
        (vectorFromOpenai.jsonBody ?? ''),
      ),
      id: memoryDone.reference.id,
      structuredMemory: memoryDone.structuredMemory,
    );
    if ((memoryDone.toShowToUserShowHide == 'Show') &&
        !memoryDone.emptyMemory &&
        !memoryDone.isUselessMemory) {
      logFirebaseEvent('memoryCreationBlock_trigger_push_notific');
      triggerPushNotification(
        notificationTitle: 'Sama',
        notificationText: FFAppState().feedback,
        userRefs: [currentUserReference!],
        initialPageName: 'chat',
        parameterData: {},
      );
    }
  }

  // clear unprocessed memories
  logFirebaseEvent('memoryCreationBlock_clearunprocessedmemo');
  FFAppState().update(() {
    FFAppState().lastMemory = '';
  });
}

Future voiceCommandBlock(BuildContext context) async {
  List<MemoriesRecord>? latestMemories;
  ApiCallResponse? voiceCommandResult;

  if (!FFAppState().commandIsProcessing) {
    logFirebaseEvent('voiceCommandBlock_update_app_state');
    FFAppState().commandIsProcessing = true;
    FFAppState().commandState = 'Listening...';
    logFirebaseEvent('voiceCommandBlock_firestore_query');
    latestMemories = await queryMemoriesRecordOnce(
      queryBuilder: (memoriesRecord) => memoriesRecord
          .where(
            'user',
            isEqualTo: currentUserReference,
          )
          .where(
            'isUselessMemory',
            isEqualTo: false,
          )
          .where(
            'emptyMemory',
            isEqualTo: false,
          )
          .orderBy('date', descending: true),
      limit: 30,
    );
    logFirebaseEvent('voiceCommandBlock_wait__delay');
    await Future.delayed(const Duration(milliseconds: 6000));
    logFirebaseEvent('voiceCommandBlock_update_app_state');
    FFAppState().update(() {
      FFAppState().commandState = 'Thinking...';
    });
    logFirebaseEvent('voiceCommandBlock_backend_call');
    voiceCommandResult = await VoiceCommandRespondCall.call(
      memory: functions.limitTranscript(FFAppState().stt, 12000),
      longTermMemory: functions.jsonEncodeString(
          functions.documentsToText(latestMemories.toList())),
    );
    logFirebaseEvent('voiceCommandBlock_update_app_state');
    FFAppState().update(() {
      FFAppState().commandState = ' Query';
    });
    if ((voiceCommandResult.succeeded ?? true)) {
      logFirebaseEvent('voiceCommandBlock_trigger_push_notificat');
      triggerPushNotification(
        notificationTitle: 'Sama',
        notificationText: getJsonField(
          (voiceCommandResult.jsonBody ?? ''),
          r'''$.choices[0].message.content''',
        ).toString().toString(),
        notificationSound: 'default',
        userRefs: [currentUserReference!],
        initialPageName: 'chat',
        parameterData: {},
      );
      logFirebaseEvent('voiceCommandBlock_backend_call');

      await MemoriesRecord.collection.doc().set({
        ...createMemoriesRecordData(
          user: currentUserReference,
          feedback: getJsonField(
            (voiceCommandResult.jsonBody ?? ''),
            r'''$.choices[0].message.content''',
          ).toString().toString(),
          toShowToUserShowHide: 'Show',
          emptyMemory: true,
          isUselessMemory: false,
        ),
        ...mapToFirestore(
          {
            'date': FieldValue.serverTimestamp(),
          },
        ),
      });
    }
    logFirebaseEvent('voiceCommandBlock_update_app_state');
    FFAppState().commandIsProcessing = false;
  }
}

Future periodicAction(BuildContext context) async {
  String? lastWords;

  logFirebaseEvent('periodicAction_custom_action');
  lastWords = await actions.getLastWords();
  if (lastWords == '') {
    if (FFAppState().lastMemory == '') {
      // convo just started
      logFirebaseEvent('periodicAction_convojuststarted');
      await actions.debugLog(
        'convo just started.',
      );
    } else {
      // add lastwords to memory
      logFirebaseEvent('periodicAction_addlastwordstomemory');
      FFAppState().lastMemory = '${FFAppState().lastMemory} $lastWords';
      logFirebaseEvent('periodicAction_action_block');
      await action_blocks.memoryCreationBlock(context);
      return;
    }
  } else {
    logFirebaseEvent('periodicAction_update_app_state');
    FFAppState().lastMemory = '${FFAppState().lastMemory} $lastWords';
  }

  logFirebaseEvent('periodicAction_backend_call');

  await MemoriesRecord.collection.doc().set({
    ...createMemoriesRecordData(
      memory: '',
      user: currentUserReference,
      structuredMemory: 'N/A!',
      feedback: '',
      toShowToUserShowHide: 'Hide',
      emptyMemory: true,
      isUselessMemory: true,
    ),
    ...mapToFirestore(
      {
        'date': FieldValue.serverTimestamp(),
      },
    ),
  });
}

Future onFinishAction(BuildContext context) async {
  String? lastWordsOnFinishAction;

  logFirebaseEvent('OnFinishAction_custom_action');
  lastWordsOnFinishAction = await actions.getLastWords();
  logFirebaseEvent('OnFinishAction_custom_action');
  await actions.debugLog(
    'LAST WORDS FINISH: $lastWordsOnFinishAction',
  );
  logFirebaseEvent('OnFinishAction_update_app_state');
  FFAppState().lastMemory =
      '${FFAppState().lastMemory} $lastWordsOnFinishAction';
  logFirebaseEvent('OnFinishAction_custom_action');
  await actions.debugLog(
    'LAST MEM FINISH: ${FFAppState().lastMemory}__LAST TRNASCRIPT: ${FFAppState().lastTranscript}',
  );
  logFirebaseEvent('OnFinishAction_action_block');
  await action_blocks.memoryCreationBlock(context);
  logFirebaseEvent('OnFinishAction_trigger_push_notification');
  triggerPushNotification(
    notificationTitle: 'Sama',
    notificationText: 'Recording is disabled! Please restart audio recording',
    userRefs: [currentUserReference!],
    initialPageName: 'chat',
    parameterData: {},
  );
}

Future startRecording(BuildContext context) async {}
