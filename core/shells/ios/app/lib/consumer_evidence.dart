import 'dart:async';
import 'dart:convert';
import 'dart:io';

const consumerEvidenceSchema = 'omi.consumer-evidence.v1';

enum ConsumerEvidenceRoute { memories, tasks, conversations, folders, listen, chat, settings }

extension ConsumerEvidenceRouteName on ConsumerEvidenceRoute {
  String get wireName => name;
}

final class RenderedConsumerObservation {
  const RenderedConsumerObservation({required this.route, required this.semantic, this.transcript});

  final ConsumerEvidenceRoute route;
  final String semantic;
  final String? transcript;

  Map<String, Object> toJson() {
    final value = <String, Object>{'route': route.wireName, 'state': 'ready', 'semantic': semantic};
    if (transcript case final transcript?) {
      value['transcript'] = transcript;
    }
    return value;
  }

  static RenderedConsumerObservation decodeRenderedJson(String encoded) {
    final decoded = jsonDecode(encoded);
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('observation is not an object');
    }
    final routeName = decoded['route'];
    final route = ConsumerEvidenceRoute.values.where((value) => value.wireName == routeName).firstOrNull;
    final expectedKeys = route == ConsumerEvidenceRoute.listen
        ? const {'route', 'state', 'semantic', 'transcript'}
        : const {'route', 'state', 'semantic'};
    if (decoded.keys.toSet().difference(expectedKeys).isNotEmpty ||
        expectedKeys.difference(decoded.keys.toSet()).isNotEmpty) {
      throw const FormatException('observation keys are not exact');
    }
    final semantic = decoded['semantic'];
    if (route == null ||
        decoded['state'] != 'ready' ||
        semantic is! String ||
        semantic.trim().isEmpty ||
        utf8.encode(semantic).length > 256) {
      throw const FormatException('observation is not rendered-ready');
    }
    final transcript = decoded['transcript'];
    if (route == ConsumerEvidenceRoute.listen) {
      if (transcript is! String || transcript.trim().isEmpty || utf8.encode(transcript).length > 1024) {
        throw const FormatException('Listen needs a bounded transcript');
      }
    } else if (transcript != null) {
      throw const FormatException('non-Listen transcript leaked');
    }
    return RenderedConsumerObservation(route: route, semantic: semantic, transcript: transcript as String?);
  }
}

final class ConsumerEvidenceTreeHashes {
  const ConsumerEvidenceTreeHashes({required this.shell, required this.surface});

  final String shell;
  final String surface;

  factory ConsumerEvidenceTreeHashes.fromAssetJson({required String shellStamp, required String surfaceStamp}) {
    String read(String encoded, String artifact) {
      final decoded = jsonDecode(encoded);
      if (decoded is! Map<String, dynamic> ||
          decoded['artifact'] != artifact ||
          decoded.containsKey('unavailable') ||
          decoded['treeHash'] is! String ||
          !RegExp(r'^[0-9a-f]{40}$').hasMatch(decoded['treeHash'] as String)) {
        throw FormatException('invalid or stale $artifact tree hash');
      }
      return decoded['treeHash'] as String;
    }

    return ConsumerEvidenceTreeHashes(
      shell: read(shellStamp, 'ios-bundle'),
      surface: read(surfaceStamp, 'surfaces-dist'),
    );
  }
}

final class ConsumerEvidenceCollector {
  ConsumerEvidenceCollector({required this.resultPath, required this.runId, required this.hashes, this.shell = 'ios'}) {
    if (!RegExp(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$').hasMatch(runId) ||
        runId == 'anonymous' ||
        runId == 'overflow' ||
        runId.startsWith('__')) {
      throw const FormatException('invalid run id');
    }
    if (shell != 'ios') throw const FormatException('invalid shell');
  }

  final String resultPath;
  final String runId;
  final String shell;
  final ConsumerEvidenceTreeHashes hashes;
  final Map<ConsumerEvidenceRoute, Map<String, Object>> _rows = {};
  bool _didWrite = false;

  Future<void> prepare() async {
    final result = File(resultPath);
    if (await result.exists()) await result.delete();
  }

  void accept(RenderedConsumerObservation observation, ConsumerEvidenceRoute expected) {
    if (observation.semantic.trim().isEmpty ||
        utf8.encode(observation.semantic).length > 256 ||
        (expected == ConsumerEvidenceRoute.listen
            ? observation.transcript == null ||
                  observation.transcript!.trim().isEmpty ||
                  utf8.encode(observation.transcript!).length > 1024
            : observation.transcript != null)) {
      throw const FormatException('observation is not rendered-ready');
    }
    if (observation.route != expected) {
      throw StateError('expected rendered route ${expected.wireName}, got ${observation.route.wireName}');
    }
    if (_rows.containsKey(expected)) {
      throw StateError('duplicate rendered route ${expected.wireName}');
    }
    _rows[expected] = {
      'runId': runId,
      'shell': shell,
      'domain': expected.wireName,
      'fixture': 'none',
      'evidence': 'rendered-semantic',
      'observation': observation.toJson(),
      'shellTreeHash': hashes.shell,
      'surfaceTreeHash': hashes.surface,
    };
  }

  Future<void> finish() async {
    if (_rows.length != ConsumerEvidenceRoute.values.length) {
      throw StateError('all seven rendered routes are required');
    }
    final rows = ConsumerEvidenceRoute.values
        .map((route) {
          final row = _rows[route];
          if (row == null) {
            throw StateError('all seven rendered routes are required');
          }
          return row;
        })
        .toList(growable: false);
    final result = File(resultPath);
    await result.parent.create(recursive: true);
    final temporary = File('$resultPath.$pid.${DateTime.now().microsecondsSinceEpoch}.tmp');
    try {
      await temporary.writeAsString(
        '${const JsonEncoder.withIndent('  ').convert({'schema': consumerEvidenceSchema, 'runId': runId, 'rows': rows})}\n',
        flush: true,
      );
      await temporary.rename(resultPath);
      _didWrite = true;
    } finally {
      if (await temporary.exists()) await temporary.delete();
    }
  }

  Future<void> teardown() async {
    if (_didWrite) return;
    final result = File(resultPath);
    if (await result.exists()) await result.delete();
  }
}

typedef EvidenceNavigate = Future<void> Function(ConsumerEvidenceRoute route);
typedef EvidenceObserve = Future<String?> Function();
typedef EvidenceStartListen = Future<bool> Function();
typedef EvidenceAuthorChat = Future<int?> Function();
typedef EvidenceSubmitChat = Future<bool> Function();
typedef EvidenceObserveChatAfterAdmission = Future<String?> Function(int baseline);

final class ConsumerEvidenceDriver {
  ConsumerEvidenceDriver({
    required this.collector,
    required this.navigate,
    required this.observe,
    required this.startListen,
    required this.authorChat,
    required this.submitChat,
    required this.observeChatAfterAdmission,
    this.delay = _defaultDelay,
    this.maxPolls = 200,
  });

  final ConsumerEvidenceCollector collector;
  final EvidenceNavigate navigate;
  final EvidenceObserve observe;
  final EvidenceStartListen startListen;
  final EvidenceAuthorChat authorChat;
  final EvidenceSubmitChat submitChat;
  final EvidenceObserveChatAfterAdmission observeChatAfterAdmission;
  final Future<void> Function(Duration duration) delay;
  final int maxPolls;
  int _routeIndex = 0;
  bool _polling = false;
  bool _closed = false;

  static Future<void> _defaultDelay(Duration duration) => Future<void>.delayed(duration);

  Future<void> start() async => navigate(ConsumerEvidenceRoute.values.first);

  Future<void> pageFinished() async {
    if (_closed || _polling || _routeIndex >= ConsumerEvidenceRoute.values.length) {
      return;
    }
    _polling = true;
    try {
      final expected = ConsumerEvidenceRoute.values[_routeIndex];
      var listenStarted = false;
      int? chatAdmissionBaseline;
      var chatSubmitted = false;
      for (var attempt = 0; attempt < maxPolls; attempt++) {
        if (expected == ConsumerEvidenceRoute.listen && !listenStarted) {
          listenStarted = await startListen();
          if (!listenStarted) {
            await delay(const Duration(milliseconds: 150));
            continue;
          }
        }
        if (expected == ConsumerEvidenceRoute.chat && chatAdmissionBaseline == null) {
          chatAdmissionBaseline = await authorChat();
          if (chatAdmissionBaseline == null) {
            await delay(const Duration(milliseconds: 150));
            continue;
          }
        }
        if (expected == ConsumerEvidenceRoute.chat && !chatSubmitted) {
          chatSubmitted = await submitChat();
          if (!chatSubmitted) {
            await delay(const Duration(milliseconds: 150));
            continue;
          }
        }
        final encoded = expected == ConsumerEvidenceRoute.chat
            ? await observeChatAfterAdmission(chatAdmissionBaseline!)
            : await observe();
        if (encoded != null && encoded != 'null') {
          final observation = RenderedConsumerObservation.decodeRenderedJson(encoded);
          collector.accept(observation, expected);
          _routeIndex++;
          if (_routeIndex == ConsumerEvidenceRoute.values.length) {
            await collector.finish();
            _closed = true;
          } else {
            await navigate(ConsumerEvidenceRoute.values[_routeIndex]);
          }
          return;
        }
        await delay(const Duration(milliseconds: 150));
      }
      throw StateError('timed out waiting for rendered semantic observation on ${expected.wireName}');
    } catch (_) {
      _closed = true;
      await collector.teardown();
      rethrow;
    } finally {
      _polling = false;
    }
  }

  Future<void> teardown() async {
    _closed = true;
    await collector.teardown();
  }
}

const renderedConsumerObservationJavaScript = r'''
(() => {
  const e = document.querySelector("main[data-production-shell='true']");
  if (!e || e.dataset.surfaceState !== 'ready' || e.dataset.qaFixture !== 'none') return null;
  const route = e.dataset.route;
  const semantic = e.dataset.consumerSemantic;
  if (!['memories','tasks','conversations','folders','listen','chat','settings'].includes(route)) return null;
  if (typeof semantic !== 'string' || semantic.trim() === '' || new TextEncoder().encode(semantic).length > 256) return null;
  if (route === 'listen') {
    const transcript = e.dataset.consumerTranscript;
    if (typeof transcript !== 'string' || transcript.trim() === '' || new TextEncoder().encode(transcript).length > 1024) return null;
    return JSON.stringify({route, state:'ready', semantic, transcript});
  }
  if (e.dataset.consumerTranscript !== undefined) return null;
  return JSON.stringify({route, state:'ready', semantic});
})()
''';

const startListenConsumerEvidenceJavaScript = r'''
(() => {
  const button = document.querySelector("main[data-production-shell='true'][data-route='listen'][data-surface-state='ready'] [data-consumer-action='start-listen']");
  if (!button) return false;
  button.click();
  return true;
})()
''';

const authorChatConsumerEvidenceJavaScript = r'''
(() => {
  const root = document.querySelector("main[data-production-shell='true'][data-route='chat'][data-surface-state='ready'][data-qa-fixture='none']");
  if (!root) return null;
  const baseline = Number(root.dataset.consumerChatAdmissionCount);
  const draft = root.querySelector('textarea.chat-draft');
  if (!Number.isSafeInteger(baseline) || baseline < 0 || !draft) return null;
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
  if (!setter) return null;
  setter.call(draft, 'C3b3 deterministic synthetic Chat evidence.');
  draft.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText'}));
  return baseline;
})()
''';

const submitChatConsumerEvidenceJavaScript = r'''
(() => {
  const root = document.querySelector("main[data-production-shell='true'][data-route='chat'][data-surface-state='ready'][data-qa-fixture='none']");
  const button = root?.querySelector('button.chat-send');
  if (!button || button.disabled) return false;
  button.click();
  return true;
})()
''';

String renderedChatObservationJavaScript(int baseline) =>
    '''
(() => {
  const e = document.querySelector("main[data-production-shell='true'][data-route='chat']");
  if (!e || e.dataset.surfaceState !== 'ready' || e.dataset.qaFixture !== 'none') return null;
  const admitted = Number(e.dataset.consumerChatAdmissionCount);
  if (!Number.isSafeInteger(admitted) || admitted <= $baseline) return null;
  const semantic = e.dataset.consumerSemantic;
  if (typeof semantic !== 'string' || semantic.trim() === '' || new TextEncoder().encode(semantic).length > 256) return null;
  if (e.dataset.consumerTranscript !== undefined) return null;
  return JSON.stringify({route:'chat', state:'ready', semantic});
})()
''';
