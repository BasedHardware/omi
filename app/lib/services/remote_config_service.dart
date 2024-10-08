import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_remote_config/firebase_remote_config.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/env/env.dart';

String constApiBaseUrl = "";
String constGoogleMapsApiKey = "";
String constGrowthBookApiKey = "";
String constMixpanelProjectToken = "";
String constOpenaiApiKey = "";
String constRechargeAppApiKey = "";

class RemoteConfigService {
  RemoteConfigService({required FirebaseRemoteConfig remoteConfig})
      : _remoteConfig = remoteConfig;
  final FirebaseRemoteConfig _remoteConfig;

  final defaults = <String, dynamic>{
    RemoteConstant.apiBaseUrl: Env.apiBaseUrl,
    RemoteConstant.googleMapsApiKey: Env.googleMapsApiKey,
    RemoteConstant.growthBookApiKey: Env.growthbookApiKey,
    RemoteConstant.mixpanelProjectToken: Env.mixpanelProjectToken,
    RemoteConstant.openaiApiKey: Env.openAIAPIKey,
    RemoteConstant.rechargeAppApiKey: Env.rechargeAppApiKey,
  };

  static RemoteConfigService? _instance;

  static Future<RemoteConfigService> getInstance() async {
    await Firebase.initializeApp();
    _instance = RemoteConfigService(
      // ignore: await_only_futures
      remoteConfig: await FirebaseRemoteConfig.instance,
    );
    return _instance!;
  }

  Future initialize() async {
    try {
      await _remoteConfig.setDefaults(defaults);
      await _fetchAndActive();

      constApiBaseUrl = _remoteConfig.getString(RemoteConstant.apiBaseUrl);

      constGoogleMapsApiKey =
          _remoteConfig.getString(RemoteConstant.googleMapsApiKey);

      constGrowthBookApiKey =
          _remoteConfig.getString(RemoteConstant.growthBookApiKey);

      constMixpanelProjectToken =
          _remoteConfig.getString(RemoteConstant.mixpanelProjectToken);

      constOpenaiApiKey = _remoteConfig.getString(RemoteConstant.openaiApiKey);

      // debugPrint("setupRemoteConfig"
      //     " -> $constApiBaseUrl"
      //     " -> $constGoogleMapsApiKey"
      //     " -> $constGrowthBookApiKey"
      //     " -> $constMixpanelProjectToken"
      //     " -> $constOpenaiApiKey");
    } catch (e) {
      debugPrint("Unable to fetch config. Default value will be used");
    }
  }

  Future _fetchAndActive() async {
    await _remoteConfig.fetch();
    await _remoteConfig.setConfigSettings(
      RemoteConfigSettings(
        fetchTimeout: const Duration(),
        minimumFetchInterval: const Duration(milliseconds: 500),
      ),
    );
    await _remoteConfig.fetchAndActivate();
  }
}

class RemoteConstant {
  static const String apiBaseUrl = "API_BASE_URL";
  static const String googleMapsApiKey = "GOOGLE_MAPS_API_KEY";
  static const String growthBookApiKey = "GROWTHBOOK_API_KEY";
  static const String mixpanelProjectToken = "MIXPANEL_PROJECT_TOKEN";
  static const String openaiApiKey = "OPENAI_API_KEY";
  static const String rechargeAppApiKey = "RECHARGEAPP_API_KEY";
}
