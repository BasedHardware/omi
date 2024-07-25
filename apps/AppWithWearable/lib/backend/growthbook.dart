import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/env.dart';
import 'package:growthbook_sdk_flutter/growthbook_sdk_flutter.dart';

class GrowthbookUtil {
  static final GrowthbookUtil _instance = GrowthbookUtil._internal();
  static GrowthBookSDK? _gb;

  factory GrowthbookUtil() {
    return _instance;
  }

  GrowthbookUtil._internal();

  static Future<void> init() async {
    if (Env.growthbookApiKey == null) return;
    var attr = {
      'id': SharedPreferencesUtil().uid,
      'device': Platform.isAndroid ? 'android' : 'ios',
    };
    _gb = await GBSDKBuilderApp(
      apiKey: Env.growthbookApiKey!,
      backgroundSync: true,
      enable: true,
      attributes: attr,
      growthBookTrackingCallBack: (gbExperiment, gbExperimentResult) {
        debugPrint('growthBookTrackingCallBack: $gbExperiment $gbExperimentResult');
      },
      hostURL: 'https://cdn.growthbook.io/',
      qaMode: true,
      gbFeatures: {
        // 'server-transcript': GBFeature(defaultValue: true),
        'streaming-transcript': GBFeature(defaultValue: false),
      },
    ).initialize();
    _gb!.setAttributes(attr);
  }

  bool hasStreamingTranscriptFeatureOn() {
    return true;
    if (!SharedPreferencesUtil().useTranscriptServer) return false;
    var feature = _gb!.feature('streaming-transcript');
    var enabled = feature.on;
    return enabled;
  }
}
