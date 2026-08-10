import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi_webview_proto/consumer_evidence.dart';

const hashA = '1111111111111111111111111111111111111111';
const hashB = '2222222222222222222222222222222222222222';

RenderedConsumerObservation observation(ConsumerEvidenceRoute route) => RenderedConsumerObservation(
  route: route,
  semantic: '${route.wireName}:rendered',
  transcript: route == ConsumerEvidenceRoute.listen ? 'synthetic local transcript' : null,
);

void main() {
  test('real iOS writer replaces no prior run and atomically writes the exact seven-row document', () async {
    final scratch = await Directory.systemTemp.createTemp('omi-ios-consumer-evidence-');
    addTearDown(() => scratch.delete(recursive: true));
    final result = File('${scratch.path}/result.json');
    await result.writeAsString('{"runId":"prior-run"}');
    final collector = ConsumerEvidenceCollector(
      resultPath: result.path,
      runId: 'run-ios-consumer',
      hashes: const ConsumerEvidenceTreeHashes(shell: hashA, surface: hashB),
    );
    await collector.prepare();
    expect(await result.exists(), isFalse, reason: 'prior-run success must be removed before driving');
    for (final route in ConsumerEvidenceRoute.values) {
      collector.accept(observation(route), route);
    }
    await collector.finish();

    final decoded = jsonDecode(await result.readAsString()) as Map<String, dynamic>;
    expect(decoded.keys.toSet(), {'schema', 'runId', 'rows'});
    expect(decoded['schema'], consumerEvidenceSchema);
    expect(decoded['runId'], 'run-ios-consumer');
    final rows = decoded['rows'] as List<dynamic>;
    expect(rows, hasLength(7));
    for (final rowValue in rows) {
      final row = rowValue as Map<String, dynamic>;
      expect(row.keys.toSet(), {
        'runId',
        'shell',
        'domain',
        'fixture',
        'evidence',
        'observation',
        'shellTreeHash',
        'surfaceTreeHash',
      });
      expect(row['runId'], 'run-ios-consumer');
      expect(row['shell'], 'ios');
      expect(row['fixture'], 'none');
      expect(row['evidence'], 'rendered-semantic');
      expect(row['shellTreeHash'], hashA);
      expect(row['surfaceTreeHash'], hashB);
      final rendered = row['observation'] as Map<String, dynamic>;
      expect(
        rendered.keys.toSet(),
        row['domain'] == 'listen' ? {'route', 'state', 'semantic', 'transcript'} : {'route', 'state', 'semantic'},
      );
    }
    expect(scratch.listSync().whereType<File>().map((file) => file.path), [result.path]);
  });

  test(
    'iOS validation rejects fixture intent, wrong identity, route reuse, and invalid transcripts or stamps',
    () async {
      expect(
        () => ConsumerEvidenceCollector(
          resultPath: '/tmp/not-written',
          runId: '__launch-intent',
          hashes: const ConsumerEvidenceTreeHashes(shell: hashA, surface: hashB),
        ),
        throwsFormatException,
      );
      expect(
        () => ConsumerEvidenceCollector(
          resultPath: '/tmp/not-written',
          runId: 'run-ok',
          shell: 'macos',
          hashes: const ConsumerEvidenceTreeHashes(shell: hashA, surface: hashB),
        ),
        throwsFormatException,
      );
      expect(
        () => ConsumerEvidenceTreeHashes.fromAssetJson(
          shellStamp: jsonEncode({'artifact': 'ios-bundle', 'treeHash': 'stale'}),
          surfaceStamp: jsonEncode({'artifact': 'surfaces-dist', 'treeHash': hashB}),
        ),
        throwsFormatException,
      );
      expect(
        () => RenderedConsumerObservation.decodeRenderedJson(
          '{"route":"chat","state":"ready","semantic":"intent","fixture":"none"}',
        ),
        throwsFormatException,
        reason: 'fixture-backed or launch-supplied fields are not rendered observation keys',
      );
      expect(
        () => RenderedConsumerObservation.decodeRenderedJson('{"route":"listen","state":"ready","semantic":"listen"}'),
        throwsFormatException,
      );
      expect(
        () => RenderedConsumerObservation.decodeRenderedJson(
          '{"route":"chat","state":"ready","semantic":"chat","transcript":"leak"}',
        ),
        throwsFormatException,
      );

      final scratch = await Directory.systemTemp.createTemp('omi-ios-consumer-red-');
      addTearDown(() => scratch.delete(recursive: true));
      final result = File('${scratch.path}/result.json');
      final collector = ConsumerEvidenceCollector(
        resultPath: result.path,
        runId: 'run-ios-red',
        hashes: const ConsumerEvidenceTreeHashes(shell: hashA, surface: hashB),
      );
      await collector.prepare();
      expect(
        () => collector.accept(observation(ConsumerEvidenceRoute.chat), ConsumerEvidenceRoute.memories),
        throwsStateError,
      );
      collector.accept(observation(ConsumerEvidenceRoute.memories), ConsumerEvidenceRoute.memories);
      expect(
        () => collector.accept(observation(ConsumerEvidenceRoute.memories), ConsumerEvidenceRoute.memories),
        throwsStateError,
      );
      expect(collector.finish, throwsStateError, reason: 'missing routes cannot write success');
      await collector.teardown();
      expect(await result.exists(), isFalse);
    },
  );

  test('iOS host lifecycle drives each rendered route once and waits for a Listen transcript', () async {
    // red-proof: observe Chat before the local POST is accepted; the driver
    // either writes no result or acceptedAdmissions remains zero.
    final scratch = await Directory.systemTemp.createTemp('omi-ios-consumer-driver-');
    addTearDown(() => scratch.delete(recursive: true));
    final result = File('${scratch.path}/result.json');
    final service = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    var acceptedAdmissions = 0;
    service.listen((request) async {
      if (request.method == 'POST' && request.uri.path == '/v1/chat-messages') {
        await utf8.decoder.bind(request).join();
        acceptedAdmissions++;
        request.response.statusCode = HttpStatus.created;
      } else {
        request.response.statusCode = HttpStatus.notFound;
      }
      await request.response.close();
    });
    addTearDown(() => service.close(force: true));
    final navigated = <ConsumerEvidenceRoute>[];
    var listenStarted = false;
    var listenStartAttempts = 0;
    var chatAuthored = false;
    var chatSubmitted = false;
    var chatAdmissionCount = 3;
    final collector = ConsumerEvidenceCollector(
      resultPath: result.path,
      runId: 'run-ios-driver',
      hashes: const ConsumerEvidenceTreeHashes(shell: hashA, surface: hashB),
    );
    await collector.prepare();
    final driver = ConsumerEvidenceDriver(
      collector: collector,
      navigate: (route) async => navigated.add(route),
      observe: () async {
        final route = navigated.last;
        if (route == ConsumerEvidenceRoute.listen && !listenStarted) {
          return null;
        }
        return jsonEncode(observation(route).toJson());
      },
      startListen: () async {
        listenStartAttempts++;
        if (listenStartAttempts < 2) return false;
        listenStarted = true;
        return true;
      },
      authorChat: () async {
        chatAuthored = true;
        return chatAdmissionCount;
      },
      submitChat: () async {
        if (!chatAuthored) return false;
        final client = HttpClient();
        final request = await client.postUrl(Uri.parse('http://127.0.0.1:${service.port}/v1/chat-messages'));
        request.headers.contentType = ContentType.json;
        request.write('{"text":"C3b3 deterministic synthetic Chat evidence."}');
        final response = await request.close();
        await response.drain<void>();
        client.close(force: true);
        if (response.statusCode != HttpStatus.created) return false;
        chatSubmitted = true;
        chatAdmissionCount++;
        return true;
      },
      observeChatAfterAdmission: (baseline) async {
        if (!chatSubmitted || chatAdmissionCount <= baseline) return null;
        return jsonEncode(observation(ConsumerEvidenceRoute.chat).toJson());
      },
      delay: (_) async {},
      maxPolls: 2,
    );
    await driver.start();
    for (var index = 0; index < ConsumerEvidenceRoute.values.length; index++) {
      await driver.pageFinished();
    }
    expect(navigated, ConsumerEvidenceRoute.values);
    expect(listenStarted, isTrue);
    expect(chatAuthored, isTrue);
    expect(chatSubmitted, isTrue);
    expect(chatAdmissionCount, 4);
    expect(acceptedAdmissions, 1);
    expect(listenStartAttempts, 2, reason: 'the host must retry until the rendered control exists');
    expect(await result.exists(), isTrue);
  });
}
