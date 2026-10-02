import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversations/capture_gaps_controller.dart';

final _day = DateTime(2026, 9, 20);

CalendarCaptureGap _gap(String eventId) => CalendarCaptureGap(
      eventId: eventId,
      title: 'Board review',
      startTime: DateTime(2026, 9, 20, 19, 30),
      endTime: DateTime(2026, 9, 20, 20),
    );

class _FakeGapsApi {
  _FakeGapsApi(this.responses);

  final List<({List<CalendarCaptureGap> items, bool ok})> responses;
  int calls = 0;

  Future<({List<CalendarCaptureGap> items, bool ok})> fetch({required DateTime start, required DateTime end}) async {
    final response = responses[calls.clamp(0, responses.length - 1)];
    calls++;
    return response;
  }
}

void main() {
  test('a failed read keeps the rows on screen and retries on the next refresh', () async {
    final api = _FakeGapsApi([
      (items: [_gap('evt-1')], ok: true),
      (items: const <CalendarCaptureGap>[], ok: false),
      (items: [_gap('evt-1')], ok: true),
    ]);
    final controller = CaptureGapsController(fetchGaps: api.fetch);

    await controller.refresh([_day]);
    expect(controller.gapsByDate[_day], hasLength(1));

    controller.invalidate();
    final changedOnFailure = await controller.refresh([_day]);

    expect(changedOnFailure, isFalse);
    expect(controller.gapsByDate[_day], hasLength(1));

    // The span was released, so the same span is read again instead of waiting
    // for the loaded range to change.
    expect(await controller.refresh([_day]), isTrue);
    expect(api.calls, 3);
  });

  test('an answered read with no gaps clears the rows', () async {
    final api = _FakeGapsApi([
      (items: [_gap('evt-1')], ok: true),
      (items: const <CalendarCaptureGap>[], ok: true),
    ]);
    final controller = CaptureGapsController(fetchGaps: api.fetch);

    await controller.refresh([_day]);
    controller.invalidate();
    await controller.refresh([_day]);

    expect(controller.gapsByDate, isEmpty);
  });

  test('the same span is not read twice', () async {
    final api = _FakeGapsApi([
      (items: [_gap('evt-1')], ok: true),
    ]);
    final controller = CaptureGapsController(fetchGaps: api.fetch);

    await controller.refresh([_day]);
    expect(await controller.refresh([_day]), isFalse);
    expect(api.calls, 1);
  });

  test('no loaded days clears the rows and the span', () async {
    final api = _FakeGapsApi([
      (items: [_gap('evt-1')], ok: true),
      (items: [_gap('evt-2')], ok: true),
    ]);
    final controller = CaptureGapsController(fetchGaps: api.fetch);

    await controller.refresh([_day]);
    expect(await controller.refresh(const <DateTime>[]), isTrue);
    expect(controller.gapsByDate, isEmpty);

    expect(await controller.refresh([_day]), isTrue);
    expect(controller.gapsByDate[_day], hasLength(1));
  });
}
