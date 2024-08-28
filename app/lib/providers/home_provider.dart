import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/speech_profile.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

class HomeProvider extends ChangeNotifier {
  int selectedIndex = 1;

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
}
