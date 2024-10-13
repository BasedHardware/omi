import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/speech_profile.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/analytics/analytics_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/schema/memory.dart'; // Make sure this import is present

class HomeProvider extends ChangeNotifier {
  int selectedIndex = 0;
  final FocusNode memoryFieldFocusNode = FocusNode();
  final FocusNode chatFieldFocusNode = FocusNode();
  bool isMemoryFieldFocused = false;
  bool isChatFieldFocused = false;
  bool hasSpeakerProfile = true;
  bool isLoading = false;
  String recordingLanguage = SharedPreferencesUtil().recordingsLanguage;

  final Map<String, String> availableLanguages = {
    'Bulgarian': 'bg',
    'Catalan': 'ca',
    'Chinese': 'zh',
    'Czech': 'cs',
    'Danish': 'da',
    'Dutch': 'nl',
    'English': 'en',
    'Estonian': 'et',
    'Finnish': 'fi',
    'French': 'fr',
    'German': 'de',
    'Greek': 'el',
    'Hindi': 'hi',
    'Hungarian': 'hu',
    'Indonesian': 'id',
    'Italian': 'it',
    'Japanese': 'ja',
    'Korean': 'ko',
    'Latvian': 'lv',
    'Lithuanian': 'lt',
    'Malay': 'ms',
    'Norwegian': 'no',
    'Polish': 'pl',
    'Portuguese': 'pt',
    'Romanian': 'ro',
    'Russian': 'ru',
    'Slovak': 'sk',
    'Spanish': 'es',
    'Swedish': 'sv',
    'Thai': 'th',
    'Turkish': 'tr',
    'Ukrainian': 'uk',
    'Vietnamese': 'vi',
  };

  HomeProvider() {
    memoryFieldFocusNode.addListener(_onFocusChange);
    chatFieldFocusNode.addListener(_onFocusChange);
  }

  void _onFocusChange() {
    isMemoryFieldFocused = memoryFieldFocusNode.hasFocus;
    isChatFieldFocused = chatFieldFocusNode.hasFocus;
    notifyListeners();
  }

  void setIndex(int index) {
    if (index >= 0 && index <= 2) { // Update this to allow index 2
      selectedIndex = index;
      notifyListeners();
    }
  }

  void setIsLoading(bool loading) {
    isLoading = loading;
    notifyListeners();
  }

  void setSpeakerProfile(bool? value) {
    hasSpeakerProfile = value ?? SharedPreferencesUtil().hasSpeakerProfile;
    notifyListeners();
  }

  Future setupHasSpeakerProfile() async {
    setIsLoading(true);
    var res = await userHasSpeakerProfile();
    setSpeakerProfile(res);
    SharedPreferencesUtil().hasSpeakerProfile = res;
    debugPrint('_setupHasSpeakerProfile: ${SharedPreferencesUtil().hasSpeakerProfile}');
    AnalyticsManager().setUserAttribute('Speaker Profile', SharedPreferencesUtil().hasSpeakerProfile);
    setIsLoading(false);
    notifyListeners();
  }

  void setRecordingLanguage(String language) {
    recordingLanguage = language;
    SharedPreferencesUtil().recordingsLanguage = language;
    notifyListeners();
  }

  String getLanguageName(String code) {
    return availableLanguages.entries.firstWhere((element) => element.value == code).key;
  }

  Future setUserPeople() async {
    SharedPreferencesUtil().cachedPeople = await getAllPeople();
    notifyListeners();
  }

  Future<List<String>> fetchLatestMemories() async {
    try {
      final List<ServerMemory> memories = await getMemories(limit: 10); // Fetch the 10 most recent memories
      
      return memories.map((memory) {
        // Extract the relevant information from the ServerMemory object
        String memoryContent = '';
        
        if (memory.structured.overview.isNotEmpty) {
          memoryContent += 'Category: ${memory.structured.overview}. ';
        }
        
        // Truncate the content if it's too long
        if (memoryContent.length > 300) {
          memoryContent = memoryContent.substring(0, 297) + '...';
        }
        
        return '$memoryContent (${memory.createdAt.toLocal()})';
      }).toList();
    } catch (e) {
      debugPrint('Error fetching memories: $e');
      return [];
    }
  }

  @override
  void dispose() {
    memoryFieldFocusNode.removeListener(_onFocusChange);
    chatFieldFocusNode.removeListener(_onFocusChange);
    memoryFieldFocusNode.dispose();
    chatFieldFocusNode.dispose();
    super.dispose();
  }
}
