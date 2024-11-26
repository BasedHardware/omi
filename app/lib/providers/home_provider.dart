import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/speech_profile.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/analytics/analytics_manager.dart';

class HomeProvider extends ChangeNotifier {
  int selectedIndex = 0;
  final FocusNode memoryFieldFocusNode = FocusNode();
  final FocusNode chatFieldFocusNode = FocusNode();
  final FocusNode appsSearchFieldFocusNode = FocusNode();
  bool isAppsSearchFieldFocused = false;
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
    'English/Spanish': 'multi',
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
    appsSearchFieldFocusNode.addListener(_onFocusChange);
  }

  void _onFocusChange() {
    isMemoryFieldFocused = memoryFieldFocusNode.hasFocus;
    isChatFieldFocused = chatFieldFocusNode.hasFocus;
    isAppsSearchFieldFocused = appsSearchFieldFocusNode.hasFocus;
    notifyListeners();
  }

  void setIndex(int index) {
    selectedIndex = index;
    notifyListeners();
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

  @override
  void dispose() {
    memoryFieldFocusNode.removeListener(_onFocusChange);
    chatFieldFocusNode.removeListener(_onFocusChange);
    appsSearchFieldFocusNode.removeListener(_onFocusChange);
    memoryFieldFocusNode.dispose();
    chatFieldFocusNode.dispose();
    appsSearchFieldFocusNode.dispose();
    super.dispose();
  }
}
