// Live binding without the test pointer crosshair. The Flutter test runner constructs
// IntegrationTestWidgetsFlutterBinding before the test's main, so this subclass has to be created
// from flutter_test_config.dart, which runs first. Test taps are re-sourced as device events: the
// live binding then dispatches them and does not paint the crosshair.
import 'package:flutter/gestures.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

class QuietWalkBinding extends IntegrationTestWidgetsFlutterBinding {
  QuietWalkBinding() {
    shouldPropagateDevicePointerEvents = true;
    framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.fullyLive;
  }

  @override
  void handlePointerEvent(PointerEvent event) {
    if (pointerEventSource == TestBindingEventSource.test && shouldPropagateDevicePointerEvents) {
      withPointerEventSource(TestBindingEventSource.device, () => super.handlePointerEvent(event));
      return;
    }
    super.handlePointerEvent(event);
  }
}
