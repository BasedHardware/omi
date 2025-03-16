import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
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
    print('GrowthbookUtil init');
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
    ).initialize();
    _gb!.setAttributes(attr);
  }

  bool displayOmiFeedback() {
    return (_gb?.feature('omi-feedback').on) ?? false;
  }

  bool displayMemoriesSearchBar() {
    return (_gb?.feature('memories-search-bar').on) ?? false;
  }

  bool isOmiFeedbackEnabled() {
    if (_gb == null) return false;
    if (_gb!.feature('omi-feedback').off) return false;
    return SharedPreferencesUtil().optInEmotionalFeedback;
  }
}
