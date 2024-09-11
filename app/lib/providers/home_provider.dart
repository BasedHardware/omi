import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/speech_profile.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

class HomeProvider extends ChangeNotifier {
  int selectedIndex = 0;
  final FocusNode memoryFieldFocusNode = FocusNode();
  final FocusNode chatFieldFocusNode = FocusNode();
  bool isMemoryFieldFocused = false;
  bool isChatFieldFocused = false;

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
    selectedIndex = index;
    notifyListeners();
  }

  Future setupHasSpeakerProfile() async {
    SharedPreferencesUtil().hasSpeakerProfile = await userHasSpeakerProfile();
    debugPrint('_setupHasSpeakerProfile: ${SharedPreferencesUtil().hasSpeakerProfile}');
    MixpanelManager().setUserProperty('Speaker Profile', SharedPreferencesUtil().hasSpeakerProfile);
    notifyListeners();
  }

  Future setUserPeople() async {
    SharedPreferencesUtil().cachedPeople = await getAllPeople();
    notifyListeners();
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
