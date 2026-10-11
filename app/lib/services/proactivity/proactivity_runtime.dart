import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:omi/backend/http/proactivity.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/proactivity/proactivity_outbox.dart';
import 'package:omi/utils/platform/platform_manager.dart';

abstract final class ProactivityRuntime {
  static const _key = 'proactivity_v2_outbox';
  static final ProactivityOutbox outbox = ProactivityOutbox(
    read: () => SharedPreferencesUtil().getString(_key),
    write: (value) async {
      if (value.isEmpty) {
        await SharedPreferencesUtil().remove(_key);
      } else {
        await SharedPreferencesUtil().saveString(_key, value);
      }
    },
    send: (id, event) {
      final epoch = outbox.epoch;
      return ProactivityApi(canSend: () => outbox.isCurrent(epoch)).outcome(id, event);
    },
    surface: () => Platform.isIOS ? 'ios' : 'android',
    ownerIsCurrent: (uid) => FirebaseAuth.instance.currentUser?.uid == uid,
    track: (action, channel, surface) =>
        PlatformManager.instance.analytics.proactivityOutcome(action: action, channel: channel, surface: surface),
  );
}
