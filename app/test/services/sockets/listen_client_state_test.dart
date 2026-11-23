import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/sockets/listen_client_state.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final state = ListenClientState.instance;

  setUp(() => state.resetForTest(foreground: true));

  test('an open capture page in front is a visible transcript', () {
    state.capturePageOpened();
    expect(state.value.toJson(), {'type': 'client_state', 'foreground': true, 'transcript_visible': true});
  });

  test('backgrounding hides the transcript even with the capture page still open', () {
    state.capturePageOpened();
    state.onLifecycle(AppLifecycleState.paused);
    expect(state.value.foreground, isFalse);
    expect(state.value.transcriptVisible, isFalse);
    state.onLifecycle(AppLifecycleState.resumed);
    expect(state.value.transcriptVisible, isTrue);
  });

  test('the notification shade (inactive) still counts as in front', () {
    state.onLifecycle(AppLifecycleState.inactive);
    expect(state.value.foreground, isTrue);
  });

  test('closing the page, or closing it twice, never goes negative', () {
    state.capturePageOpened();
    state.capturePageClosed();
    state.capturePageClosed();
    expect(state.value.transcriptVisible, isFalse);
    state.capturePageOpened();
    expect(state.value.transcriptVisible, isTrue);
  });

  test('listeners fire only when the reported state changes', () {
    var calls = 0;
    void listener() => calls++;
    state.addListener(listener);
    state.onLifecycle(AppLifecycleState.resumed); // already foreground: no change
    state.capturePageOpened();
    state.onLifecycle(AppLifecycleState.hidden);
    state.removeListener(listener);
    expect(calls, 2);
  });
}
