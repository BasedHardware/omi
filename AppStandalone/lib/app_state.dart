import 'package:flutter/material.dart';
import '/backend/backend.dart';
import '/backend/schema/structs/index.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'flutter_flow/flutter_flow_util.dart';
import 'dart:convert';

class FFAppState extends ChangeNotifier {
  static FFAppState _instance = FFAppState._internal();

  factory FFAppState() {
    return _instance;
  }

  FFAppState._internal();

  static void reset() {
    _instance = FFAppState._internal();
  }

  Future initializePersistedState() async {
    prefs = await SharedPreferences.getInstance();
    _safeInit(() {
      _speechWasActivatedByUser =
          prefs.getBool('ff_speechWasActivatedByUser') ??
              _speechWasActivatedByUser;
    });
    _safeInit(() {
      _firstIntroNotificationWasAlreadyCreated =
          prefs.getBool('ff_firstIntroNotificationWasAlreadyCreated') ??
              _firstIntroNotificationWasAlreadyCreated;
    });
    _safeInit(() {
      _selectedLanguage =
          prefs.getString('ff_selectedLanguage') ?? _selectedLanguage;
    });
    _safeInit(() {
      if (prefs.containsKey('ff_chatHistory')) {
        try {
          _chatHistory = jsonDecode(prefs.getString('ff_chatHistory') ?? '');
        } catch (e) {
          print("Can't decode persisted json. Error: $e.");
        }
      }
    });
  }

  void update(VoidCallback callback) {
    callback();
    notifyListeners();
  }

  late SharedPreferences prefs;

  String _stt = '';
  String get stt => _stt;
  set stt(String value) {
    _stt = value;
  }

  String _response = '';
  String get response => _response;
  set response(String value) {
    _response = value;
  }

  String _question = '';
  String get question => _question;
  set question(String value) {
    _question = value;
  }

  String _lastMemory = '';
  String get lastMemory => _lastMemory;
  set lastMemory(String value) {
    _lastMemory = value;
  }

  String _AllButLastMemory = '';
  String get AllButLastMemory => _AllButLastMemory;
  set AllButLastMemory(String value) {
    _AllButLastMemory = value;
  }

  bool _DisableRecording = false;
  bool get DisableRecording => _DisableRecording;
  set DisableRecording(bool value) {
    _DisableRecording = value;
  }

  bool _stopAction = false;
  bool get stopAction => _stopAction;
  set stopAction(bool value) {
    _stopAction = value;
  }

  bool _isSpeechRunning = false;
  bool get isSpeechRunning => _isSpeechRunning;
  set isSpeechRunning(bool value) {
    _isSpeechRunning = value;
  }

  DateTime? _latestUse;
  DateTime? get latestUse => _latestUse;
  set latestUse(DateTime? value) {
    _latestUse = value;
  }

  bool _swtest = false;
  bool get swtest => _swtest;
  set swtest(bool value) {
    _swtest = value;
  }

  bool _speechWorkin = false;
  bool get speechWorkin => _speechWorkin;
  set speechWorkin(bool value) {
    _speechWorkin = value;
  }

  bool _speechWasActivatedByUser = false;
  bool get speechWasActivatedByUser => _speechWasActivatedByUser;
  set speechWasActivatedByUser(bool value) {
    _speechWasActivatedByUser = value;
    prefs.setBool('ff_speechWasActivatedByUser', value);
  }

  String _LastMemoryStructured = '';
  String get LastMemoryStructured => _LastMemoryStructured;
  set LastMemoryStructured(String value) {
    _LastMemoryStructured = value;
  }

  bool _RecordingPopupIsShown = false;
  bool get RecordingPopupIsShown => _RecordingPopupIsShown;
  set RecordingPopupIsShown(bool value) {
    _RecordingPopupIsShown = value;
  }

  List<dynamic> _dailyMemories = [];
  List<dynamic> get dailyMemories => _dailyMemories;
  set dailyMemories(List<dynamic> value) {
    _dailyMemories = value;
  }

  void addToDailyMemories(dynamic value) {
    _dailyMemories.add(value);
  }

  void removeFromDailyMemories(dynamic value) {
    _dailyMemories.remove(value);
  }

  void removeAtIndexFromDailyMemories(int index) {
    _dailyMemories.removeAt(index);
  }

  void updateDailyMemoriesAtIndex(
    int index,
    dynamic Function(dynamic) updateFn,
  ) {
    _dailyMemories[index] = updateFn(_dailyMemories[index]);
  }

  void insertAtIndexInDailyMemories(int index, dynamic value) {
    _dailyMemories.insert(index, value);
  }

  String _openaidaily = '';
  String get openaidaily => _openaidaily;
  set openaidaily(String value) {
    _openaidaily = value;
  }

  String _currentPlatform = '';
  String get currentPlatform => _currentPlatform;
  set currentPlatform(String value) {
    _currentPlatform = value;
  }

  String _lastTranscript = '';
  String get lastTranscript => _lastTranscript;
  set lastTranscript(String value) {
    _lastTranscript = value;
  }

  bool _commandIsProcessing = false;
  bool get commandIsProcessing => _commandIsProcessing;
  set commandIsProcessing(bool value) {
    _commandIsProcessing = value;
  }

  int _testCountRunsOfNotifications = 0;
  int get testCountRunsOfNotifications => _testCountRunsOfNotifications;
  set testCountRunsOfNotifications(int value) {
    _testCountRunsOfNotifications = value;
  }

  int _testCallBackIncrement = 0;
  int get testCallBackIncrement => _testCallBackIncrement;
  set testCallBackIncrement(int value) {
    _testCallBackIncrement = value;
  }

  bool _firstIntroNotificationWasAlreadyCreated = false;
  bool get firstIntroNotificationWasAlreadyCreated =>
      _firstIntroNotificationWasAlreadyCreated;
  set firstIntroNotificationWasAlreadyCreated(bool value) {
    _firstIntroNotificationWasAlreadyCreated = value;
    prefs.setBool('ff_firstIntroNotificationWasAlreadyCreated', value);
  }

  List<LocaleStruct> _languages = [];
  List<LocaleStruct> get languages => _languages;
  set languages(List<LocaleStruct> value) {
    _languages = value;
  }

  void addToLanguages(LocaleStruct value) {
    _languages.add(value);
  }

  void removeFromLanguages(LocaleStruct value) {
    _languages.remove(value);
  }

  void removeAtIndexFromLanguages(int index) {
    _languages.removeAt(index);
  }

  void updateLanguagesAtIndex(
    int index,
    LocaleStruct Function(LocaleStruct) updateFn,
  ) {
    _languages[index] = updateFn(_languages[index]);
  }

  void insertAtIndexInLanguages(int index, LocaleStruct value) {
    _languages.insert(index, value);
  }

  String _selectedLanguage = '';
  String get selectedLanguage => _selectedLanguage;
  set selectedLanguage(String value) {
    _selectedLanguage = value;
    prefs.setString('ff_selectedLanguage', value);
  }

  String _feedback = '';
  String get feedback => _feedback;
  set feedback(String value) {
    _feedback = value;
  }

  String _isFeedbackUseful = '';
  String get isFeedbackUseful => _isFeedbackUseful;
  set isFeedbackUseful(String value) {
    _isFeedbackUseful = value;
  }

  String _commandState = 'Query';
  String get commandState => _commandState;
  set commandState(String value) {
    _commandState = value;
  }

  String _test = '';
  String get test => _test;
  set test(String value) {
    _test = value;
  }

  String _test2 = '';
  String get test2 => _test2;
  set test2(String value) {
    _test2 = value;
  }

  String _inputContent = '';
  String get inputContent => _inputContent;
  set inputContent(String value) {
    _inputContent = value;
  }

  dynamic _chatHistory =
      jsonDecode('[{\"role\":\"system\",\"content\":\"empty\"}]');
  dynamic get chatHistory => _chatHistory;
  set chatHistory(dynamic value) {
    _chatHistory = value;
    prefs.setString('ff_chatHistory', jsonEncode(value));
  }

  bool _memoryCreationProcessing = false;
  bool get memoryCreationProcessing => _memoryCreationProcessing;
  set memoryCreationProcessing(bool value) {
    _memoryCreationProcessing = value;
  }

  List<String> _testlist = [];
  List<String> get testlist => _testlist;
  set testlist(List<String> value) {
    _testlist = value;
  }

  void addToTestlist(String value) {
    _testlist.add(value);
  }

  void removeFromTestlist(String value) {
    _testlist.remove(value);
  }

  void removeAtIndexFromTestlist(int index) {
    _testlist.removeAt(index);
  }

  void updateTestlistAtIndex(
    int index,
    String Function(String) updateFn,
  ) {
    _testlist[index] = updateFn(_testlist[index]);
  }

  void insertAtIndexInTestlist(int index, String value) {
    _testlist.insert(index, value);
  }
}

void _safeInit(Function() initializeField) {
  try {
    initializeField();
  } catch (_) {}
}

Future _safeInitAsync(Function() initializeField) async {
  try {
    await initializeField();
  } catch (_) {}
}
