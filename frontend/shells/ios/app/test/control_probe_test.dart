import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi_webview_proto/control_probe.dart';

final class WebKitNullSentinel {
  @override
  String toString() => '<null>';
}

void main() {
  test('iOS probe result unwraps WKWebView JSON strings and null sentinels', () {
    // red-proof: treat the WKWebView "<null>" sentinel or a quoted pending
    // value as a finished payload; parseProbeJsLine would then miss the run.
    expect(normalizeProbeJsResult(null), isNull);
    expect(normalizeProbeJsResult(WebKitNullSentinel()), isNull);
    expect(normalizeProbeJsResult('<null>'), isNull);
    expect(normalizeProbeJsResult('null'), isNull);
    expect(normalizeProbeJsResult('"$controlProbePendingValue"'), controlProbePendingValue);
    expect(normalizeProbeJsResult(controlProbePendingValue), controlProbePendingValue);
    const payload = '{"schema":"omi.control-acceptance.v1","steps":[]}';
    expect(normalizeProbeJsResult(payload), payload);
    expect(normalizeProbeJsResult(jsonEncode(payload)), payload);
    expect(
      normalizeProbeJsResult({'schema': 'omi.control-acceptance.v1', 'steps': []}),
      payload,
    );
  });

  test('the iOS probe line is the macOS PROBE_JS envelope, including pending', () {
    // red-proof: emit a different prefix or drop the pending token so
    // verdict.parseProbeJsLine cannot read this host.
    expect(
      formatProbeJsLine(value: '{"schema":"omi.control-acceptance.v1","steps":[]}'),
      'PROBE_JS: {"schema":"omi.control-acceptance.v1","steps":[]} error: none',
    );
    expect(formatProbeJsLine(value: controlProbePendingValue), 'PROBE_JS: $controlProbePendingValue error: none');
    expect(formatProbeJsLine(), 'PROBE_JS: nil error: none');
    expect(formatProbeJsLine(error: 'TypeError:\nboom'), 'PROBE_JS: nil error: TypeError: boom');
  });

  test('probe driver writes the first non-pending evaluation and not a prior file', () async {
    // red-proof: keep the prior result, or finish on OMI_CONTROL_PENDING.
    final scratch = await Directory.systemTemp.createTemp('omi-ios-control-probe-');
    addTearDown(() => scratch.delete(recursive: true));
    final result = File('${scratch.path}/$controlProbeResultFilename');
    await result.writeAsString('PROBE_JS: prior error: none\n');
    var attempts = 0;
    const finished = '{"schema":"omi.control-acceptance.v1","steps":[{"slug":"home","verdict":"ready"}]}';
    final sleeps = <Duration>[];
    final driver = ControlProbeDriver(
      driverSource: '(() => window.__omiCA)()',
      resultPath: result.path,
      maxAttempts: 5,
      retryInterval: const Duration(milliseconds: 1),
      initialDelay: const Duration(milliseconds: 2),
      sleep: (duration) async {
        sleeps.add(duration);
      },
      evaluate: (source) async {
        if (source.contains('return "reset"')) return 'reset';
        if (source.contains('if (!html) return "OMI_CONTROL_PENDING"')) return 'home';
        expect(source.contains('omi-ca-driver'), isTrue);
        expect(source, contains('(() => window.__omiCA)()'));
        attempts += 1;
        if (attempts < 3) return controlProbePendingValue;
        return finished;
      },
    );
    await driver.start();
    expect(attempts, 3);
    expect(sleeps.first, const Duration(milliseconds: 2));
    expect(await result.readAsString(), 'PROBE_JS: $finished error: none\n');
  });

  test('probe driver records pending as the macOS timeout line, never a pass token', () async {
    final scratch = await Directory.systemTemp.createTemp('omi-ios-control-probe-timeout-');
    addTearDown(() => scratch.delete(recursive: true));
    final result = File('${scratch.path}/$controlProbeResultFilename');
    final driver = ControlProbeDriver(
      driverSource: '(() => "OMI_CONTROL_PENDING")()',
      resultPath: result.path,
      maxAttempts: 2,
      retryInterval: Duration.zero,
      initialDelay: Duration.zero,
      sleep: (_) async {},
      evaluate: (_) async => controlProbePendingValue,
    );
    await driver.start();
    expect(await result.readAsString(), 'PROBE_JS: $controlProbePendingValue error: none\n');
  });

  test('probe basename is a closed Documents name, never a host path', () {
    // red-proof: admit ../ or an absolute path so the simulator writes outside Documents.
    expect(isSafeProbeBasename(controlProbeDriverFilename), isTrue);
    expect(isSafeProbeBasename(controlProbeResultFilename), isTrue);
    expect(isSafeProbeBasename('../omi-control-probe.js'), isFalse);
    expect(isSafeProbeBasename('/tmp/omi-control-probe.js'), isFalse);
    expect(isSafeProbeBasename('omi-control-probe.exe'), isFalse);
  });

  test('iOS rebinds sessionStorage rather than forking the shared driver', () {
    // red-proof: drop the prelude so custom-scheme evaluateJavaScript returns
    // PENDING 100 times and parseProbeJsLine reports probe-timeout.
    expect(controlProbeStoragePrelude, contains('sessionStorage'));
    expect(controlProbeStoragePrelude, contains('localStorage'));
    expect(controlProbeStoragePrelude, contains('window.name'));
    expect(controlProbeStoragePrelude, contains(controlProbeStorageKey));
    expect(controlProbeStorageResetSource, contains(controlProbeStorageKey));
    final sent = controlProbeInstallSource('(function () {\nreturn 1;\n})()');
    expect(sent, contains(controlProbeScriptId));
    expect(sent, contains(controlProbeResultAttr));
    expect(controlProbePageBundle('(function () { return 1; })()'), contains('setInterval'));
    expect(controlProbePageBundle('(function () { return 1; })()'), contains('data-omi-ca-steps'));
    expect(controlProbePageBundle('(function () { return 1; })()'), contains('__omiCAHostPoll === document'));
    expect(controlProbeDeferredInstallSource('(() => 1)()'), contains('__omiCAInstallWatch === document'));
    expect(controlProbeDeferredShellWatchSource(), contains('__omiCAShellWatch === document'));
    expect(controlProbeInstallSource('(function () {\nreturn 1;\n})()'), contains("data-production-shell='true'"));
    expect(controlProbeDiagnosticSource, contains('data-omi-ca-steps'));
    expect(controlProbeShellProbeSource, contains('getElementById("root")'));
    expect(controlProbeShellProbeSource, contains("data-production-shell='true'"));
    expect(controlProbeShellProbeSource.contains(controlProbeScriptId), isFalse);
    expect(controlProbeShellProbeSource.contains('appendChild'), isFalse);
    expect(isControlProbeShellReady(null), isFalse);
    expect(isControlProbeShellReady(controlProbePendingValue), isFalse);
    expect(isControlProbeShellReady('home'), isTrue);
    expect(isControlProbeShellReady('<script id="omi-ca-shell-watch"></script>'), isFalse);
  });

  test('probe waits for the production shell before injecting the shared driver', () async {
    // red-proof: inject driver.js while #root is still empty so the IIFE
    // starves React and the run times out with shell:false.
    final scratch = await Directory.systemTemp.createTemp('omi-ios-control-probe-shell-');
    addTearDown(() => scratch.delete(recursive: true));
    final result = File('${scratch.path}/$controlProbeResultFilename');
    var shellPolls = 0;
    var installPolls = 0;
    var sawReset = false;
    const finished = '{"schema":"omi.control-acceptance.v1","steps":[{"slug":"home","verdict":"ready"}]}';
    final driver = ControlProbeDriver(
      driverSource: '(() => window.__omiCA)()',
      resultPath: result.path,
      maxAttempts: 3,
      retryInterval: Duration.zero,
      initialDelay: Duration.zero,
      sleep: (_) async {},
      evaluate: (source) async {
        if (source.contains('return "reset"')) {
          expect(installPolls, 0, reason: 'storage reset must precede driver inject');
          expect(shellPolls, greaterThan(0), reason: 'reset must wait for the shell');
          sawReset = true;
          return 'reset';
        }
        if (source.contains('if (!html) return "OMI_CONTROL_PENDING"')) {
          expect(installPolls, 0);
          shellPolls += 1;
          if (shellPolls == 1) return '<script id="omi-ca-shell-watch"></script>';
          if (shellPolls < 3) return controlProbePendingValue;
          return 'home';
        }
        expect(source.contains('omi-ca-driver'), isTrue);
        expect(sawReset, isTrue);
        installPolls += 1;
        if (installPolls < 3) return controlProbePendingValue;
        return finished;
      },
    );
    await driver.start();
    expect(shellPolls, 3);
    expect(installPolls, 3);
    expect(await result.readAsString(), 'PROBE_JS: $finished error: none\n');
  });

  test('javascript channel writes the finished payload without polling evaluate', () async {
    // red-proof: keep runJavaScriptReturningResult in a loop so a click
    // navigation blocks the Dart isolate and the launcher exits 124.
    final scratch = await Directory.systemTemp.createTemp('omi-ios-control-probe-channel-');
    addTearDown(() => scratch.delete(recursive: true));
    final result = File('${scratch.path}/$controlProbeResultFilename');
    final sources = <String>[];
    const finished = '{"schema":"omi.control-acceptance.v1","steps":[{"slug":"home","verdict":"ready"}]}';
    final driver = ControlProbeDriver(
      driverSource: '(() => window.__omiCA)()',
      resultPath: result.path,
      useJavaScriptChannel: true,
      initialDelay: Duration.zero,
      shellWait: const Duration(seconds: 1),
      resultWait: const Duration(seconds: 1),
      sleep: (_) async {},
      evaluate: (source) async {
        sources.add(source);
        return controlProbePendingValue;
      },
    );
    await driver.acceptChannel('shell:home');
    await driver.acceptChannel(finished);
    await driver.start();
    expect(sources.any((source) => source.contains('setTimeout')), isTrue);
    expect(controlProbeDeferredInstallSource('(() => 1)()'), contains(controlProbeChannelName));
    expect(controlProbeDeferredInstallSource('(() => 1)()'), contains("data-production-shell='true'"));
    expect(await result.readAsString(), 'PROBE_JS: $finished error: none\n');
  });

  test('resumeAfterNavigation re-injects while the result wait is open', () async {
    // red-proof: keep __omiCAInstallWatch as a boolean so an <a href> to
    // memories never re-injects (2026-08-16: mountLen:0, script:false).
    final scratch = await Directory.systemTemp.createTemp('omi-ios-control-probe-resume-');
    addTearDown(() => scratch.delete(recursive: true));
    final result = File('${scratch.path}/$controlProbeResultFilename');
    var installCount = 0;
    const finished = '{"schema":"omi.control-acceptance.v1","steps":[{"slug":"home","verdict":"ready"}]}';
    final driver = ControlProbeDriver(
      driverSource: '(() => 1)()',
      resultPath: result.path,
      useJavaScriptChannel: true,
      initialDelay: Duration.zero,
      resultWait: const Duration(seconds: 2),
      sleep: (_) async {},
      evaluate: (source) async {
        if (source.contains('__omiCAInstallWatch === document')) installCount += 1;
        return controlProbePendingValue;
      },
    );
    await driver.acceptChannel('shell:home');
    final started = driver.start();
    await Future<void>.delayed(Duration.zero);
    await driver.resumeAfterNavigation();
    await driver.acceptChannel(finished);
    await started;
    expect(installCount, greaterThanOrEqualTo(2));
    expect(await result.readAsString(), 'PROBE_JS: $finished error: none\n');
  });

  test('probe writes on evaluate timeout rather than hanging the launcher', () async {
    // red-proof: a hung runJavaScriptReturningResult leaves no PROBE_JS file
    // and the launcher exits 124 (measured 2026-08-16, probe-missing).
    final scratch = await Directory.systemTemp.createTemp('omi-ios-control-probe-hang-');
    addTearDown(() => scratch.delete(recursive: true));
    final result = File('${scratch.path}/$controlProbeResultFilename');
    final driver = ControlProbeDriver(
      driverSource: '(() => 1)()',
      resultPath: result.path,
      maxAttempts: 3,
      retryInterval: Duration.zero,
      initialDelay: Duration.zero,
      evaluateTimeout: const Duration(milliseconds: 20),
      sleep: (_) async {},
      evaluate: (_) => Completer<Object?>().future,
    );
    await driver.start();
    expect(await result.readAsString(), 'PROBE_JS: nil error: probe-evaluate-timeout\n');
  });

  test('probe timeout publishes recorded steps so CONTROL lines are not missing-step', () async {
    // red-proof: keep only the PENDING timeout line. A 2026-08-16 iOS run had
    // mic=transcript-rendered and screen=bridge-unreachable in window.name
    // while every CONTROL slug printed missing-step.
    final scratch = await Directory.systemTemp.createTemp('omi-ios-control-probe-steps-');
    addTearDown(() => scratch.delete(recursive: true));
    final result = File('${scratch.path}/$controlProbeResultFilename');
    const steps = [
      {'slug': 'home', 'verdict': 'ready'},
      {'slug': 'mic', 'verdict': 'transcript-rendered'},
      {'slug': 'screen', 'verdict': 'bridge-unreachable'},
    ];
    final driver = ControlProbeDriver(
      driverSource: '(() => 1)()',
      resultPath: result.path,
      maxAttempts: 2,
      retryInterval: Duration.zero,
      initialDelay: Duration.zero,
      sleep: (_) async {},
      evaluate: (source) async {
        if (source.contains('return "reset"')) return 'reset';
        if (source.contains('if (!html) return "OMI_CONTROL_PENDING"') && source.contains('omi-ca-driver') == false) {
          return 'home';
        }
        if (source.contains('hasRoot: !!root')) {
          return jsonEncode({
            'href': 'omi-ui://local/index.html?route=memories',
            'phase': 'nav-wait',
            'steps': steps,
            'shell': false,
          });
        }
        return controlProbePendingValue;
      },
    );
    await driver.start();
    final text = await result.readAsString();
    expect(text, contains('probe-timeout:'));
    expect(text, contains('"slug":"mic"'));
    final last = text.trim().split('\n').last;
    expect(last, startsWith('PROBE_JS: {"schema":"omi.control-acceptance.v1"'));
    expect(last, contains('"verdict":"transcript-rendered"'));
    expect(last, endsWith('error: none'));
  });

  test('probe driver rejects an empty program and tears down a failed write', () async {
    expect(
      () => ControlProbeDriver(
        driverSource: '  ',
        resultPath: '/tmp/x',
        evaluate: (_) async => null,
      ),
      throwsFormatException,
    );
    final scratch = await Directory.systemTemp.createTemp('omi-ios-control-probe-teardown-');
    addTearDown(() => scratch.delete(recursive: true));
    final result = File('${scratch.path}/$controlProbeResultFilename');
    await result.writeAsString('stale\n');
    final driver = ControlProbeDriver(
      driverSource: '(() => 1)()',
      resultPath: result.path,
      evaluate: (_) async => throw StateError('not started'),
    );
    await driver.teardown();
    expect(await result.exists(), isFalse);
  });
}
