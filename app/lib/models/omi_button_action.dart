enum OmiButtonAction {
  endConversation(0),
  pauseResume(1),
  starConversation(2),
  askQuestion(3),
  noAction(4);

  const OmiButtonAction(this.value);

  final int value;

  static OmiButtonAction fromValue(int value,
      {required OmiButtonAction fallback}) {
    for (final action in values) {
      if (action.value == value) return action;
    }
    return fallback;
  }
}

enum OmiButtonPress {
  singleTap(1),
  doubleTap(2),
  tripleTap(6);

  const OmiButtonPress(this.state);

  final int state;

  static OmiButtonPress? fromState(int state) {
    for (final press in values) {
      if (press.state == state) return press;
    }
    return null;
  }
}
