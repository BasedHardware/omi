import 'package:flutter/material.dart';

class NoDeviceOnboardingProvider extends ChangeNotifier {
  static final NoDeviceOnboardingProvider _instance = NoDeviceOnboardingProvider._internal();
  factory NoDeviceOnboardingProvider() => _instance;
  NoDeviceOnboardingProvider._internal();

  String _fullName = '';
  String get fullName => _fullName;

  List<String> _audiences = [];
  List<String> get audiences => _audiences;

  String _twitterHandle = '';
  String get twitterHandle => _twitterHandle;

  void setFullName(String name) {
    _fullName = name;
    notifyListeners();
  }

  void setAudiences(List<String> audiences) {
    _audiences = audiences;
    notifyListeners();
  }

  void setTwitterHandle(String handle) {
    _twitterHandle = handle;
    notifyListeners();
  }

  // We can add more fields here as needed for the flow
  // For example: social handles, preferences, etc.
} 