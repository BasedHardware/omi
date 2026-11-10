import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/experiments/episode_detail_gate.dart';

void main() {
  test('on by default, kill flag true restores old UI, reader failures stay on', () async {
    expect(
        await EpisodeDetailGate.enabled(readFlag: (key) async {
          expect(key, 'mobile-episode-detail-redesign-disabled');
          return false;
        }),
        isTrue);
    expect(await EpisodeDetailGate.enabled(readFlag: (_) async => true), isFalse);
    expect(await EpisodeDetailGate.enabled(readFlag: (_) async => throw StateError('offline')), isTrue);
  });
}
