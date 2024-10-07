import 'package:flutter/material.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/providers/plugin_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:tuple/tuple.dart';

class MemoryDetailProvider extends ChangeNotifier with MessageNotifierMixin {
  PluginProvider? pluginProvider;
  MemoryProvider? memoryProvider;
  // late ServerMemory memory;

  int memoryIdx = 0;
  DateTime selectedDate = DateTime.now();

  int selectedTab = 0;
  bool isLoading = false;
  bool loadingReprocessMemory = false;
  String reprocessMemoryId = '';

  final scaffoldKey = GlobalKey<ScaffoldState>();
  final focusTitleField = FocusNode();
  final focusOverviewField = FocusNode();
  List<Plugin> pluginsList = [];

  Structured get structured => memoryProvider!.groupedMemories[selectedDate]![memoryIdx].structured;
  ServerMemory get memory => memoryProvider!.groupedMemories[selectedDate]![memoryIdx];
  List<bool> pluginResponseExpanded = [];

  bool editingTitle = false;
  bool editingOverview = false;

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

  void setProviders(PluginProvider provider, MemoryProvider memoryProvider) {
    this.memoryProvider = memoryProvider;
    pluginProvider = provider;
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

  updateReprocessMemoryLoadingState(bool loading) {
    loadingReprocessMemory = loading;
    notifyListeners();
  }

  void updateRepocessMemoryId(String id) {
    reprocessMemoryId = id;
    notifyListeners();
  }

  void updateMemory(int memIdx, DateTime date) {
    memoryIdx = memIdx;
    selectedDate = date;
    pluginResponseExpanded = List.filled(memory.pluginsResults.length, false);
    notifyListeners();
  }

  void updateEventState(bool state, int i) {
    memory.structured.events[i].created = state;
    notifyListeners();
  }

  void updatePluginResponseExpanded(int index) {
    pluginResponseExpanded[index] = !pluginResponseExpanded[index];
    notifyListeners();
  }

  Future initMemory() async {
    // updateLoadingState(true);
    photos = [];
    canDisplaySeconds = TranscriptSegment.canDisplaySeconds(memory.transcriptSegments);
    if (memory.source == MemorySource.openglass) {
      await getMemoryPhotos(memory.id).then((value) async {
        photos = value;
        await populatePhotosData();
      });
    } else if (memory.source == MemorySource.friend) {
      // await hasMemoryRecording(memory.id).then((value) {
      //   hasAudioRecording = value;
      // });
    }
    pluginsList = pluginProvider!.plugins;
    // updateLoadingState(false);
    notifyListeners();
  }

  Future<bool> reprocessMemory() async {
    debugPrint('_reProcessMemory');
    updateReprocessMemoryLoadingState(true);
    updateRepocessMemoryId(memory.id);
    try {
      var updatedMemory = await reProcessMemoryServer(memory.id);
      MixpanelManager().reProcessMemory(memory);
      updateReprocessMemoryLoadingState(false);
      updateRepocessMemoryId('');
      if (updatedMemory == null) {
        notifyError('REPROCESS_FAILED');
        notifyListeners();
        return false;
      } else {
        memoryProvider!.updateMemory(updatedMemory);
        SharedPreferencesUtil().modifiedMemoryDetails = updatedMemory;
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
      updateReprocessMemoryLoadingState(false);
      updateRepocessMemoryId('');
      notifyListeners();
      return false;
    }
  }

  void unassignMemoryTranscriptSegment(String memoryId, int segmentIdx) {
    memory.transcriptSegments[segmentIdx].isUser = false;
    memory.transcriptSegments[segmentIdx].personId = null;
    assignMemoryTranscriptSegment(memoryId, segmentIdx);
    notifyListeners();
  }
}
