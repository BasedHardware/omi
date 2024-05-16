import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '/backend/schema/structs/index.dart';
import 'flutter_flow/flutter_flow_util.dart';

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
      _speechWasActivatedByUser = prefs.getBool('ff_speechWasActivatedByUser') ?? _speechWasActivatedByUser;
    });
    _safeInit(() {
      _firstIntroNotificationWasAlreadyCreated =
          prefs.getBool('ff_firstIntroNotificationWasAlreadyCreated') ?? _firstIntroNotificationWasAlreadyCreated;
    });
    _safeInit(() {
      _selectedLanguage = prefs.getString('ff_selectedLanguage') ?? _selectedLanguage;
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
    _safeInit(() async => {
          memories = await MemoryStorage.getAllMemories(filterOutUseless: true),
        });
  }

  void update(VoidCallback callback) {
    callback();
    notifyListeners();
  }

  late SharedPreferences prefs;

  String _stt = '';

  String get stt => _stt;

  set stt(String _value) {
    _stt = _value;
  }

  String _response = '';

  String get response => _response;

  set response(String _value) {
    _response = _value;
  }

  String _question = '';

  String get question => _question;

  set question(String _value) {
    _question = _value;
  }

  String _lastMemory = '';

  String get lastMemory => _lastMemory;

  set lastMemory(String _value) {
    _lastMemory = _value;
  }

  String _AllButLastMemory = '';

  String get AllButLastMemory => _AllButLastMemory;

  set AllButLastMemory(String _value) {
    _AllButLastMemory = _value;
  }

  bool _DisableRecording = false;

  bool get DisableRecording => _DisableRecording;

  set DisableRecording(bool _value) {
    _DisableRecording = _value;
  }

  bool _stopAction = false;

  bool get stopAction => _stopAction;

  set stopAction(bool _value) {
    _stopAction = _value;
  }

  bool _isSpeechRunning = false;

  bool get isSpeechRunning => _isSpeechRunning;

  set isSpeechRunning(bool _value) {
    _isSpeechRunning = _value;
  }

  DateTime? _latestUse;

  DateTime? get latestUse => _latestUse;

  set latestUse(DateTime? _value) {
    _latestUse = _value;
  }

  bool _swtest = false;

  bool get swtest => _swtest;

  set swtest(bool _value) {
    _swtest = _value;
  }

  bool _speechWorkin = false;

  bool get speechWorkin => _speechWorkin;

  set speechWorkin(bool _value) {
    _speechWorkin = _value;
  }

  bool _speechWasActivatedByUser = false;

  bool get speechWasActivatedByUser => _speechWasActivatedByUser;

  set speechWasActivatedByUser(bool _value) {
    _speechWasActivatedByUser = _value;
    prefs.setBool('ff_speechWasActivatedByUser', _value);
  }

  String _LastMemoryStructured = '';

  String get LastMemoryStructured => _LastMemoryStructured;

  set LastMemoryStructured(String _value) {
    _LastMemoryStructured = _value;
  }

  bool _RecordingPopupIsShown = false;

  bool get RecordingPopupIsShown => _RecordingPopupIsShown;

  set RecordingPopupIsShown(bool _value) {
    _RecordingPopupIsShown = _value;
  }

  List<MemoryRecord> _memories = [];

  List<MemoryRecord> get memories => _memories;

  set memories(List<MemoryRecord> value) {
    _memories = value;
  }

  String _openaidaily = '';

  String get openaidaily => _openaidaily;

  set openaidaily(String _value) {
    _openaidaily = _value;
  }

  String _currentPlatform = '';

  String get currentPlatform => _currentPlatform;

  set currentPlatform(String _value) {
    _currentPlatform = _value;
  }

  String _lastTranscript = '';

  String get lastTranscript => _lastTranscript;

  set lastTranscript(String _value) {
    _lastTranscript = _value;
  }

  bool _commandIsProcessing = false;

  bool get commandIsProcessing => _commandIsProcessing;

  set commandIsProcessing(bool _value) {
    _commandIsProcessing = _value;
  }

  int _testCountRunsOfNotifications = 0;

  int get testCountRunsOfNotifications => _testCountRunsOfNotifications;

  set testCountRunsOfNotifications(int _value) {
    _testCountRunsOfNotifications = _value;
  }

  int _testCallBackIncrement = 0;

  int get testCallBackIncrement => _testCallBackIncrement;

  set testCallBackIncrement(int _value) {
    _testCallBackIncrement = _value;
  }

  bool _firstIntroNotificationWasAlreadyCreated = false;

  bool get firstIntroNotificationWasAlreadyCreated => _firstIntroNotificationWasAlreadyCreated;

  set firstIntroNotificationWasAlreadyCreated(bool _value) {
    _firstIntroNotificationWasAlreadyCreated = _value;
    prefs.setBool('ff_firstIntroNotificationWasAlreadyCreated', _value);
  }

  List<LocaleStruct> _languages = [];

  List<LocaleStruct> get languages => _languages;

  set languages(List<LocaleStruct> _value) {
    _languages = _value;
  }

  void addToLanguages(LocaleStruct _value) {
    _languages.add(_value);
  }

  void removeFromLanguages(LocaleStruct _value) {
    _languages.remove(_value);
  }

  void removeAtIndexFromLanguages(int _index) {
    _languages.removeAt(_index);
  }

  void updateLanguagesAtIndex(
    int _index,
    LocaleStruct Function(LocaleStruct) updateFn,
  ) {
    _languages[_index] = updateFn(_languages[_index]);
  }

  void insertAtIndexInLanguages(int _index, LocaleStruct _value) {
    _languages.insert(_index, _value);
  }

  String _selectedLanguage = '';

  String get selectedLanguage => _selectedLanguage;

  set selectedLanguage(String _value) {
    _selectedLanguage = _value;
    prefs.setString('ff_selectedLanguage', _value);
  }

  String _feedback = '';

  String get feedback => _feedback;

  set feedback(String _value) {
    _feedback = _value;
  }

  String _isFeedbackUseful = '';

  String get isFeedbackUseful => _isFeedbackUseful;

  set isFeedbackUseful(String _value) {
    _isFeedbackUseful = _value;
  }

  String _commandState = 'Query';

  String get commandState => _commandState;

  set commandState(String _value) {
    _commandState = _value;
  }

  String _test = '';

  String get test => _test;

  set test(String _value) {
    _test = _value;
  }

  String _test2 = '';

  String get test2 => _test2;

  set test2(String _value) {
    _test2 = _value;
  }

  String _inputContent = '';

  String get inputContent => _inputContent;

  set inputContent(String _value) {
    _inputContent = _value;
  }

  // TODO: migrate chatHistory to a model, and storage like MemoryRecord
  dynamic _chatHistory = jsonDecode('[{\"role\":\"system\",\"content\":\"empty\"}]');

  dynamic get chatHistory => _chatHistory;

  set chatHistory(dynamic _value) {
    _chatHistory = _value;
    prefs.setString('ff_chatHistory', jsonEncode(_value));
  }

  bool _memoryCreationProcessing = false;

  bool get memoryCreationProcessing => _memoryCreationProcessing;

  set memoryCreationProcessing(bool _value) {
    _memoryCreationProcessing = _value;
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
