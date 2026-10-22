import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/utils/live_start_anchor.dart';

final _t0 = DateTime.utc(2026, 10, 22, 2, 18);

Episode _episode(DateTime startedAt, {String id = 'ep1'}) => Episode(
    id: id, live: true, startedAt: startedAt, lastActivityAt: startedAt, title: '', conversationIds: const ['c1']);

void main() {
  group('LiveStartAnchor', () {
    test('a pendant lease lapsing for a tick keeps the running start', () {
      final anchor = LiveStartAnchor();
      DateTime? at(int s, DateTime? capture) =>
          anchor.resolve(episode: null, captureStart: capture, streaming: true, now: _t0.add(Duration(seconds: s)));
      expect(at(0, _t0), _t0);
      // The verified-ingress start reads null between health updates: still the same start, never 0s.
      expect(at(30, null), _t0);
      expect(at(31, _t0), _t0);
    });

    test('a reconnect re-arming the capture start later does not restart the count', () {
      final anchor = LiveStartAnchor();
      anchor.resolve(episode: null, captureStart: _t0, streaming: true, now: _t0);
      final later = _t0.add(const Duration(minutes: 9));
      expect(anchor.resolve(episode: null, captureStart: later, streaming: true, now: later), _t0);
    });

    test('the server episode start wins, and its close lets the next stretch count fresh', () {
      final anchor = LiveStartAnchor();
      final now = _t0.add(const Duration(minutes: 8));
      expect(anchor.resolve(episode: _episode(_t0), captureStart: now, streaming: true, now: now), _t0);
      final next = now.add(const Duration(minutes: 40));
      expect(anchor.resolve(episode: null, captureStart: next, streaming: true, now: next), next);
    });

    test('a server clock ahead of the phone falls back to the capture start', () {
      final anchor = LiveStartAnchor();
      final ahead = _episode(_t0.add(const Duration(seconds: 20)));
      expect(anchor.resolve(episode: ahead, captureStart: _t0, streaming: true, now: _t0), _t0);
    });

    test('nothing streaming means no running start', () {
      final anchor = LiveStartAnchor();
      anchor.resolve(episode: null, captureStart: _t0, streaming: true, now: _t0);
      expect(anchor.resolve(episode: null, captureStart: null, streaming: false, now: _t0), isNull);
    });
  });

  test('a watcher polls sooner until the live episode appears, then relaxes', () {
    fakeAsync((async) {
      var reads = 0;
      Episode? live;
      final provider = EpisodeProvider(fetchLive: () async {
        reads++;
        return ApiSuccess(EpisodeRead(enabled: true, episode: live));
      });
      provider.watch();
      async.flushMicrotasks();
      expect(reads, 1);
      async.elapse(EpisodeProvider.pendingPollInterval);
      expect(reads, 2);
      live = _episode(_t0);
      async.elapse(EpisodeProvider.pendingPollInterval);
      expect(reads, 3);
      // Now that it is shown, the next read waits the normal interval.
      async.elapse(EpisodeProvider.pendingPollInterval);
      expect(reads, 3);
      async.elapse(EpisodeProvider.pollInterval);
      expect(reads, 4);
      provider.unwatch();
      provider.dispose();
    });
  });
}
