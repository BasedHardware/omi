import 'package:flutter_test/flutter_test.dart';
import 'package:omi/startup/startup_error_router.dart';

class _Report {
  _Report(this.error, this.stack, {required this.fatal, required this.origin});

  final Object error;
  final StackTrace stack;
  final bool fatal;
  final String origin;
}

void main() {
  late List<_Report> reports;
  late StartupErrorRouter router;

  setUp(() {
    reports = [];
    router = StartupErrorRouter(
      report: (error, stack, {required fatal, required origin}) {
        reports.add(_Report(error, stack, fatal: fatal, origin: origin));
      },
    );
  });

  test('zone error before startup completes is fatal boot', () {
    final error = StateError('boot failure');
    final stack = StackTrace.current;
    router.handleZoneError(error, stack);
    expect(reports, hasLength(1));
    expect(reports.single.fatal, isTrue);
    expect(reports.single.origin, 'boot');
  });

  test('platform error before startup completes is fatal boot and returns true', () {
    final error = StateError('boot failure');
    final stack = StackTrace.current;
    expect(router.handlePlatformError(error, stack), isTrue);
    expect(reports, hasLength(1));
    expect(reports.single.fatal, isTrue);
    expect(reports.single.origin, 'boot');
  });

  test('errors after startup completes are non-fatal uncaught_async', () {
    router.beginStartup();
    router.completeStartup();
    router.handleZoneError(StateError('zone'), StackTrace.current);
    expect(router.handlePlatformError(StateError('platform'), StackTrace.current), isTrue);
    expect(reports, hasLength(2));
    for (final report in reports) {
      expect(report.fatal, isFalse);
      expect(report.origin, 'uncaught_async');
    }
  });

  test('beginStartup resets severity so a retry reports fatal boot again', () {
    router.beginStartup();
    router.completeStartup();
    router.handleZoneError(StateError('post'), StackTrace.current);
    router.beginStartup();
    router.handleZoneError(StateError('retry'), StackTrace.current);
    expect(reports[0].fatal, isFalse);
    expect(reports[0].origin, 'uncaught_async');
    expect(reports[1].fatal, isTrue);
    expect(reports[1].origin, 'boot');
  });

  test('every invocation forwards the exact error and stack', () {
    final firstError = StateError('first');
    final firstStack = StackTrace.current;
    final secondError = ArgumentError('second');
    final secondStack = StackTrace.current;
    router.handleZoneError(firstError, firstStack);
    router.handlePlatformError(secondError, secondStack);
    expect(reports, hasLength(2));
    expect(reports[0].error, same(firstError));
    expect(reports[0].stack, same(firstStack));
    expect(reports[1].error, same(secondError));
    expect(reports[1].stack, same(secondStack));
  });

  test('severity is captured when the handler is invoked', () {
    router.handleZoneError(StateError('early'), StackTrace.current);
    router.completeStartup();
    router.handleZoneError(StateError('late'), StackTrace.current);
    expect(reports[0].fatal, isTrue);
    expect(reports[0].origin, 'boot');
    expect(reports[1].fatal, isFalse);
    expect(reports[1].origin, 'uncaught_async');
  });
}
