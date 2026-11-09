import 'dart:async';

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
    test('server timer start replaces yesterday restart and follows same-id corrections', () {
      final anchor = LiveStartAnchor();
      final previousEnd = DateTime.utc(2026, 10, 28, 18, 32);
      final started = DateTime.utc(2026, 10, 29, 5, 46);
      final now = DateTime.utc(2026, 10, 29, 7, 11);
      anchor.restart(previousEnd);
      Episode current(DateTime at) =>
          Episode(id: 'current', live: true, startedAt: at, timerStartedAt: at, lastActivityAt: now);
      final start = anchor.resolve(episode: current(started), captureStart: previousEnd, streaming: true, now: now);
      expect(start, started);
      expect(now.difference(start!), const Duration(hours: 1, minutes: 25));
      final corrected = started.subtract(const Duration(minutes: 2));
      expect(
          anchor.resolve(episode: current(corrected), captureStart: previousEnd, streaming: true, now: now), corrected);
    });

    test('late uploaded capture time cannot rewind the current episode or a polling gap', () {
      final anchor = LiveStartAnchor();
      final recorded = DateTime.utc(2026, 10, 29, 1, 4);
      final currentStart = DateTime.utc(2026, 10, 29, 5, 46);
      final now = DateTime.utc(2026, 10, 29, 7, 11);
      final current = Episode(
        id: 'current',
        live: true,
        startedAt: currentStart,
        timerStartedAt: currentStart,
        lastActivityAt: now,
      );
      expect(anchor.resolve(episode: current, captureStart: recorded, streaming: true, now: now), currentStart);
      // A delayed capture timestamp during a short server polling gap cannot
      // replace the authoritative floor established by the current episode.
      expect(anchor.resolve(episode: null, captureStart: recorded, streaming: true, now: now), currentStart);
      expect(anchor.resolve(episode: null, captureStart: recorded, streaming: true, now: now), currentStart);
      expect(anchor.resolve(episode: current, captureStart: recorded, streaming: true, now: now), currentStart);
      expect(now.difference(currentStart), const Duration(hours: 1, minutes: 25));
    });

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

    test('live episode start owns elapsed time while the episode is open', () {
      final anchor = LiveStartAnchor();
      final now = _t0.add(const Duration(minutes: 8));
      expect(anchor.resolve(episode: _episode(_t0), captureStart: now, streaming: true, now: now), _t0);
      final next = now.add(const Duration(minutes: 40));
      expect(anchor.resolve(episode: _episode(_t0), captureStart: next, streaming: true, now: next), _t0);
    });

    test('fresh Home mount uses the live episode start rather than the older capture start', () {
      final capture = DateTime.utc(2026, 10, 27, 8, 11, 57);
      final shifted = _episode(DateTime.utc(2026, 10, 27, 8, 20, 2));
      final now = capture.add(const Duration(minutes: 8, seconds: 24));
      for (final anchor in [LiveStartAnchor(), LiveStartAnchor()]) {
        final start = anchor.resolve(episode: shifted, captureStart: capture, streaming: true, now: now);
        expect(start, shifted.startedAt);
        expect(now.difference(start!), const Duration(seconds: 19));
      }
    });

    test('capture start does not replace the live episode start', () {
      final anchor = LiveStartAnchor();
      final older = _episode(_t0.subtract(const Duration(minutes: 3)));
      expect(anchor.resolve(episode: older, captureStart: null, streaming: true, now: _t0), older.startedAt);
      expect(anchor.resolve(episode: older, captureStart: _t0, streaming: true, now: _t0), older.startedAt);
    });

    test('an episode rotation starts elapsed time from the new live episode', () {
      // The capture can continue across the server's hard-cap rotation. The live row
      // follows the new episode so it never reports the previous episode's duration.
      final anchor = LiveStartAnchor();
      final sessionStart = _t0;
      final later = _t0.add(const Duration(minutes: 8, seconds: 24));
      expect(anchor.resolve(episode: _episode(sessionStart), captureStart: sessionStart, streaming: true, now: later),
          sessionStart);
      final rotated = _episode(later, id: 'ep2');
      expect(anchor.resolve(episode: rotated, captureStart: sessionStart, streaming: true, now: later), later);
      expect(
          anchor.resolve(
              episode: rotated,
              captureStart: sessionStart,
              streaming: true,
              now: later.add(const Duration(minutes: 2))),
          later);
    });

    test('polling during a hard-cap rotation gap never rewinds before adopting the successor', () {
      final anchor = LiveStartAnchor();
      final oldStart = _t0.add(const Duration(minutes: 8));
      final oldEpisode = _episode(oldStart);
      final now = oldStart.add(const Duration(minutes: 12));
      expect(anchor.resolve(episode: oldEpisode, captureStart: _t0, streaming: true, now: now), oldStart);

      // The old row has closed and the service has not written the successor yet.
      expect(anchor.resolve(episode: null, captureStart: _t0, streaming: true, now: now), oldStart);
      expect(
        anchor.resolve(
          episode: null,
          captureStart: _t0,
          streaming: true,
          now: now.add(const Duration(seconds: 20)),
        ),
        oldStart,
      );

      final capStart = _t0.add(const Duration(hours: 4));
      expect(
        anchor.resolve(
          episode: _episode(capStart, id: 'ep2'),
          captureStart: _t0,
          streaming: true,
          now: capStart,
        ),
        capStart,
      );
    });

    test('an idle close during a lapsed lease keeps the old start instead of 0s', () {
      final anchor = LiveStartAnchor();
      final now = _t0.add(const Duration(minutes: 40));
      anchor.resolve(episode: _episode(_t0), captureStart: null, streaming: true, now: now);
      expect(anchor.resolve(episode: null, captureStart: null, streaming: true, now: now), _t0);
    });

    test('a future server start keeps elapsed time at zero until its start', () {
      final anchor = LiveStartAnchor();
      final ahead = _episode(_t0.add(const Duration(seconds: 20)));
      expect(anchor.resolve(episode: ahead, captureStart: _t0, streaming: true, now: _t0), ahead.startedAt);
      // The episode's start remains authoritative as the local clock reaches it.
      final later = _t0.add(const Duration(seconds: 30));
      expect(anchor.resolve(episode: ahead, captureStart: _t0, streaming: true, now: later), ahead.startedAt);
    });

    test('nothing streaming means no running start', () {
      final anchor = LiveStartAnchor();
      anchor.resolve(episode: null, captureStart: _t0, streaming: true, now: _t0);
      expect(anchor.resolve(episode: null, captureStart: null, streaming: false, now: _t0), isNull);
    });

    test('a pendant wear start does not count time a closed episode already owns', () {
      final anchor = LiveStartAnchor();
      final wearStart = DateTime.utc(2026, 11, 9, 3, 7);
      final closedEnd = DateTime.utc(2026, 11, 9, 6, 27);
      final before = DateTime.utc(2026, 11, 9, 6, 0);
      // Before the closed episode is known, the wear session's start is the fallback.
      expect(anchor.resolve(episode: null, captureStart: wearStart, streaming: true, now: before), wearStart);
      // The episode closed at 06:27 and the live stretch continues from its end, not from 03:07.
      final now = DateTime.utc(2026, 11, 9, 7, 30);
      expect(
        anchor.resolve(episode: null, captureStart: wearStart, streaming: true, now: now, closedFloor: closedEnd),
        closedEnd,
      );
      // The wear session keeps reporting its earlier start on later polls; the floor still holds.
      final later = now.add(const Duration(minutes: 2));
      expect(
        anchor.resolve(episode: null, captureStart: wearStart, streaming: true, now: later, closedFloor: closedEnd),
        closedEnd,
      );
      expect(later.difference(closedEnd), const Duration(hours: 1, minutes: 5));
    });

    test('a closed floor earlier than the wear start changes nothing', () {
      final anchor = LiveStartAnchor();
      final wearStart = DateTime.utc(2026, 11, 9, 3, 7);
      final earlierClose = DateTime.utc(2026, 11, 9, 2, 0);
      final now = DateTime.utc(2026, 11, 9, 4, 0);
      expect(
        anchor.resolve(episode: null, captureStart: wearStart, streaming: true, now: now, closedFloor: earlierClose),
        wearStart,
      );
    });

    test('a closed episode that ends after now is not yet a floor', () {
      final anchor = LiveStartAnchor();
      final wearStart = DateTime.utc(2026, 11, 9, 3, 7);
      final now = DateTime.utc(2026, 11, 9, 6, 0);
      final futureClose = DateTime.utc(2026, 11, 9, 6, 27);
      expect(
        anchor.resolve(episode: null, captureStart: wearStart, streaming: true, now: now, closedFloor: futureClose),
        wearStart,
      );
    });

    test('an episode that holds the anchor still wins over a closed floor', () {
      final anchor = LiveStartAnchor();
      final started = DateTime.utc(2026, 11, 9, 6, 40);
      final now = DateTime.utc(2026, 11, 9, 7, 0);
      expect(
        anchor.resolve(
          episode: _episode(started),
          captureStart: null,
          streaming: true,
          now: now,
          closedFloor: DateTime.utc(2026, 11, 9, 6, 27),
        ),
        started,
      );
    });
  });

  group('closed Home episode floor', () {
    test('is the newest closed episode end by now; open and future episodes do not count', () {
      final provider = EpisodeProvider();
      final now = DateTime.utc(2026, 11, 9, 7, 30);
      final older = Episode(
        id: 'older',
        live: false,
        startedAt: DateTime.utc(2026, 11, 9, 2, 26),
        lastActivityAt: DateTime.utc(2026, 11, 9, 4, 0),
        closedAt: DateTime.utc(2026, 11, 9, 4, 0),
        title: '',
        conversationIds: const ['c1'],
      );
      final newest = Episode(
        id: 'newest',
        live: false,
        startedAt: DateTime.utc(2026, 11, 9, 2, 26),
        lastActivityAt: DateTime.utc(2026, 11, 9, 6, 26),
        closedAt: DateTime.utc(2026, 11, 9, 6, 27),
        title: '',
        conversationIds: const ['c2'],
      );
      final future = Episode(
        id: 'future',
        live: false,
        startedAt: DateTime.utc(2026, 11, 9, 7, 0),
        lastActivityAt: DateTime.utc(2026, 11, 9, 8, 0),
        closedAt: DateTime.utc(2026, 11, 9, 8, 0),
        title: '',
        conversationIds: const ['c3'],
      );
      final open = _episode(DateTime.utc(2026, 11, 9, 6, 40), id: 'open');
      provider.debugSetLive(null);
      provider.debugSetHomeEpisodes([older, newest, future, open]);
      expect(provider.closedEpisodeFloor(now), DateTime.utc(2026, 11, 9, 6, 27));
      expect(provider.closedEpisodeFloor(DateTime.utc(2026, 11, 9, 1, 0)), isNull);
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

  test('quiet wear relaxes the quick re-reads after the pending window', () {
    fakeAsync((async) {
      var reads = 0;
      final provider = EpisodeProvider(
        clock: () => _t0.add(async.elapsed),
        fetchLive: () async {
          reads++;
          return const ApiSuccess(EpisodeRead(enabled: true));
        },
      );
      provider.watch();
      async.elapse(EpisodeProvider.pendingPollWindow + EpisodeProvider.pendingPollInterval);
      final quick = reads;
      async.elapse(EpisodeProvider.pollInterval * 2);
      // Only the normal cadence now: two reads in a minute, not six.
      expect(reads - quick, inInclusiveRange(1, 3));
      provider.unwatch();
      provider.dispose();
    });
  });

  test('a read landing after dispose arms nothing', () async {
    final release = Completer<void>();
    final provider = EpisodeProvider(fetchLive: () async {
      await release.future;
      return const ApiSuccess(EpisodeRead(enabled: true));
    });
    provider.watch();
    provider.dispose();
    release.complete();
    await Future<void>.delayed(Duration.zero);
    expect(provider.live, isNull);
  });

  group('ending the live conversation', () {
    test('the count restarts at 0 and the next episode never jumps it back', () {
      final anchor = LiveStartAnchor();
      final end = _t0.add(const Duration(minutes: 40));
      expect(anchor.resolve(episode: _episode(_t0), captureStart: _t0, streaming: true, now: end), _t0);
      anchor.restart(end);
      expect(anchor.resolve(episode: null, captureStart: _t0, streaming: true, now: end), end);
      // Not streaming for a moment (the pendant between health updates) still counts from the restart.
      final quiet = end.add(const Duration(seconds: 20));
      expect(anchor.resolve(episode: null, captureStart: null, streaming: false, now: quiet), end);
      // The next episode opens at its first words a minute later; the count keeps the restart.
      final firstWords = end.add(const Duration(minutes: 1));
      final next = _episode(firstWords, id: 'ep2');
      expect(anchor.resolve(episode: next, captureStart: _t0, streaming: true, now: firstWords), end);
      expect(anchor.resolve(episode: next, captureStart: _t0, streaming: true, now: firstWords), end);
    });

    test('the live episode closes at once and is never adopted again', () async {
      final calls = <(String, String?)>[];
      final live = _episode(_t0);
      final provider = EpisodeProvider(
        clock: () => _t0.add(const Duration(minutes: 40)),
        fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: live)),
        wrapUp: (id, {conversationId}) async {
          calls.add((id, conversationId));
          return ApiSuccess(live);
        },
      );
      provider.debugSetLive(live);
      provider.onLiveFinalized();
      expect(provider.live, isNull);
      expect(calls, [('ep1', null)]);
      // The server can still report it live for a few minutes; it must not come back.
      await provider.refreshLive();
      expect(provider.live, isNull);
      // A later episode is adopted normally.
      final next = _episode(_t0.add(const Duration(minutes: 41)), id: 'ep2');
      final second = EpisodeProvider(fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: next)));
      await second.refreshLive();
      expect(second.live?.id, 'ep2');
      // Ending with nothing live still restarts the clock and makes no call.
      provider.onLiveFinalized();
      expect(calls, hasLength(1));
    });
  });
}
