import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/main.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

class HomeProvider extends ChangeNotifier {
  int selectedIndex = 0;
  Function(int idx)? onSelectedIndexChanged;
  final FocusNode chatFieldFocusNode = FocusNode();
  final FocusNode appsSearchFieldFocusNode = FocusNode();
  final FocusNode convoSearchFieldFocusNode = FocusNode();
  final FocusNode memoriesSearchFieldFocusNode = FocusNode();
  bool isAppsSearchFieldFocused = false;
  bool isChatFieldFocused = false;
  bool isConvoSearchFieldFocused = false;
  bool isMemoriesSearchFieldFocused = false;
  bool showConvoSearchBar = false;
  bool hasSpeakerProfile = true;
  bool isLoading = false;
  String userPrimaryLanguage = SharedPreferencesUtil().userPrimaryLanguage;
  bool hasSetPrimaryLanguage = SharedPreferencesUtil().hasSetPrimaryLanguage;

  // Available languages ordered by popularity
  final Map<String, String> availableLanguages = {
    // Top languages first
    'English': 'en',
    'English (US)': 'en-US',
    'English (UK)': 'en-GB',
    'English (Australia)': 'en-AU',
    'English (New Zealand)': 'en-NZ',
    'English (India)': 'en-IN',
    'Spanish': 'es',
    'Spanish (Latin America)': 'es-419',
    'Chinese (Mandarin, Simplified)': 'zh',
    'Chinese (Mandarin, Simplified, CN)': 'zh-CN',
    'Chinese (Mandarin, Simplified, Hans)': 'zh-Hans',
    'Hindi': 'hi',
    'Portuguese': 'pt',
    'Portuguese (Brazil)': 'pt-BR',
    'Portuguese (Portugal)': 'pt-PT',
    'Russian': 'ru',
    'Japanese': 'ja',
    'German': 'de',
    // Other languages alphabetically
    'Bulgarian': 'bg',
    'Catalan': 'ca',
    'Chinese (Mandarin, Traditional)': 'zh-TW',
    'Chinese (Mandarin, Traditional, Hant)': 'zh-Hant',
    'Chinese (Cantonese, Traditional)': 'zh-HK',
    'Czech': 'cs',
    'Danish': 'da',
    'Danish (Denmark)': 'da-DK',
    'Dutch': 'nl',
    'Estonian': 'et',
    'Finnish': 'fi',
    'Flemish': 'nl-BE',
    'French': 'fr',
    'French (Canada)': 'fr-CA',
    'German (Switzerland)': 'de-CH',
    'Greek': 'el',
    'Hungarian': 'hu',
    'Indonesian': 'id',
    'Italian': 'it',
    'Korean': 'ko',
    'Korean (Korea)': 'ko-KR',
    'Latvian': 'lv',
    'Lithuanian': 'lt',
    'Malay': 'ms',
    'Norwegian': 'no',
    'Polish': 'pl',
    'Romanian': 'ro',
    'Slovak': 'sk',
    'Swedish': 'sv',
    'Swedish (Sweden)': 'sv-SE',
    'Thai': 'th',
    'Thai (Thailand)': 'th-TH',
    'Turkish': 'tr',
    'Ukrainian': 'uk',
    'Vietnamese': 'vi',
  };

  HomeProvider() {
    chatFieldFocusNode.addListener(_onFocusChange);
    appsSearchFieldFocusNode.addListener(_onFocusChange);
    convoSearchFieldFocusNode.addListener(_onConvoSearchFocusChange);
    memoriesSearchFieldFocusNode.addListener(_onFocusChange);
  }

  void _onFocusChange() {
    isChatFieldFocused = chatFieldFocusNode.hasFocus;
    isAppsSearchFieldFocused = appsSearchFieldFocusNode.hasFocus;
    isMemoriesSearchFieldFocused = memoriesSearchFieldFocusNode.hasFocus;
    notifyListeners();
  }

  void _onConvoSearchFocusChange() {
    isConvoSearchFieldFocused = convoSearchFieldFocusNode.hasFocus;
    // Don't auto-hide search bar when focus is lost - the widget will handle visibility
    // based on whether there's an active search query
    notifyListeners();
  }

  void setIndex(int index) {
    selectedIndex = index;
    notifyListeners();
  }

  void toggleConvoSearchBar() {
    showConvoSearchBar = !showConvoSearchBar;
    if (showConvoSearchBar) {
      // Focus the search field when showing the search bar
      // Use a post-frame callback for reliability.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        convoSearchFieldFocusNode.requestFocus();
      });
    } else {
      // Clear search and unfocus when hiding
      convoSearchFieldFocusNode.unfocus();
    }
    notifyListeners();
  }

  void hideConvoSearchBar() {
    if (showConvoSearchBar) {
      showConvoSearchBar = false;
      convoSearchFieldFocusNode.unfocus();
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

  Future<void> setupUserPrimaryLanguage() async {
    if (SharedPreferencesUtil().hasSetPrimaryLanguage && SharedPreferencesUtil().userPrimaryLanguage.isNotEmpty) {
      return;
    }

    try {
      final language = await getUserPrimaryLanguage();
      if (language == null) {
        // User hasn't set a primary language yet
        userPrimaryLanguage = '';
        hasSetPrimaryLanguage = false;

        // Show language dialog after a short delay to ensure UI is ready
        Future.delayed(const Duration(milliseconds: 500), () {
          if (MyApp.navigatorKey.currentContext != null) {
            showLanguageDialogIfNeeded(MyApp.navigatorKey.currentContext!);
          }
        });
      } else {
        userPrimaryLanguage = language;
        hasSetPrimaryLanguage = true;
        SharedPreferencesUtil().userPrimaryLanguage = language;
        SharedPreferencesUtil().hasSetPrimaryLanguage = true;
        AnalyticsManager().setUserAttribute('Primary Language', language);
      }
      debugPrint('setupUserPrimaryLanguage: $language, hasSet: $hasSetPrimaryLanguage');
    } catch (e) {
      debugPrint('Error setting up user primary language: $e');
      userPrimaryLanguage = '';
      hasSetPrimaryLanguage = false;
    }
    notifyListeners();
    return;
  }

  void showLanguageDialogIfNeeded(BuildContext context) {
    if (!hasSetPrimaryLanguage) {
      LanguageSelectionDialog.show(context, isRequired: true);
    }
  }

  Future<bool> updateUserPrimaryLanguage(String languageCode) async {
    try {
      final success = await setUserPrimaryLanguage(languageCode);
      if (success) {
        userPrimaryLanguage = languageCode;
        hasSetPrimaryLanguage = true;
        SharedPreferencesUtil().userPrimaryLanguage = languageCode;
        SharedPreferencesUtil().hasSetPrimaryLanguage = true;
        AnalyticsManager().setUserAttribute('Primary Language', languageCode);
        notifyListeners();
        return true;
      }
      return false;
    } catch (e) {
      debugPrint('Error setting user primary language: $e');
      return false;
    }
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
    chatFieldFocusNode.removeListener(_onFocusChange);
    appsSearchFieldFocusNode.removeListener(_onFocusChange);
    convoSearchFieldFocusNode.removeListener(_onConvoSearchFocusChange);
    memoriesSearchFieldFocusNode.removeListener(_onFocusChange);
    memoriesSearchFieldFocusNode.dispose();
    chatFieldFocusNode.dispose();
    appsSearchFieldFocusNode.dispose();
    convoSearchFieldFocusNode.dispose();
    onSelectedIndexChanged = null;
    super.dispose();
  }
}
