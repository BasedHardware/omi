import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/button_action.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';

void main() {
  group('resolveSingleTapAction', () {
    test('defaults to ask question', () {
      expect(resolveSingleTapAction(0), ButtonAction.askQuestion);
      expect(resolveSingleTapAction(-1), ButtonAction.askQuestion);
      expect(resolveSingleTapAction(99), ButtonAction.askQuestion);
    });

    test('maps stored codes', () {
      expect(resolveSingleTapAction(1), ButtonAction.endConversation);
      expect(resolveSingleTapAction(2), ButtonAction.toggleMute);
      expect(resolveSingleTapAction(3), ButtonAction.starConversation);
    });

    test('onboarding step forces ask question', () {
      expect(
        resolveSingleTapActionForSession(2, onboardingAskQuestionStep: true),
        ButtonAction.askQuestion,
      );
      expect(
        resolveSingleTapActionForSession(2, onboardingAskQuestionStep: false),
        ButtonAction.toggleMute,
      );
    });
  });

  group('resolveDoubleTapAction / triple', () {
    test('maps legacy encoding including off', () {
      expect(resolveDoubleTapAction(0), ButtonAction.endConversation);
      expect(resolveDoubleTapAction(1), ButtonAction.toggleMute);
      expect(resolveDoubleTapAction(2), ButtonAction.starConversation);
      expect(resolveDoubleTapAction(3), ButtonAction.none);
      expect(resolveTripleTapAction(0), ButtonAction.endConversation);
      expect(resolveTripleTapAction(3), ButtonAction.none);
    });
  });

  group('ButtonTapDispatcher', () {
    ButtonAction actionFor(int count) {
      switch (count) {
        case 1:
          return ButtonAction.askQuestion;
        case 2:
          return ButtonAction.toggleMute;
        case 3:
          return ButtonAction.endConversation;
        default:
          return ButtonAction.none;
      }
    }

    test('waits when a higher count is mapped', () {
      final d = ButtonTapDispatcher(actionFor);
      expect(d.onTap(1), isNull);
      expect(d.onTap(2), isNull);
      expect(d.onSequenceEnd(2), ButtonAction.toggleMute);
    });

    test('fires immediately when no higher count is mapped', () {
      ButtonAction mapped(int count) {
        if (count == 1) return ButtonAction.askQuestion;
        return ButtonAction.none;
      }

      final d = ButtonTapDispatcher(mapped);
      expect(d.onTap(1), ButtonAction.askQuestion);
      expect(d.onSequenceEnd(1), isNull);
    });

    test('ignores sequence end with no prior taps', () {
      final d = ButtonTapDispatcher(actionFor);
      expect(d.onSequenceEnd(2), isNull);
    });

    test('triple fires on the third tap when mapped', () {
      final d = ButtonTapDispatcher(actionFor);
      expect(d.onTap(1), isNull);
      expect(d.onTap(2), isNull);
      expect(d.onTap(3), ButtonAction.endConversation);
      expect(d.onSequenceEnd(3), isNull);
    });
  });

  group('preferences defaults', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('unset doubleTapAction defaults to mute (issue #2825)', () {
      expect(SharedPreferencesUtil().doubleTapAction, 1);
      expect(resolveDoubleTapAction(SharedPreferencesUtil().doubleTapAction), ButtonAction.toggleMute);
    });

    test('stored doubleTapAction 0 keeps end conversation', () {
      SharedPreferencesUtil().doubleTapAction = 0;
      expect(SharedPreferencesUtil().doubleTapAction, 0);
      expect(resolveDoubleTapAction(0), ButtonAction.endConversation);
    });

    test('single and triple defaults', () {
      expect(SharedPreferencesUtil().singleTapAction, 0);
      expect(SharedPreferencesUtil().tripleTapAction, 0);
      expect(resolveSingleTapAction(0), ButtonAction.askQuestion);
      expect(resolveTripleTapAction(0), ButtonAction.endConversation);
    });
  });
}
