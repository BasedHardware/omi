import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/http/api/conversations.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:tuple/tuple.dart';

class ConversationDetailProvider extends ChangeNotifier with MessageNotifierMixin {
  AppProvider? appProvider;
  ConversationProvider? conversationProvider;

  // late ServerConversation memory;

  int memoryIdx = 0;
  DateTime selectedDate = DateTime.now();

  int selectedTab = 0;
  bool isLoading = false;
  bool loadingReprocessConversation = false;
  String reprocessConversationId = '';

  final scaffoldKey = GlobalKey<ScaffoldState>();
  List<App> appsList = [];

  Structured get structured => conversationProvider!.groupedConversations[selectedDate]![memoryIdx].structured;

  ServerConversation get memory => conversationProvider!.groupedConversations[selectedDate]![memoryIdx];
  List<bool> appResponseExpanded = [];

  TextEditingController? titleController;
  FocusNode? titleFocusNode;

  bool isTranscriptExpanded = false;

  bool canDisplaySeconds = true;

  // bool hasAudioRecording = false;

  List<MemoryPhoto> photos = [];
  List<Tuple2<String, String>> photosData = [];

  bool displayDevToolsInSheet = false;
  bool displayShareOptionsInSheet = false;

  bool editSegmentLoading = false;

  void toggleEditSegmentLoading(bool value) {
    editSegmentLoading = value;
    notifyListeners();
  }

  Future populatePhotosData() async {
    if (photos.isEmpty) return;
    // photosData = await compute<List<MemoryPhoto>, List<Tuple2<String, String>>>(
    //   (photos) => photos.map((e) => Tuple2(e.base64, e.description)).toList(),
    //   photos,
    // );
    photosData = photos.map((e) => Tuple2(e.base64, e.description)).toList();
    notifyListeners();
  }

  void toggleIsTranscriptExpanded() {
    isTranscriptExpanded = !isTranscriptExpanded;
    notifyListeners();
  }

  void toggleDevToolsInSheet(bool value) {
    displayDevToolsInSheet = value;
    notifyListeners();
  }

  void toggleShareOptionsInSheet(bool value) {
    displayShareOptionsInSheet = value;
    notifyListeners();
  }

  void setProviders(AppProvider provider, ConversationProvider conversationProvider) {
    this.conversationProvider = conversationProvider;
    appProvider = provider;
    notifyListeners();
  }

  updateSelectedTab(int index) {
    selectedTab = index;
    notifyListeners();
  }

  updateLoadingState(bool loading) {
    isLoading = loading;
    notifyListeners();
  }

  updateReprocessConversationLoadingState(bool loading) {
    loadingReprocessConversation = loading;
    notifyListeners();
  }

  void updateReprocessConversationId(String id) {
    reprocessConversationId = id;
    notifyListeners();
  }

  void updateConversation(int memIdx, DateTime date) {
    memoryIdx = memIdx;
    selectedDate = date;
    appResponseExpanded = List.filled(memory.appResults.length, false);
    notifyListeners();
  }

  void updateEventState(bool state, int i) {
    memory.structured.events[i].created = state;
    notifyListeners();
  }

  void updateActionItemState(bool state, int i) {
    memory.structured.actionItems[i].completed = state;
    notifyListeners();
  }

  List<ActionItem> deletedActionItems = [];

  void deleteActionItem(int i) {
    deletedActionItems.add(memory.structured.actionItems[i]);
    memory.structured.actionItems.removeAt(i);
    notifyListeners();
  }

  void undoDeleteActionItem(int idx) {
    memory.structured.actionItems.insert(idx, deletedActionItems.removeLast());
    notifyListeners();
  }

  void deleteActionItemPermanently(ActionItem item, int itemIdx) {
    deletedActionItems.removeWhere((element) => element == item);
    deleteConversationActionItem(memory.id, item);
    notifyListeners();
  }

  void updateAppResponseExpanded(int index) {
    appResponseExpanded[index] = !appResponseExpanded[index];
    notifyListeners();
  }

  bool hasConversationSummaryRatingSet = false;
  Timer? _ratingTimer;
  bool showRatingUI = false;

  void setShowRatingUi(bool value) {
    showRatingUI = value;
    notifyListeners();
  }

  void setConversationRating(int value) {
    setMemorySummaryRating(memory.id, value);
    hasConversationSummaryRatingSet = true;
    setShowRatingUi(false);
  }

  Future initConversation() async {
    // updateLoadingState(true);
    titleController?.dispose();
    titleFocusNode?.dispose();
    _ratingTimer?.cancel();
    showRatingUI = false;
    hasConversationSummaryRatingSet = false;

    titleController = TextEditingController();
    titleFocusNode = FocusNode();

    titleController!.text = memory.structured.title;
    titleFocusNode!.addListener(() {
      print('titleFocusNode focus changed');
      if (!titleFocusNode!.hasFocus) {
        memory.structured.title = titleController!.text;
        updateConversationTitle(memory.id, titleController!.text);
      }
    });

    photos = [];
    canDisplaySeconds = TranscriptSegment.canDisplaySeconds(memory.transcriptSegments);
    if (memory.source == ConversationSource.openglass) {
      await getConversationPhotos(memory.id).then((value) async {
        photos = value;
        await populatePhotosData();
      });
    } else if (memory.source == ConversationSource.friend) {
      // await hasMemoryRecording(memory.id).then((value) {
      //   hasAudioRecording = value;
      // });
    }
    appsList = appProvider!.apps;
    if (!memory.discarded) {
      getHasMemorySummaryRating(memory.id).then((value) {
        hasConversationSummaryRatingSet = value;
        notifyListeners();
        if (!hasConversationSummaryRatingSet) {
          _ratingTimer = Timer(const Duration(seconds: 15), () {
            setMemorySummaryRating(memory.id, -1); // set -1 to indicate is was shown
            showRatingUI = true;
            notifyListeners();
          });
        }
      });
    }

    // updateLoadingState(false);
    notifyListeners();
  }

  Future<bool> reprocessConversation() async {
    debugPrint('_reProcessConversation');
    updateReprocessConversationLoadingState(true);
    updateReprocessConversationId(memory.id);
    try {
      var updatedConversation = await reProcessConversationServer(memory.id);
      MixpanelManager().reProcessMemory(memory);
      updateReprocessConversationLoadingState(false);
      updateReprocessConversationId('');
      if (updatedConversation == null) {
        notifyError('REPROCESS_FAILED');
        notifyListeners();
        return false;
      } else {
        conversationProvider!.updateMemory(updatedConversation);
        SharedPreferencesUtil().modifiedMemoryDetails = updatedConversation;
        notifyInfo('REPROCESS_SUCCESS');
        notifyListeners();
        return true;
      }
    } catch (err, stacktrace) {
      print(err);
      var memoryReporting = MixpanelManager().getMemoryEventProperties(memory);
      CrashReporting.reportHandledCrash(err, stacktrace, level: NonFatalExceptionLevel.critical, userAttributes: {
        'memory_transcript_length': memoryReporting['transcript_length'].toString(),
        'memory_transcript_word_count': memoryReporting['transcript_word_count'].toString(),
      });
      notifyError('REPROCESS_FAILED');
      updateReprocessConversationLoadingState(false);
      updateReprocessConversationId('');
      notifyListeners();
      return false;
    }
  }

  void unassignConversationTranscriptSegment(String memoryId, int segmentIdx) {
    memory.transcriptSegments[segmentIdx].isUser = false;
    memory.transcriptSegments[segmentIdx].personId = null;
    assignConversationTranscriptSegment(memoryId, segmentIdx);
    notifyListeners();
  }
}
