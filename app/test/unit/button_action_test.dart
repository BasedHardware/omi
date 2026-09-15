import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/button_action.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('single tap', () {
    test('an unset preference keeps the current ask-a-question behaviour', () {
      expect(SharedPreferencesUtil().singleTapAction, 0);
      expect(resolveSingleTapAction(SharedPreferencesUtil().singleTapAction), ButtonAction.askQuestion);
    });

    test('maps each stored code to its action', () {
      expect(resolveSingleTapAction(0), ButtonAction.askQuestion);
      expect(resolveSingleTapAction(1), ButtonAction.endConversation);
      expect(resolveSingleTapAction(2), ButtonAction.toggleMute);
      expect(resolveSingleTapAction(3), ButtonAction.starConversation);
    });

    test('falls back to ask a question for an unknown code', () {
      expect(resolveSingleTapAction(99), ButtonAction.askQuestion);
      expect(resolveSingleTapAction(-1), ButtonAction.askQuestion);
    });

    test('round trips through the preference', () async {
      SharedPreferencesUtil().singleTapAction = 2;

      expect(resolveSingleTapAction(SharedPreferencesUtil().singleTapAction), ButtonAction.toggleMute);
    });
  });

  group('onboarding', () {
    test('step one always asks a question, whatever the mapping is', () {
      expect(
        resolveSingleTapActionForSession(2, onboardingAskQuestionStep: true),
        ButtonAction.askQuestion,
      );
      expect(
        resolveSingleTapActionForSession(3, onboardingAskQuestionStep: true),
        ButtonAction.askQuestion,
      );
    });

    test('outside that step the stored mapping applies', () {
      expect(
        resolveSingleTapActionForSession(2, onboardingAskQuestionStep: false),
        ButtonAction.toggleMute,
      );
      expect(
        resolveSingleTapActionForSession(0, onboardingAskQuestionStep: false),
        ButtonAction.askQuestion,
      );
    });
  });

  group('double tap', () {
    test('keeps the existing stored encoding', () {
      expect(resolveDoubleTapAction(0), ButtonAction.endConversation);
      expect(resolveDoubleTapAction(1), ButtonAction.toggleMute);
      expect(resolveDoubleTapAction(2), ButtonAction.starConversation);
    });

    test('an unset preference still ends the conversation', () {
      expect(SharedPreferencesUtil().doubleTapAction, 0);
      expect(resolveDoubleTapAction(SharedPreferencesUtil().doubleTapAction), ButtonAction.endConversation);
    });

    test('falls back to ending the conversation for an unknown code', () {
      expect(resolveDoubleTapAction(42), ButtonAction.endConversation);
    });

    test('can be turned off', () {
      expect(resolveDoubleTapAction(3), ButtonAction.none);
    });
  });

  group('triple tap', () {
    test('an unset preference ends the conversation', () {
      expect(SharedPreferencesUtil().tripleTapAction, 0);
      expect(resolveTripleTapAction(SharedPreferencesUtil().tripleTapAction), ButtonAction.endConversation);
    });

    test('uses the same encoding as double tap', () {
      expect(resolveTripleTapAction(1), ButtonAction.toggleMute);
      expect(resolveTripleTapAction(2), ButtonAction.starConversation);
      expect(resolveTripleTapAction(3), ButtonAction.none);
      expect(resolveTripleTapAction(7), ButtonAction.endConversation);
    });
  });

  group('tap dispatcher', () {
    ButtonTapDispatcher dispatcher({
      ButtonAction single = ButtonAction.askQuestion,
      ButtonAction double = ButtonAction.endConversation,
      ButtonAction triple = ButtonAction.endConversation,
    }) {
      return ButtonTapDispatcher((count) => switch (count) {
            1 => single,
            2 => double,
            3 => triple,
            _ => ButtonAction.none,
          });
    }

    test('with every tap mapped it waits for the sequence to end before single and double', () {
      final d = dispatcher(double: ButtonAction.toggleMute);
      expect(d.onTap(1), isNull);
      expect(d.onSequenceEnd(1), ButtonAction.askQuestion);
      expect(d.onTap(1), isNull);
      expect(d.onTap(2), isNull);
      expect(d.onSequenceEnd(2), ButtonAction.toggleMute);
    });

    test('the highest mapped count fires on the tap itself', () {
      final d = dispatcher();
      expect(d.onTap(1), isNull);
      expect(d.onTap(2), isNull);
      expect(d.onTap(3), ButtonAction.endConversation);
      expect(d.onSequenceEnd(3), isNull);
    });

    test('double tap fires without waiting when triple tap is off', () {
      final d = dispatcher(double: ButtonAction.toggleMute, triple: ButtonAction.none);
      expect(d.onTap(1), isNull);
      expect(d.onTap(2), ButtonAction.toggleMute);
      expect(d.onSequenceEnd(2), isNull);
    });

    test('single tap fires without waiting when double and triple are off', () {
      final d = dispatcher(double: ButtonAction.none, triple: ButtonAction.none);
      expect(d.onTap(1), ButtonAction.askQuestion);
      expect(d.onSequenceEnd(1), isNull);
    });

    test('a turned off count does nothing when its sequence ends', () {
      final d = dispatcher(double: ButtonAction.none);
      expect(d.onTap(1), isNull);
      expect(d.onTap(2), isNull);
      expect(d.onSequenceEnd(2), isNull);
    });

    test('extra taps after the action fired do not fire it again', () {
      final d = dispatcher();
      d.onTap(1);
      d.onTap(2);
      expect(d.onTap(3), ButtonAction.endConversation);
      expect(d.onTap(4), isNull);
      expect(d.onSequenceEnd(4), isNull);
    });

    test('a new sequence starts clean even if the last end was never received', () {
      final d = dispatcher(double: ButtonAction.none, triple: ButtonAction.none);
      expect(d.onTap(1), ButtonAction.askQuestion);
      expect(d.onTap(1), ButtonAction.askQuestion);
    });
  });
}
