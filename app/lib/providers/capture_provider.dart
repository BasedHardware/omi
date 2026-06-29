import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/capture/capture_external_actions.dart';

class CaptureProvider extends CaptureController {
  CaptureProvider({CaptureExternalActions? externalActions}) : super(externalActions: externalActions);
}
