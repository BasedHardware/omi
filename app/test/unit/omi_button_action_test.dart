import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/omi_button_action.dart';

Future<void> _initPrefs(Map<String, Object> values) async {
  SharedPreferences.setMockInitialValues(values);
  await SharedPreferencesUtil.init();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('OmiButtonGesture.fromButtonState', () {
    test('maps the remappable firmware states and nothing else', () {
      expect(OmiButtonGesture.fromButtonState(OmiButtonState.singleTap), OmiButtonGesture.singleTap);
      expect(OmiButtonGesture.fromButtonState(OmiButtonState.doubleTap), OmiButtonGesture.doubleTap);
      expect(OmiButtonGesture.fromButtonState(OmiButtonState.tripleTap), OmiButtonGesture.tripleTap);

      // Press/release and the legacy long press are not user-configurable.
      expect(OmiButtonGesture.fromButtonState(OmiButtonState.longPress), isNull);
      expect(OmiButtonGesture.fromButtonState(OmiButtonState.press), isNull);
      expect(OmiButtonGesture.fromButtonState(OmiButtonState.release), isNull);
      expect(OmiButtonGesture.fromButtonState(0), isNull);
      expect(OmiButtonGesture.fromButtonState(7), isNull);
    });

    test('firmware wire values match omi/firmware/common/button_gesture.h', () {
      expect(OmiButtonState.singleTap, 1);
      expect(OmiButtonState.doubleTap, 2);
      expect(OmiButtonState.release, 5);
      expect(OmiButtonState.tripleTap, 6);
    });
  });

  group('OmiButtonAction stored encoding', () {
    test('keeps the historical doubleTapAction values and round-trips every action', () {
      expect(OmiButtonAction.endConversation.storedValue, 0);
      expect(OmiButtonAction.muteUnmute.storedValue, 1);
      expect(OmiButtonAction.starConversation.storedValue, 2);
      for (final action in OmiButtonAction.values) {
        expect(OmiButtonAction.fromStoredValue(action.storedValue), action);
      }
    });

    test('unknown or missing values resolve to null', () {
      expect(OmiButtonAction.fromStoredValue(null), isNull);
      expect(OmiButtonAction.fromStoredValue(99), isNull);
      expect(OmiButtonAction.fromStoredValue(-1), isNull);
    });
  });

  group('SharedPreferencesUtil button mapping', () {
    test('defaults follow #2825: ask question, mute/unmute, end conversation', () async {
      await _initPrefs({});
      final prefs = SharedPreferencesUtil();
      expect(prefs.buttonActionFor(OmiButtonGesture.singleTap), OmiButtonAction.askQuestion);
      expect(prefs.buttonActionFor(OmiButtonGesture.doubleTap), OmiButtonAction.muteUnmute);
      expect(prefs.buttonActionFor(OmiButtonGesture.tripleTap), OmiButtonAction.endConversation);
      expect(prefs.doubleTapAction, OmiButtonAction.muteUnmute.storedValue);
    });

    test('a doubleTapAction persisted by an older build is honoured as-is', () async {
      await _initPrefs({'doubleTapAction': 2});
      final prefs = SharedPreferencesUtil();
      expect(prefs.buttonActionFor(OmiButtonGesture.doubleTap), OmiButtonAction.starConversation);
      // Legacy int accessor still reads the same slot.
      expect(prefs.doubleTapAction, 2);
    });

    test('an explicit 0 stays end conversation rather than falling back to the default', () async {
      await _initPrefs({'doubleTapAction': 0});
      expect(SharedPreferencesUtil().buttonActionFor(OmiButtonGesture.doubleTap), OmiButtonAction.endConversation);
    });

    test('setButtonActionFor persists per gesture without touching the others', () async {
      await _initPrefs({});
      final prefs = SharedPreferencesUtil();
      await prefs.setButtonActionFor(OmiButtonGesture.tripleTap, OmiButtonAction.none);
      await prefs.setButtonActionFor(OmiButtonGesture.singleTap, OmiButtonAction.starConversation);

      expect(prefs.buttonActionFor(OmiButtonGesture.tripleTap), OmiButtonAction.none);
      expect(prefs.buttonActionFor(OmiButtonGesture.singleTap), OmiButtonAction.starConversation);
      expect(prefs.buttonActionFor(OmiButtonGesture.doubleTap), OmiButtonAction.muteUnmute);
      expect((await SharedPreferences.getInstance()).getInt('tripleTapAction'), OmiButtonAction.none.storedValue);
    });

    test('a stored value this build does not know falls back to the gesture default', () async {
      await _initPrefs({'singleTapAction': 42});
      expect(SharedPreferencesUtil().buttonActionFor(OmiButtonGesture.singleTap), OmiButtonAction.askQuestion);
    });

    test('the legacy int setter and the typed getter share one slot', () async {
      await _initPrefs({});
      final prefs = SharedPreferencesUtil();
      prefs.doubleTapAction = OmiButtonAction.endConversation.storedValue;
      await Future<void>.delayed(Duration.zero);
      expect(prefs.buttonActionFor(OmiButtonGesture.doubleTap), OmiButtonAction.endConversation);
    });
  });
}
