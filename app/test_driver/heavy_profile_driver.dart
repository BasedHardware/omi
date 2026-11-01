import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_driver/flutter_driver.dart';
import 'package:integration_test/common.dart';
import 'package:integration_test/integration_test_driver.dart' show writeResponseData;

/// Stream timeline chunks to the host instead of losing early scenarios to
/// the VM ring buffer. CPU bounds come from the app's monotonic scenario clock,
/// so fixture generation and receipt serialization cannot enter attribution.
Future<void> main() async {
  final output = Platform.environment['OMI_PERF_DEVICE_OUTPUT_DIR'];
  if (output == null) throw StateError('Heavy profile output directory is required');
  final run = int.parse(Platform.environment['OMI_PERF_RUN_NUMBER'] ?? '1');
  final timelineEnabled = Platform.environment['OMI_PERF_TIMELINE'] == '1';
  final platform = (await File('$output/platform.txt').readAsString()).trim();
  final device = (await File('$output/device-id.txt').readAsString()).trim();
  final timelineName = 'receipt-$run-timeline.json';
  final sink = timelineEnabled ? (File('$output/$timelineName').openWrite()..write('{"traceEvents":[')) : null;
  final seen = <String>{};
  var eventCount = 0;
  var truncated = false;
  void record(Map<String, dynamic> event) {
    if (eventCount >= 2000000) {
      truncated = true;
      return;
    }
    final key = '${event['pid']}/${event['tid']}/${event['ph']}/${event['ts']}/${event['name']}/${event['id']}';
    if (!seen.add(key)) return;
    if (eventCount++ > 0) sink!.write(',');
    sink!.write(jsonEncode(event));
  }

  final driver = await FlutterDriver.connect();
  StreamSubscription? subscription;
  int? ownedPid;
  String? ownedIsolateId;
  var ownsHarness = false;
  try {
    final service = driver.serviceClient;
    final vm = await service.getVM();
    final isolates = vm.isolates!.where((isolate) => isolate.name == 'main').toList();
    if (isolates.length != 1) throw StateError('Expected one main application isolate');
    final isolateId = isolates.single.id!;
    ownedIsolateId = isolateId;
    ownedPid = vm.pid;
    if (platform == 'ios' && Platform.environment['OMI_PERF_SIMULATOR'] != '1') {
      // Discovery may take minutes. Activate this exact DEV bundle before
      // releasing the scenario handshake; never terminate a connected VM.
      final activation = await Process.run('xcrun', [
        'devicectl',
        'device',
        'process',
        'launch',
        '--device',
        device,
        '--activate',
        '--timeout',
        '20',
        'com.friend-app-with-wearable.ios12.development'
      ]);
      if (activation.exitCode != 0) throw StateError('DEV foreground activation failed: ${activation.stderr}');
    }
    await service.setVMTimelineFlags([]);
    if (timelineEnabled) {
      subscription = service.onTimelineEvent.listen((event) {
        for (final item in event.timelineEvents ?? []) {
          if (item.json != null) record(item.json!);
        }
      });
      await service.streamListen('Timeline');
    }
    await service.clearCpuSamples(isolateId);
    await service.callServiceExtension('ext.omi.heavy.start', isolateId: isolateId);
    ownsHarness = true;
    final response = Response.fromJson(await driver.requestData(null, timeout: const Duration(minutes: 12)));
    final data = response.data ?? <String, dynamic>{};
    await service.setVMTimelineFlags([]);
    if (timelineEnabled) {
      final tail = await service.getVMTimeline();
      for (final event in tail.traceEvents ?? []) {
        if (event.json != null) record(event.json!);
      }
      await Future<void>.delayed(const Duration(milliseconds: 500));
      await subscription?.cancel();
      subscription = null;
    }
    data['heavy_run'] = {
      'source_sha': (await File('$output/source-sha.txt').readAsString()).trim(),
      'binary_sha256': (await File('$output/binary-sha256.txt').readAsString()).split(' ').first,
      'harness_sha256': (await File('$output/harness-sha256.txt').readAsString()).trim(),
      'device_id': device,
      'platform': platform,
      'device_os_version': data['heavy_profile']?['device_os_version'],
      'flutter_revision':
          (jsonDecode(await File('$output/flutter-version.json').readAsString()) as Map)['frameworkRevision'],
    };
    if (Platform.environment['OMI_PERF_VIRTUAL'] == '1') {
      data['heavy_run']['virtual_runtime'] = jsonDecode(await File('$output/virtual-runtime.json').readAsString());
      data['heavy_run']['launch_protocol'] = jsonDecode(await File('$output/launch-protocol.json').readAsString());
      data['heavy_host'] = jsonDecode(await File('$output/host-state.json').readAsString());
    }
    if (platform == 'android') {
      data['heavy_run']['native_harness'] = jsonDecode(await File('$output/native-harness.json').readAsString());
    }
    final scenarios = data['heavy_profile']?['scenarios'] as Map?;
    if (scenarios != null && scenarios.isNotEmpty) {
      final starts = scenarios.values.map((s) => s['start_vm_us'] as int).toList()..sort();
      final ends = scenarios.values.map((s) => s['end_vm_us'] as int).toList()..sort();
      if (timelineEnabled) {
        data['heavy_cpu_samples'] =
            _compactSamples((await service.getCpuSamples(isolateId, starts.first, ends.last - starts.first)).toJson());
      }
      data['heavy_timeline_capture'] = {
        'enabled': timelineEnabled,
        'file': timelineEnabled ? timelineName : null,
        'events': eventCount,
        'truncated': truncated,
        'start_vm_us': starts.first,
        'end_vm_us': ends.last
      };
    }
    await writeResponseData(data, destinationDirectory: output);
    final passed = response.allTestsPassed && !truncated;
    if (!passed) {
      final details = response.formattedFailureDetails;
      stderr.writeln(details);
      final rejection = data['heavy_measurement_rejection'];
      if (!response.allTestsPassed && rejection is Map && rejection['kind'] == 'foreground_or_frames') {
        await File('$output/measurement-rejected.json').writeAsString(jsonEncode(rejection));
      }
      if (truncated) stderr.writeln('Timeline exceeded the bounded event budget');
      exitCode = 1;
    }
    stdout.writeln(jsonEncode({'heavy_driver_passed': passed}));
  } finally {
    await subscription?.cancel();
    sink?.write(']}');
    await sink?.close();
    if (ownsHarness) {
      // Keep installation/data. The authenticated extension exits this exact
      // completed harness process on both OSes; no external PID/package kill.
      try {
        final current = await driver.serviceClient.getVM();
        if (ownedPid == null ||
            current.pid != ownedPid ||
            ownedIsolateId == null ||
            !current.isolates!.any((isolate) => isolate.id == ownedIsolateId)) {
          throw StateError('Harness process/isolate ownership changed');
        }
        final response =
            await driver.serviceClient.callServiceExtension('ext.omi.heavy.exit', isolateId: ownedIsolateId);
        if (response.json?['exiting'] != true) throw StateError('Harness refused completed-process exit');
        await File('$output/process-cleanup.json').writeAsString(jsonEncode({
          'pid': ownedPid,
          'self_exit_acknowledged': true,
          'uninstall_requested': false,
        }));
      } catch (error) {
        stderr.writeln('Harness process cleanup: $error');
        exitCode = 1;
      }
    }
    await driver.close();
  }
}

/// VM AOT tables include every compiled function, even when never sampled.
/// Retain every sample and referenced function, with a lossless index remap.
Map<String, dynamic> _compactSamples(Map<String, dynamic> raw) {
  final functions = raw['functions'] as List;
  final samples = raw['samples'] as List;
  final used = <int>{for (final sample in samples) ...((sample['stack'] as List).cast<int>())}.toList()..sort();
  final remap = {for (var i = 0; i < used.length; i++) used[i]: i};
  return {
    ...raw,
    'original_function_count': functions.length,
    'functions': [for (final index in used) functions[index]],
    'samples': [
      for (final sample in samples)
        {
          ...Map<String, dynamic>.from(sample as Map),
          'stack': [for (final index in sample['stack'] as List) remap[index]!],
        }
    ],
  };
}
