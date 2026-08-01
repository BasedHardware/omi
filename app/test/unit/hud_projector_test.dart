import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices/display/glasses_display.dart';
import 'package:omi/services/devices/display/hud_content.dart';
import 'package:omi/services/devices/display/hud_projector.dart';

void main() {
  final now = DateTime(2026, 8, 1, 9);
  const projector = HudProjector();

  group('HudProjector.tasks', () {
    test('drops completed tasks and says so when nothing is pending', () {
      final screen = projector.tasks([
        const HudTask(description: 'Ship the PR', completed: true),
      ], now: now);

      expect(screen.kind, HudScreenKind.tasks);
      expect(screen.lines.single.text, 'Nothing due');
      expect(screen.lines.single.muted, isTrue);
    });

    test('orders by due date, then priority, before falling back to text', () {
      final screen = projector.tasks([
        const HudTask(description: 'No due, low', priority: 'low'),
        HudTask(description: 'Due later', dueAt: now.add(const Duration(days: 2))),
        const HudTask(description: 'No due, high', priority: 'high'),
        HudTask(description: 'Due soon', dueAt: now.add(const Duration(hours: 1))),
      ], now: now);

      expect(
        screen.lines.map((l) => l.text).toList(),
        ['Due soon', 'Due later', 'No due, high', 'No due, low'],
      );
    });

    test('never exceeds the line budget and reports what it hid', () {
      final screen = projector.tasks([
        for (var i = 0; i < 12; i++) HudTask(description: 'Task $i', priority: 'high'),
      ], now: now);

      expect(screen.lines.length, 5);
      expect(screen.lines.last.text, '+8 more');
      expect(screen.lines.last.muted, isTrue);
    });

    test('fills the budget exactly when the count fits, with no overflow line', () {
      final screen = projector.tasks([
        for (var i = 0; i < 5; i++) HudTask(description: 'Task $i'),
      ], now: now);

      expect(screen.lines.length, 5);
      expect(screen.lines.every((l) => l.text.startsWith('Task')), isTrue);
    });

    test('collapses whitespace and truncates an over-long description', () {
      final screen = projector.tasks([
        HudTask(description: 'a  b\n\tc ${'x' * 80}'),
      ], now: now);

      final text = screen.lines.single.text;
      expect(text.length, lessThanOrEqualTo(48));
      expect(text, startsWith('a b c'));
      expect(text, endsWith('…'));
    });
  });

  group('HudProjector.answer', () {
    test('wraps on word boundaries within the remaining budget', () {
      final screen = projector.answer('What is left?', List.filled(40, 'word').join(' '));

      expect(screen.lines.length, lessThanOrEqualTo(5));
      expect(screen.lines.first.text, 'What is left?');
      expect(screen.lines.skip(1).every((l) => l.text.length <= 48), isTrue);
      expect(screen.lines.last.text, endsWith('…'));
    });

    test('keeps a short answer on one line', () {
      final screen = projector.answer('Ping?', 'Pong');
      expect(screen.lines.map((l) => l.text).toList(), ['Ping?', 'Pong']);
    });
  });

  group('HudProjector.capture', () {
    test('marks the paused state muted and offers resume', () {
      final screen = projector.capture(recording: false);
      expect(screen.lines.single.text, 'Paused');
      expect(screen.lines.single.muted, isTrue);
      expect(screen.actions.single.label, 'Resume');
    });

    test('omits a blank transcript line rather than rendering an empty row', () {
      final screen = projector.capture(recording: true, lastLine: '   ');
      expect(screen.lines.length, 1);
      expect(screen.lines.single.text, 'Listening');
    });
  });

  group('GlassesDisplayGate', () {
    test('a display-less device stays closed even when the user opts in', () {
      const gate = GlassesDisplayGate(deviceSupportsDisplay: false, userEnabled: true);
      expect(gate.isOpen, isFalse);
      expect(gate.closedReason, 'device_has_no_display');
    });

    test('a display device stays closed until the user opts in', () {
      const gate = GlassesDisplayGate(deviceSupportsDisplay: true, userEnabled: false);
      expect(gate.isOpen, isFalse);
      expect(gate.closedReason, 'user_disabled');
    });

    test('opens only when both conditions hold', () {
      const gate = GlassesDisplayGate(deviceSupportsDisplay: true, userEnabled: true);
      expect(gate.isOpen, isTrue);
      expect(gate.closedReason, isEmpty);
    });
  });
}
