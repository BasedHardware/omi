import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

class CaptureProvider extends CaptureController {
  CaptureProvider({
    CaptureExternalActions? externalActions,
    Future<BleAudioCodec> Function(String deviceId)? audioCodecLoader,
    Future<bool> Function(String deviceId, int level)? speakerHaptic,
  }) : super(externalActions: externalActions, audioCodecLoader: audioCodecLoader, speakerHaptic: speakerHaptic);
}
