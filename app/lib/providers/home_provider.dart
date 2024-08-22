import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/speech_profile.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

class HomeProvider extends ChangeNotifier {
  Future setupHasSpeakerProfile() async {
    SharedPreferencesUtil().hasSpeakerProfile = await userHasSpeakerProfile();
    debugPrint('_setupHasSpeakerProfile: ${SharedPreferencesUtil().hasSpeakerProfile}');
    MixpanelManager().setUserProperty('Speaker Profile', SharedPreferencesUtil().hasSpeakerProfile);
    notifyListeners();
  }
}
