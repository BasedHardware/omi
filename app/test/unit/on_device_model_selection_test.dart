import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/freemium_transcription_service.dart';

void main() {
  group('FreemiumTranscriptionService.chooseModelPath', () {
    test('returns null when nothing is downloaded', () {
      expect(FreemiumTranscriptionService.chooseModelPath(const []), isNull);
    });

    test('the selected model wins over the smallest one', () {
      // The reported case: base was downloaded alongside an older tiny, and tiny ran.
      final path = FreemiumTranscriptionService.chooseModelPath(
        const ['/m/models/ggml-tiny.bin', '/m/models/ggml-base.bin'],
        preferredModel: 'base',
      );
      expect(path, '/m/models/ggml-base.bin');
    });

    test('an explicit path wins over the selected model name', () {
      final path = FreemiumTranscriptionService.chooseModelPath(
        const ['/m/models/ggml-tiny.bin', '/m/models/ggml-small.bin'],
        preferredModel: 'tiny',
        preferredPath: '/m/models/ggml-small.bin',
      );
      expect(path, '/m/models/ggml-small.bin');
    });

    test('a preferred path that is gone falls through to the model name', () {
      final path = FreemiumTranscriptionService.chooseModelPath(
        const ['/m/models/ggml-base.bin'],
        preferredModel: 'base',
        preferredPath: '/m/models/ggml-medium.bin',
      );
      expect(path, '/m/models/ggml-base.bin');
    });

    test('falls back to the smallest model when nothing was selected', () {
      final path = FreemiumTranscriptionService.chooseModelPath(
        const ['/m/models/ggml-small.bin', '/m/models/ggml-base.bin', '/m/models/ggml-tiny.bin'],
      );
      expect(path, '/m/models/ggml-tiny.bin');
    });

    test('falls back to the smallest available when the selection is absent', () {
      final path = FreemiumTranscriptionService.chooseModelPath(
        const ['/m/models/ggml-medium.bin', '/m/models/ggml-base.bin'],
        preferredModel: 'large-v2',
      );
      expect(path, '/m/models/ggml-base.bin');
    });

    test('matches Windows separators on the preferred path', () {
      final path = FreemiumTranscriptionService.chooseModelPath(
        const [r'C:\app\models\ggml-tiny.bin', r'C:\app\models\ggml-base.bin'],
        preferredPath: r'C:\app\models\ggml-base.bin',
      );
      expect(path, r'C:\app\models\ggml-base.bin');
    });

    test('an unrecognised file is still used rather than reporting nothing', () {
      final path = FreemiumTranscriptionService.chooseModelPath(
        const ['/m/models/custom-model.bin'],
        preferredModel: 'tiny',
      );
      expect(path, '/m/models/custom-model.bin');
    });
  });
}
