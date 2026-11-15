import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('authenticated exit RPC refuses unfinished tests then exits only its child process', () async {
    final directory = await Directory.systemTemp.createTemp('heavy-exit-test-');
    final complete = File('${directory.path}/completed.txt');
    final retained = File('${directory.path}/retained.txt');
    await retained.writeAsString('synthetic retention canary');
    final helper = File('integration_test/perf/heavy_process_exit.dart').absolute.uri;
    final script = File('${directory.path}/child.dart');
    await script.writeAsString('import "dart:io";\n'
        'import "dart:developer" as developer;\n'
        'import ${jsonEncode(helper.toString())};\n'
        'Future<void> main() async {\n'
        ' registerHeavyProcessExit(testsComplete: () => File(${jsonEncode(complete.path)}).existsSync());\n'
        ' stdin.listen((_) {});\n'
        ' final service = await developer.Service.controlWebServer(enable: true);\n'
        ' stdout.writeln("READY:" + service.serverUri.toString());\n'
        '}\n');
    final child = await Process.start('dart', ['--enable-vm-service=0', script.path]);
    var exited = false;
    unawaited(child.exitCode.then((_) => exited = true));
    final ready = Completer<Uri>();
    // Drain rather than print: the VM startup banner contains its auth token.
    final stdoutDone = child.stdout.transform(utf8.decoder).transform(const LineSplitter()).forEach((line) {
      if (line.startsWith('READY:') && !ready.isCompleted) ready.complete(Uri.parse(line.substring(6)));
    });
    final stderrDone = child.stderr.drain<void>();
    final client = HttpClient();
    addTearDown(() async {
      client.close(force: true);
      if (!exited) child.kill(ProcessSignal.sigkill);
      await child.exitCode.timeout(const Duration(seconds: 15));
      await Future.wait([stdoutDone, stderrDone]);
      // Only this test's generated script/JSON/text files; no WAL/audio.
      await directory.delete(recursive: true);
    });
    final base = await ready.future.timeout(const Duration(seconds: 15));
    Future<Map<String, dynamic>> rpc(String method, [Map<String, String>? params]) async {
      try {
        final request = await client.getUrl(base.resolve(method).replace(queryParameters: params));
        final response = await request.close();
        return jsonDecode(await utf8.decoder.bind(response).join()) as Map<String, dynamic>;
      } catch (_) {
        // Do not expose a VM-service authentication token in a failure URI.
        throw StateError('Child VM RPC transport failed');
      }
    }

    final vm = await rpc('getVM');
    final isolates = vm['result']['isolates'] as List;
    final main = isolates.singleWhere((isolate) => isolate['name'] == 'main');
    final params = {'isolateId': main['id'] as String};
    final early = await rpc('ext.omi.heavy.exit', params);
    expect(early['error'], isNotNull);
    expect((await rpc('getVM'))['result']['pid'], child.pid);
    await complete.writeAsString('test teardown complete');
    final accepted = await rpc('ext.omi.heavy.exit', params);
    expect(accepted['result']['exiting'], isTrue);
    expect(await child.exitCode.timeout(const Duration(seconds: 15)), 0);
    expect(await retained.readAsString(), 'synthetic retention canary');
  });
}
