import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// Host-side poll of the shared control-acceptance driver.
///
/// The macOS shell evaluates `OMI_PROBE_JS` in WKWebView. iOS cannot take that
/// env var into the simulator process, so the launcher drops the same driver
/// source into Documents and this host evaluates it until it returns a
/// non-pending value. The line written here is the macOS `PROBE_JS:` shape
/// `verdict.mjs` already parses — do not invent a second envelope.
///
/// Flutter's `runJavaScriptReturningResult` does not share a durable JS
/// environment with the page on `omi-ui://local`. A 2026-08-16 run printed
/// `CONTROL harness=probe-timeout` with every slug `missing-step` after 100
/// successful PENDING returns: the shared driver uses `sessionStorage` so a
/// real `<a href>` navigation does not reset, and that storage never
/// accumulated across host evaluations. This host injects the unchanged
/// `driver.js` through a page-world `<script>` (DOM is shared even when the
/// evaluate world is not) and reads the result from a document attribute. It
/// does not fork the driver or the verdict vocabulary.
///
/// A later 2026-08-16 run still printed `probe-timeout` with
/// `main[data-production-shell='true']` missing after the page-world inject:
/// evaluating the full driver IIFE every 400ms on the WKWebView JS thread
/// starved React before the shell marker appeared. The host now polls with a
/// tiny shell probe and only then injects `driver.js`.
const controlProbePendingValue = 'OMI_CONTROL_PENDING';
const controlProbeDriverFilename = 'omi-control-probe.js';
const controlProbeResultFilename = 'omi-control-probe-result.txt';
const controlProbeStorageKey = 'omi.control-acceptance.v1';
const controlProbeScriptId = 'omi-ca-driver';
const controlProbeResultAttr = 'data-omi-ca-result';
const controlProbeChannelName = 'OmiControlProbe';

const controlProbeStoragePrelude = r'''
(function () {
  if (window.__omiCASessionPatched) return;
  window.__omiCASessionPatched = true;
  var KEY = "omi.control-acceptance.v1";
  var PREFIX = "omiCA:";
  var mem = Object.create(null);
  try {
    var raw = localStorage.getItem(KEY);
    if (typeof raw === "string") mem[KEY] = raw;
  } catch (e) {}
  if (!mem[KEY] && typeof window.name === "string" && window.name.indexOf(PREFIX) === 0) {
    mem[KEY] = window.name.slice(PREFIX.length);
  }
  var fake = {
    getItem: function (k) {
      return Object.prototype.hasOwnProperty.call(mem, k) ? mem[k] : null;
    },
    setItem: function (k, v) {
      mem[k] = String(v);
      if (k === KEY) {
        try { window.name = PREFIX + String(v); } catch (e0) {}
      }
      try { localStorage.setItem(k, String(v)); } catch (e) {}
    },
    removeItem: function (k) {
      delete mem[k];
      if (k === KEY) {
        try { window.name = ""; } catch (e0) {}
      }
      try { localStorage.removeItem(k); } catch (e) {}
    },
    clear: function () {
      for (var k in mem) delete mem[k];
      try { window.name = ""; } catch (e0) {}
    },
    key: function (i) { return Object.keys(mem)[i] || null; }
  };
  Object.defineProperty(fake, "length", {
    get: function () { return Object.keys(mem).length; }
  });
  try {
    Object.defineProperty(window, "sessionStorage", {
      configurable: true,
      enumerable: true,
      value: fake
    });
  } catch (e1) {
    try {
      sessionStorage.getItem = function (k) { return fake.getItem(k); };
      sessionStorage.setItem = function (k, v) { fake.setItem(k, v); };
      sessionStorage.removeItem = function (k) { fake.removeItem(k); };
    } catch (e2) {}
  }
})();
''';

String controlProbePageBundle(String driverSource) {
  final pending = controlProbePendingValue;
  final attr = controlProbeResultAttr;
  return '''
${controlProbeStoragePrelude.trim()}
(function () {
  // Key the watch to this document. A 2026-08-16 run reused window across
  // an <a href> to memories, left #root empty (mountLen:0, script:false),
  // and never re-injected because a boolean watch stayed true.
  if (window.__omiCAHostPoll === document) return;
  window.__omiCAHostPoll = document;
  window.__omiCAResult = "$pending";
  if (document.documentElement) {
    document.documentElement.setAttribute("$attr", "$pending");
  }
  var tick = function () {
    try {
      var value = ${driverSource.trim()};
      if (document.documentElement) {
        try {
          var stored = sessionStorage.getItem("$controlProbeStorageKey");
          var parsed = stored ? JSON.parse(stored) : null;
          document.documentElement.setAttribute(
            "data-omi-ca-phase",
            parsed && parsed.phase ? String(parsed.phase) : ""
          );
          document.documentElement.setAttribute(
            "data-omi-ca-steps",
            JSON.stringify(parsed && parsed.steps ? parsed.steps : [])
          );
        } catch (e0) {}
      }
      if (typeof value === "string" && value !== "$pending") {
        window.__omiCAResult = value;
        if (document.documentElement) document.documentElement.setAttribute("$attr", value);
        if (window.__omiCATimer) clearInterval(window.__omiCATimer);
        try { $controlProbeChannelName.postMessage(value); } catch (e1) {}
      }
    } catch (err) {
      if (document.documentElement) {
        document.documentElement.setAttribute("data-omi-ca-error", String(err));
      }
    }
  };
  // Do not run tick() synchronously: a 2026-08-16 run that did made
  // runJavaScriptReturningResult wait through an <a href> navigation and
  // never wrote PROBE_JS (launcher exit 124; the Dart isolate was blocked
  // so Future.timeout could not fire).
  window.__omiCATimer = setInterval(tick, 400);
})();
''';
}

String controlProbeInstallSource(String driverSource) {
  final bundle = jsonEncode(controlProbePageBundle(driverSource));
  return '''
(function () {
  var root = document.documentElement;
  if (!root) return "$controlProbePendingValue";
  if (!document.getElementById("$controlProbeScriptId")) {
    // A 2026-08-16 run that injected on a post-navigation document while
    // #root was still empty left mountLen:0 for the rest of the timeout
    // (phase=nav-wait, route=memories). Wait for the shell marker the same
    // way the first inject does.
    var mount = document.getElementById("root");
    var html = mount && typeof mount.innerHTML === "string" ? mount.innerHTML : "";
    var shell = document.querySelector("main[data-production-shell='true']");
    var route = shell ? shell.getAttribute("data-route") : "";
    if (!html || typeof route !== "string" || !route) {
      return "$controlProbePendingValue";
    }
    var script = document.createElement("script");
    script.id = "$controlProbeScriptId";
    script.textContent = $bundle;
    root.appendChild(script);
  }
  return root.getAttribute("$controlProbeResultAttr") || "$controlProbePendingValue";
})()
''';
}

const controlProbeStorageResetSource = '''
(function () {
  var root = document.documentElement;
  if (!root) return "reset";
  var script = document.createElement("script");
  script.textContent = 'try{localStorage.removeItem("$controlProbeStorageKey");sessionStorage.removeItem("$controlProbeStorageKey");window.name="";}catch(e){}';
  root.appendChild(script);
  script.remove();
  return "reset";
})()
''';

/// Read-only poll. Must not inject a script: a 2026-08-16 run that injected a
/// watcher (and then `driver.js`) left `#root` empty (`mountLen:0`) for the
/// whole timeout. The host only mutates the page after a closed route name
/// appears on `main[data-production-shell='true']`.
const controlProbeShellProbeSource = r'''
(function () {
  var mount = document.getElementById("root");
  var html = mount && typeof mount.innerHTML === "string" ? mount.innerHTML : "";
  if (!html) return "OMI_CONTROL_PENDING";
  var shell = document.querySelector("main[data-production-shell='true']");
  if (!shell) return "OMI_CONTROL_PENDING";
  var route = shell.getAttribute("data-route");
  if (typeof route !== "string" || !route) return "OMI_CONTROL_PENDING";
  return route;
})()
''';

const controlProbeDiagnosticSource = r'''
(function () {
  var root = document.documentElement;
  var mount = document.getElementById("root");
  var shell = document.querySelector("main[data-production-shell='true']");
  var html = mount && typeof mount.innerHTML === "string" ? mount.innerHTML : "";
  return JSON.stringify({
    href: String(location.href || ""),
    ready: String(document.readyState || ""),
    hasRoot: !!root,
    script: !!document.getElementById("omi-ca-driver"),
    attr: root ? root.getAttribute("data-omi-ca-result") : null,
    err: root ? root.getAttribute("data-omi-ca-error") : null,
    shell: !!(shell),
    route: shell ? (shell.getAttribute("data-route") || "") : "",
    mountLen: html.length,
    mountHead: html.slice(0, 80),
    scripts: document.scripts ? document.scripts.length : 0,
    phase: root ? (root.getAttribute("data-omi-ca-phase") || "") : "",
    steps: (function () {
      try {
        var attr = root ? root.getAttribute("data-omi-ca-steps") : null;
        if (attr) return JSON.parse(attr);
        if (typeof window.name === "string" && window.name.indexOf("omiCA:") === 0) {
          var parsed = JSON.parse(window.name.slice("omiCA:".length));
          return parsed && parsed.steps ? parsed.steps : [];
        }
      } catch (e) {}
      return [];
    })(),
    name: typeof window.name === "string" && window.name.indexOf("omiCA:") === 0
  });
})()
''';

String controlProbeEvaluateSource(String driverSource) => controlProbeInstallSource(driverSource);

String controlProbeDeferredShellWatchSource() {
  return '''
(function () {
  setTimeout(function () {
    if (window.__omiCAShellWatch === document) return;
    window.__omiCAShellWatch = document;
    var tick = function () {
      var mount = document.getElementById("root");
      var html = mount && typeof mount.innerHTML === "string" ? mount.innerHTML : "";
      if (!html) return;
      var shell = document.querySelector("main[data-production-shell='true']");
      var route = shell ? shell.getAttribute("data-route") : "";
      if (typeof route === "string" && route) {
        try { $controlProbeChannelName.postMessage("shell:" + route); } catch (e) {}
        if (window.__omiCAShellTimer) clearInterval(window.__omiCAShellTimer);
      }
    };
    window.__omiCAShellTimer = setInterval(tick, 400);
  }, 0);
  return "$controlProbePendingValue";
})()
''';
}

String controlProbeDeferredInstallSource(String driverSource) {
  final bundle = jsonEncode(controlProbePageBundle(driverSource));
  return '''
(function () {
  setTimeout(function () {
    if (window.__omiCAInstallWatch === document) return;
    window.__omiCAInstallWatch = document;
    var tryInject = function () {
      var root = document.documentElement;
      if (!root || document.getElementById("$controlProbeScriptId")) {
        if (window.__omiCAInstallTimer) clearInterval(window.__omiCAInstallTimer);
        return;
      }
      var mount = document.getElementById("root");
      var html = mount && typeof mount.innerHTML === "string" ? mount.innerHTML : "";
      var shell = document.querySelector("main[data-production-shell='true']");
      var route = shell ? shell.getAttribute("data-route") : "";
      if (!html || typeof route !== "string" || !route) return;
      var script = document.createElement("script");
      script.id = "$controlProbeScriptId";
      script.textContent = $bundle;
      root.appendChild(script);
      if (window.__omiCAInstallTimer) clearInterval(window.__omiCAInstallTimer);
    };
    window.__omiCAInstallTimer = setInterval(tryInject, 400);
    tryInject();
  }, 0);
  return "$controlProbePendingValue";
})()
''';
}

final _safeProbeBasename = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,191}\.(js|txt)$');

bool isSafeProbeBasename(String name) => _safeProbeBasename.hasMatch(name);

String? normalizeProbeJsResult(Object? result) {
  if (result == null) return null;
  if (result is Map || result is List) return jsonEncode(result);
  var text = result.toString();
  if (text == '<null>' || text == 'null' || text.isEmpty) return null;
  if (text.startsWith('"') && text.endsWith('"')) {
    try {
      final decoded = jsonDecode(text);
      if (decoded is String) {
        text = decoded;
      } else if (decoded is Map || decoded is List) {
        return jsonEncode(decoded);
      }
    } on FormatException {
      // WKWebView sometimes returns the raw JS string; keep it.
    }
  }
  if (text == '<null>' || text == 'null' || text.isEmpty) return null;
  return text;
}

String formatProbeJsLine({String? value, String error = 'none'}) {
  final sanitized = error.replaceAll(RegExp(r'\s+'), ' ').trim();
  return 'PROBE_JS: ${value ?? 'nil'} error: ${sanitized.isEmpty ? 'none' : sanitized}';
}

/// Closed production-route set. Flutter's `runJavaScriptReturningResult` has
/// returned an HTMLScriptElement payload for an inject IIFE (2026-08-16:
/// `script:true` and `mountLen:0` together). That string is not a shell.
const controlProbeShellReadyValues = {
  'home',
  'memories',
  'conversations',
  'folders',
  'tasks',
  'rewind',
  'apps',
  'brain-map',
  'listen',
  'chat',
  'settings',
  'unsupported',
  'ready',
};

bool isControlProbeShellReady(String? value) {
  if (value == null || value.isEmpty || value == controlProbePendingValue) return false;
  return controlProbeShellReadyValues.contains(value);
}

typedef ProbeEvaluate = Future<Object?> Function(String source);

final class ControlProbeDriver {
  ControlProbeDriver({
    required this.driverSource,
    required this.resultPath,
    required this.evaluate,
    this.pendingValue = controlProbePendingValue,
    this.maxAttempts = 100,
    this.retryInterval = const Duration(milliseconds: 400),
    this.initialDelay = const Duration(seconds: 5),
    this.evaluateTimeout = const Duration(seconds: 8),
    this.hostQuery = '',
    this.useJavaScriptChannel = false,
    this.shellWait = const Duration(seconds: 40),
    this.resultWait = const Duration(seconds: 90),
    this.sleep = _defaultSleep,
  }) {
    if (driverSource.trim().isEmpty) {
      throw const FormatException('control probe driver source is empty');
    }
    if (resultPath.isEmpty) {
      throw const FormatException('control probe result path is empty');
    }
  }

  final String driverSource;
  final String resultPath;
  final ProbeEvaluate evaluate;
  final String pendingValue;
  final int maxAttempts;
  final Duration retryInterval;
  final Duration initialDelay;
  final Duration evaluateTimeout;
  final String hostQuery;
  final bool useJavaScriptChannel;
  final Duration shellWait;
  final Duration resultWait;
  final Future<void> Function(Duration duration) sleep;
  bool _started = false;
  bool _wrote = false;
  Completer<String>? _shellCompleter;
  Completer<String>? _resultCompleter;
  final List<String> _channelInbox = [];

  static Future<void> _defaultSleep(Duration duration) => Future<void>.delayed(duration);

  Future<void> acceptChannel(String message) async {
    if (_wrote) return;
    if (_shellCompleter == null && _resultCompleter == null) {
      _channelInbox.add(message);
      return;
    }
    await _dispatchChannel(message);
  }

  Future<void> _dispatchChannel(String message) async {
    if (_wrote || message.isEmpty || message == pendingValue) return;
    if (message.startsWith('shell:')) {
      final route = message.substring('shell:'.length);
      final shell = _shellCompleter;
      if (isControlProbeShellReady(route) && shell != null && !shell.isCompleted) {
        shell.complete(route);
      }
      return;
    }
    final result = _resultCompleter;
    if (result != null && !result.isCompleted) {
      result.complete(message);
    }
  }

  void _drainChannelInbox() {
    final pending = List<String>.of(_channelInbox);
    _channelInbox.clear();
    for (final message in pending) {
      unawaited(_dispatchChannel(message));
    }
  }

  Future<Object?> _evaluateBounded(String source) {
    return evaluate(source).timeout(
      evaluateTimeout,
      onTimeout: () => throw TimeoutException('probe-evaluate-timeout'),
    );
  }

  Future<void> start() async {
    if (_started) return;
    _started = true;
    if (useJavaScriptChannel) {
      await _startViaChannel();
      return;
    }
    await _startViaEvaluate();
  }

  /// Re-inject the page-world driver after an `<a href>` navigation. The
  /// previous document's script is gone; sessionStorage/window.name is not.
  /// Must not reset storage.
  Future<void> resumeAfterNavigation() async {
    if (!_started || _wrote) return;
    final result = _resultCompleter;
    if (useJavaScriptChannel && (result == null || result.isCompleted)) return;
    try {
      await _evaluateBounded(controlProbeDeferredInstallSource(driverSource));
    } on TimeoutException {
      // The result wait still owns the timeout.
    }
  }

  Future<void> _startViaChannel() async {
    _shellCompleter = Completer<String>();
    _resultCompleter = Completer<String>();
    _drainChannelInbox();
    await sleep(initialDelay);
    await writeLine(formatProbeJsLine(value: pendingValue, error: 'probe-started'), finished: false);
    try {
      await _evaluateBounded(controlProbeDeferredShellWatchSource());
    } on TimeoutException catch (caught) {
      await writeLine(formatProbeJsLine(error: caught.message ?? 'probe-evaluate-timeout'));
      return;
    }
    String lastShell;
    try {
      lastShell = await _shellCompleter!.future.timeout(shellWait);
    } on TimeoutException {
      await writeLine(formatProbeJsLine(
        value: pendingValue,
        error: 'probe-timeout:shell-missing;dartQuery=${hostQuery.replaceAll(RegExp(r'\s+'), '')}',
      ));
      return;
    }
    try {
      await _evaluateBounded(controlProbeStorageResetSource);
    } catch (_) {
      // A missing document here still lets install proceed.
    }
    try {
      await _evaluateBounded(controlProbeDeferredInstallSource(driverSource));
    } on TimeoutException catch (caught) {
      await writeLine(formatProbeJsLine(error: caught.message ?? 'probe-evaluate-timeout'));
      return;
    }
    try {
      final value = await _resultCompleter!.future.timeout(resultWait);
      await writeLine(formatProbeJsLine(value: value));
    } on TimeoutException {
      await _writeTimeout(
        lastValue: pendingValue,
        error: 'probe-timeout:channel;lastShell=$lastShell;injected=true;dartQuery=${hostQuery.replaceAll(RegExp(r'\s+'), '')}',
        lastShellValue: lastShell,
        shellReady: true,
      );
    }
  }

  Future<void> _startViaEvaluate() async {
    await sleep(initialDelay);
    String? lastValue;
    String? lastShellValue;
    var error = 'none';
    var shellReady = false;
    try {
      for (var attempt = 1; attempt <= maxAttempts; attempt++) {
        final shell = normalizeProbeJsResult(await _evaluateBounded(controlProbeShellProbeSource));
        lastShellValue = shell;
        if (isControlProbeShellReady(shell)) {
          shellReady = true;
          break;
        }
        lastValue = pendingValue;
        if (attempt < maxAttempts) await sleep(retryInterval);
      }
    } on TimeoutException catch (caught) {
      await writeLine(formatProbeJsLine(error: caught.message ?? 'probe-evaluate-timeout'));
      return;
    } catch (caught) {
      error = caught.toString();
    }
    if (!shellReady) {
      await _writeTimeout(lastValue: lastValue, error: error, lastShellValue: lastShellValue, shellReady: false);
      return;
    }
    try {
      await _evaluateBounded(controlProbeStorageResetSource);
    } catch (_) {
      // A missing document here still lets install proceed.
    }
    final install = controlProbeInstallSource(driverSource);
    try {
      for (var attempt = 1; attempt <= maxAttempts; attempt++) {
        final value = normalizeProbeJsResult(await _evaluateBounded(install));
        lastValue = value;
        error = 'none';
        if (value != null && value != pendingValue) {
          await writeLine(formatProbeJsLine(value: value));
          return;
        }
        if (attempt < maxAttempts) await sleep(retryInterval);
      }
    } on TimeoutException catch (caught) {
      await writeLine(formatProbeJsLine(error: caught.message ?? 'probe-evaluate-timeout'));
      return;
    } catch (caught) {
      error = caught.toString();
      lastValue = null;
    }
    await _writeTimeout(lastValue: lastValue, error: error, lastShellValue: lastShellValue, shellReady: true);
  }

  Future<void> _writeTimeout({
    required String? lastValue,
    required String error,
    required String? lastShellValue,
    required bool shellReady,
  }) async {
    String? diagnostic;
    List<dynamic>? steps;
    try {
      diagnostic = normalizeProbeJsResult(await _evaluateBounded(controlProbeDiagnosticSource));
      if (diagnostic != null && diagnostic != pendingValue && diagnostic.startsWith('{')) {
        final decoded = jsonDecode(diagnostic);
        if (decoded is Map && decoded['steps'] is List) {
          steps = decoded['steps'] as List<dynamic>;
        }
      }
    } catch (_) {
      diagnostic = null;
    }
    final query = hostQuery.replaceAll(RegExp(r'\s+'), '');
    final timeoutLine = diagnostic != null && diagnostic.startsWith('{')
        ? formatProbeJsLine(
            value: lastValue,
            error:
                'probe-timeout:$diagnostic;lastShell=${lastShellValue ?? 'nil'};injected=$shellReady;dartQuery=$query',
          )
        : formatProbeJsLine(value: lastValue, error: error);
    if (steps != null && steps.isNotEmpty) {
      // Recorded outcomes are the CONTROL lines. A timeout that swallowed
      // them printed every slug missing-step after Listen had already
      // rendered a transcript (measured 2026-08-16).
      await writeBody(
        '$timeoutLine\n${formatProbeJsLine(value: jsonEncode({
          'schema': 'omi.control-acceptance.v1',
          'steps': steps,
        }))}\n',
      );
      return;
    }
    await writeLine(timeoutLine);
  }

  Future<void> writeLine(String line, {bool finished = true}) async {
    await writeBody('$line\n', finished: finished);
  }

  Future<void> writeBody(String body, {bool finished = true}) async {
    final result = File(resultPath);
    await result.parent.create(recursive: true);
    final temporary = File('$resultPath.$pid.${DateTime.now().microsecondsSinceEpoch}.tmp');
    try {
      await temporary.writeAsString(body, flush: true);
      await temporary.rename(resultPath);
      if (finished) _wrote = true;
    } finally {
      if (await temporary.exists()) await temporary.delete();
    }
  }

  Future<void> teardown() async {
    if (_wrote) return;
    final result = File(resultPath);
    if (await result.exists()) await result.delete();
  }
}
