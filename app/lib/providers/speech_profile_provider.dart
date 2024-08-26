import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';

class SpeechProfileProvider extends ChangeNotifier {
  bool? permissionEnabled;
  bool loading = false;

  changeLoadingState() => loading = !loading;

  Future setupSpeechRecording() async {
    final permission = await getStoreRecordingPermission();
    permissionEnabled = permission;
    if (permission != null) {
      SharedPreferencesUtil().permissionStoreRecordingsEnabled = permission;
    }
  }
}
