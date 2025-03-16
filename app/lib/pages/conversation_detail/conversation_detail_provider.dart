import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:tuple/tuple.dart';

class ConversationDetailProvider extends ChangeNotifier with MessageNotifierMixin {
  AppProvider? appProvider;
  ConversationProvider? conversationProvider;

  // late ServerConversation memory;

  int conversationIdx = 0;
  DateTime selectedDate = DateTime.now();

  int selectedTab = 1;
  bool isLoading = false;
  bool loadingReprocessConversation = false;
  String reprocessConversationId = '';

  final scaffoldKey = GlobalKey<ScaffoldState>();
  List<App> appsList = [];

  Structured get structured => conversationProvider!.groupedConversations[selectedDate]![conversationIdx].structured;

  ServerConversation get conversation => conversationProvider!.groupedConversations[selectedDate]![conversationIdx];
  List<bool> appResponseExpanded = [];

  TextEditingController? titleController;
  FocusNode? titleFocusNode;

  bool isTranscriptExpanded = false;

  bool canDisplaySeconds = true;

  bool hasAudioRecording = false;

  List<ConversationPhoto> photos = [];
  List<Tuple2<String, String>> photosData = [];

  bool displayDevToolsInSheet = false;
  bool displayShareOptionsInSheet = false;

  bool editSegmentLoading = false;

  bool showUnassignedFloatingButton = true;

  void toggleEditSegmentLoading(bool value) {
    editSegmentLoading = value;
    notifyListeners();
  }

  void setShowUnassignedFloatingButton(bool value) {
    showUnassignedFloatingButton = value;
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
    conversationIdx = memIdx;
    selectedDate = date;
    appResponseExpanded = List.filled(conversation.appResults.length, false);
    notifyListeners();
  }

  void updateEventState(bool state, int i) {
    conversation.structured.events[i].created = state;
    notifyListeners();
  }

  void updateActionItemState(bool state, int i) {
    conversation.structured.actionItems[i].completed = state;
    notifyListeners();
  }

  List<ActionItem> deletedActionItems = [];

  void deleteActionItem(int i) {
    deletedActionItems.add(conversation.structured.actionItems[i]);
    conversation.structured.actionItems.removeAt(i);
    notifyListeners();
  }

  void undoDeleteActionItem(int idx) {
    conversation.structured.actionItems.insert(idx, deletedActionItems.removeLast());
    notifyListeners();
  }

  void deleteActionItemPermanently(ActionItem item, int itemIdx) {
    deletedActionItems.removeWhere((element) => element == item);
    deleteConversationActionItem(conversation.id, item);
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
    setConversationSummaryRating(conversation.id, value);
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

    showUnassignedFloatingButton = true;

    titleController!.text = conversation.structured.title;
    titleFocusNode!.addListener(() {
      print('titleFocusNode focus changed');
      if (!titleFocusNode!.hasFocus) {
        conversation.structured.title = titleController!.text;
        updateConversationTitle(conversation.id, titleController!.text);
      }
    });

    photos = [];
    canDisplaySeconds = TranscriptSegment.canDisplaySeconds(conversation.transcriptSegments);
    if (conversation.source == ConversationSource.openglass) {
      await getConversationPhotos(conversation.id).then((value) async {
        photos = value;
        await populatePhotosData();
      });
    }
    appsList = appProvider!.apps;
    if (!conversation.discarded) {
      getHasConversationSummaryRating(conversation.id).then((value) {
        hasConversationSummaryRatingSet = value;
        notifyListeners();
        if (!hasConversationSummaryRatingSet) {
          _ratingTimer = Timer(const Duration(seconds: 15), () {
            setConversationSummaryRating(conversation.id, -1); // set -1 to indicate is was shown
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
    updateReprocessConversationId(conversation.id);
    try {
      var updatedConversation = await reProcessConversationServer(conversation.id);
      MixpanelManager().reProcessConversation(conversation);
      updateReprocessConversationLoadingState(false);
      updateReprocessConversationId('');
      if (updatedConversation == null) {
        notifyError('REPROCESS_FAILED');
        notifyListeners();
        return false;
      } else {
        conversationProvider!.updateConversation(updatedConversation);
        SharedPreferencesUtil().modifiedConversationDetails = updatedConversation;
        notifyInfo('REPROCESS_SUCCESS');
        notifyListeners();
        return true;
      }
    } catch (err, stacktrace) {
      print(err);
      var conversationReporting = MixpanelManager().getConversationEventProperties(conversation);
      CrashReporting.reportHandledCrash(err, stacktrace, level: NonFatalExceptionLevel.critical, userAttributes: {
        'conversation_transcript_length': conversationReporting['transcript_length'].toString(),
        'conversation_transcript_word_count': conversationReporting['transcript_word_count'].toString(),
      });
      notifyError('REPROCESS_FAILED');
      updateReprocessConversationLoadingState(false);
      updateReprocessConversationId('');
      notifyListeners();
      return false;
    }
  }

  void unassignConversationTranscriptSegment(String conversationId, int segmentIdx) {
    conversation.transcriptSegments[segmentIdx].isUser = false;
    conversation.transcriptSegments[segmentIdx].personId = null;
    assignConversationTranscriptSegment(conversationId, segmentIdx);
    notifyListeners();
  }
}
