import 'package:omi/services/local_vision/local_vision_service.dart';

class TfliteYoloeDetector implements LocalVisionDetector {
  const TfliteYoloeDetector();

  @override
  Future<LocalVisionDetectorResult> detect(LocalVisionFrame frame) async {
    return const LocalVisionDetectorResult(detections: []);
  }

  Future<void> close() async {}
}
