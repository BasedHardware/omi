import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/startup/boot_crash_handlers.dart';
import 'package:omi/startup/boot_journal.dart';
import 'package:omi/env/physical_qualification.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';

class _Documents extends PathProviderPlatform {
  _Documents(this.path);
  final String path;
  @override
  Future<String> getApplicationDocumentsPath() async => path;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('handlers are installed before Crashlytics and auth stages run', () async {
    final directory = await Directory.systemTemp.createTemp('boot-handler-');
    final previousProvider = PathProviderPlatform.instance;
    final previousFlutter = FlutterError.onError;
    final previousPlatform = PlatformDispatcher.instance.onError;
    PathProviderPlatform.instance = _Documents(directory.path);
    try {
      void flutterHandler(FlutterErrorDetails details) {}
      bool platformHandler(Object error, StackTrace stack) => true;
      await BootCrashHandlers.install(
        initialize: () async {
          expect(FlutterError.onError, same(flutterHandler));
          expect(PlatformDispatcher.instance.onError, same(platformHandler));
        },
        flutterError: flutterHandler,
        platformError: platformHandler,
      );
      await PhysicalQualification.startupStage('resolve_auth', () async {
        expect(FlutterError.onError, same(flutterHandler));
        expect(PlatformDispatcher.instance.onError, same(platformHandler));
      });
      final states = (await BootJournal.instance.read()).map((row) => row['stage']).toList();
      expect(states, contains('crash_reporter'));
      expect(states, contains('resolve_auth'));
    } finally {
      FlutterError.onError = previousFlutter;
      PlatformDispatcher.instance.onError = previousPlatform;
      PathProviderPlatform.instance = previousProvider;
      await directory.delete(recursive: true);
    }
  }, skip: PhysicalQualification.enabled);
}
