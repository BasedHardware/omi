import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/logger.dart';

/// Base language codes eligible for live multi-language auto-detection.
/// Mirrors the backend live STT capability policy
/// (backend/config/stt_provider_policy.py MODULATE_SUPPORTED_LANGUAGES, #10022);
/// regional variants ("pt-BR") are normalized to their base code before lookup.
const multiLanguageSupported = {
  'multi',
  'af', 'ar', 'az', 'be', 'bg', 'bn', 'bs', 'ca', 'cs', 'cy', 'da', 'de',
  'el', 'en', 'es', 'et', 'eu', 'fa', 'fi', 'fr', 'gl', 'gu', 'he', 'hi',
  'hr', 'hu', 'id', 'it', 'ja', 'kk', 'kn', 'ko', 'lt', 'lv', 'mk', 'ml',
  'mr', 'ms', 'nl', 'no', 'pa', 'pl', 'pt', 'ro', 'ru', 'sk', 'sl', 'sq',
  'sr', 'sv', 'sw', 'ta', 'te', 'th', 'tl', 'tr', 'uk', 'ur', 'vi', 'zh',
};

/// Whether a (possibly regional) language code may enter live multi-language
/// mode, matching the backend's normalized policy check.
bool supportsLiveMultilingualMode(String languageCode) {
  final base = languageCode.split('-').first.split('_').first.toLowerCase();
  return multiLanguageSupported.contains(base);
}

class HomeProvider extends ChangeNotifier {
  int _sessionGeneration = 0;
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
    'Arabic': 'ar',
    'Belarusian': 'be',
    'Bengali': 'bn',
    'Bosnian': 'bs',
    'Bulgarian': 'bg',
    'Catalan': 'ca',
    'Chinese (Mandarin, Traditional)': 'zh-TW',
    'Chinese (Mandarin, Traditional, Hant)': 'zh-Hant',
    'Chinese (Cantonese, Traditional)': 'zh-HK',
    'Croatian': 'hr',
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
    'Hebrew': 'he',
    'Hungarian': 'hu',
    'Indonesian': 'id',
    'Italian': 'it',
    'Kannada': 'kn',
    'Korean': 'ko',
    'Korean (Korea)': 'ko-KR',
    'Latvian': 'lv',
    'Lithuanian': 'lt',
    'Macedonian': 'mk',
    'Malay': 'ms',
    'Marathi': 'mr',
    'Norwegian': 'no',
    'Persian': 'fa',
    'Polish': 'pl',
    'Romanian': 'ro',
    'Serbian': 'sr',
    'Slovak': 'sk',
    'Slovenian': 'sl',
    'Swedish': 'sv',
    'Swedish (Sweden)': 'sv-SE',
    'Tagalog': 'tl',
    'Tamil': 'ta',
    'Telugu': 'te',
    'Thai': 'th',
    'Thai (Thailand)': 'th-TH',
    'Turkish': 'tr',
    'Ukrainian': 'uk',
    'Urdu': 'ur',
    'Vietnamese': 'vi',
  };

  HomeProvider() {
    chatFieldFocusNode.addListener(_onFocusChange);
    appsSearchFieldFocusNode.addListener(_onFocusChange);
    convoSearchFieldFocusNode.addListener(_onConvoSearchFocusChange);
    memoriesSearchFieldFocusNode.addListener(_onFocusChange);
  }

  void clearUserData() {
    _sessionGeneration++;
    selectedIndex = 0;
    isAppsSearchFieldFocused = false;
    isChatFieldFocused = false;
    isConvoSearchFieldFocused = false;
    isMemoriesSearchFieldFocused = false;
    showConvoSearchBar = false;
    hasSpeakerProfile = false;
    isLoading = false;
    userPrimaryLanguage = '';
    hasSetPrimaryLanguage = false;
    chatFieldFocusNode.unfocus();
    appsSearchFieldFocusNode.unfocus();
    convoSearchFieldFocusNode.unfocus();
    memoriesSearchFieldFocusNode.unfocus();
    notifyListeners();
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
    onSelectedIndexChanged?.call(index);
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
    final generation = _sessionGeneration;
    setIsLoading(true);
    var res = await userHasSpeakerProfile();
    if (generation != _sessionGeneration) return;
    setSpeakerProfile(res);
    SharedPreferencesUtil().hasSpeakerProfile = res;
    Logger.debug('_setupHasSpeakerProfile: ${SharedPreferencesUtil().hasSpeakerProfile}');
    PlatformManager.instance.analytics.setUserAttribute('Speaker Profile', SharedPreferencesUtil().hasSpeakerProfile);

    setIsLoading(false);
    notifyListeners();
  }

  Future<void> setupUserPrimaryLanguage() async {
    if (SharedPreferencesUtil().hasSetPrimaryLanguage && SharedPreferencesUtil().userPrimaryLanguage.isNotEmpty) {
      return;
    }

    final generation = _sessionGeneration;
    try {
      final language = await getUserPrimaryLanguage();
      if (generation != _sessionGeneration) return;
      if (language == null) {
        // User hasn't set a primary language yet
        userPrimaryLanguage = '';
        hasSetPrimaryLanguage = false;

        // Show language dialog after a short delay to ensure UI is ready
        Future.delayed(const Duration(milliseconds: 500), () {
          if (generation == _sessionGeneration && globalNavigatorKey.currentContext != null) {
            showLanguageDialogIfNeeded(globalNavigatorKey.currentContext!);
          }
        });
      } else {
        userPrimaryLanguage = language;
        hasSetPrimaryLanguage = true;
        SharedPreferencesUtil().userPrimaryLanguage = language;
        SharedPreferencesUtil().hasSetPrimaryLanguage = true;
        PlatformManager.instance.analytics.setUserAttribute('Primary Language', language);
      }
      Logger.debug('setupUserPrimaryLanguage: $language, hasSet: $hasSetPrimaryLanguage');
    } catch (e) {
      if (generation != _sessionGeneration) return;
      Logger.debug('Error setting up user primary language: $e');
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

  Future<bool> updateUserPrimaryLanguage(String languageCode, {UserProvider? userProvider}) async {
    try {
      final success = await setUserPrimaryLanguage(languageCode);
      if (success) {
        userPrimaryLanguage = languageCode;
        hasSetPrimaryLanguage = true;
        SharedPreferencesUtil().userPrimaryLanguage = languageCode;
        SharedPreferencesUtil().hasSetPrimaryLanguage = true;
        PlatformManager.instance.analytics.setUserAttribute('Primary Language', languageCode);

        // Backend auto-sets single_language_mode — sync local state to match
        final singleLanguageMode = !supportsLiveMultilingualMode(languageCode);
        userProvider?.updateSingleLanguageModeLocally(singleLanguageMode);

        notifyListeners();
        return true;
      }
      return false;
    } catch (e) {
      Logger.debug('Error setting user primary language: $e');
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
