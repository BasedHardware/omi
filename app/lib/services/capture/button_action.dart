enum ButtonAction { askQuestion, endConversation, toggleMute, starConversation }

ButtonAction resolveSingleTapAction(int code) {
  switch (code) {
    case 1:
      return ButtonAction.endConversation;
    case 2:
      return ButtonAction.toggleMute;
    case 3:
      return ButtonAction.starConversation;
    default:
      return ButtonAction.askQuestion;
  }
}

ButtonAction resolveDoubleTapAction(int code) {
  switch (code) {
    case 1:
      return ButtonAction.toggleMute;
    case 2:
      return ButtonAction.starConversation;
    default:
      return ButtonAction.endConversation;
  }
}

ButtonAction resolveSingleTapActionForSession(int code, {required bool onboardingAskQuestionStep}) {
  if (onboardingAskQuestionStep) return ButtonAction.askQuestion;
  return resolveSingleTapAction(code);
}
