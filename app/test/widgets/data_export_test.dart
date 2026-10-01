import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/data_export.dart';
import 'package:omi/ui/ui.dart';

class _Harness {
  late final Directory exportDir;
  String? lastPath;
  ShareParams? params;
  String currentOwner = 'owner-1';
  int downloadCalls = 0;
  int exportDirCalls = 0;
  int exportedCalls = 0;
  final deletedDirs = <String>[];
  Future<Directory> Function()? exportDirImpl;
  Future<ShareResult> Function(ShareParams)? shareImpl;
  Future<String?> Function(String path, {void Function(int)? onProgress, Future<void>? abortTrigger})? downloadImpl;
}

Future<void> _pumpApp(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    theme: ThemeData.dark(),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Builder(
      builder: (context) => Scaffold(
        body: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextButton(
                onPressed: () {},
                child: const Text('export'),
              ),
            ],
          ),
        ),
      ),
    ),
  ));
}

Future<void> _run(WidgetTester tester, _Harness harness) {
  final context = tester.element(find.byType(Scaffold));
  return DataExport.run(
    context,
    shareOrigin: const Rect.fromLTWH(1, 1, 10, 10),
    exportDirectory: () async {
      harness.exportDirCalls++;
      if (harness.exportDirImpl != null) return harness.exportDirImpl!();
      return harness.exportDir;
    },
    cleanupDirectory: (dir) async {
      if (dir != null) harness.deletedDirs.add(dir.path);
    },
    download: (path, {onProgress, abortTrigger}) {
      harness.lastPath = path;
      harness.downloadCalls++;
      return harness.downloadImpl!(path, onProgress: onProgress, abortTrigger: abortTrigger);
    },
    share: (params) {
      harness.params = params;
      return (harness.shareImpl ?? (p) async => const ShareResult('test', ShareResultStatus.success))(params);
    },
    ownerId: () => harness.currentOwner,
    onExported: () => harness.exportedCalls++,
  );
}

Future<void> _finishRun(WidgetTester tester, Future<void> running) async {
  var done = false;
  unawaited(running.then((_) => done = true));
  for (var i = 0; i < 200 && !done; i++) {
    await tester.pump(const Duration(milliseconds: 20));
  }
  expect(done, isTrue);
  await running;
  for (var i = 0; i < 50 && find.byType(OmiSpinner).evaluate().isNotEmpty; i++) {
    await tester.pump(const Duration(milliseconds: 20));
  }
  await tester.pump(const Duration(milliseconds: 300));
}

Future<String?> _successDownload(
  String path, {
  void Function(int)? onProgress,
  Future<void>? abortTrigger,
}) async {
  onProgress?.call(3);
  onProgress?.call(30);
  return path;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _Harness harness;

  setUp(() {
    harness = _Harness();
    harness.exportDir = Directory('${Directory.systemTemp.path}/omi-export-widget-test-dir');
    DataExport.exportInProgress.value = false;
    DataExport.debugClearRetainedExportDirectory();
  });

  tearDown(() {
    DataExport.exportInProgress.value = false;
    DataExport.debugClearRetainedExportDirectory();
  });

  testWidgets('successful export shares file with filename, MIME type, and origin', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    harness.downloadImpl = _successDownload;

    await _finishRun(tester, _run(tester, harness));

    expect(harness.params, isNotNull);
    final params = harness.params!;
    expect(params.files!.single.path, endsWith('omi-export.json'));
    expect(params.files!.single.mimeType, 'application/json');
    expect(params.sharePositionOrigin, const Rect.fromLTWH(1, 1, 10, 10));
    expect(harness.exportedCalls, 1);
    expect(DataExport.exportInProgress.value, isFalse);
    expect(find.text(l10n.exportFailedTryAgain), findsNothing);
    expect(harness.lastPath, contains(harness.exportDir.path));
  });

  testWidgets('repeated taps while exporting do not start a second download', (tester) async {
    await _pumpApp(tester);
    final gate = Completer<String?>();
    harness.downloadImpl = (path, {onProgress, abortTrigger}) => gate.future;

    final running = _run(tester, harness);
    for (var i = 0; i < 200 && harness.downloadCalls == 0; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    expect(harness.downloadCalls, 1);

    await _run(tester, harness);
    expect(harness.downloadCalls, 1);

    gate.complete(harness.lastPath);
    await _finishRun(tester, running);
    expect(harness.downloadCalls, 1);
    expect(harness.exportedCalls, 1);
  });

  testWidgets('shows persistent progress with real byte count and no invented total', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    harness.downloadImpl = (path, {onProgress, abortTrigger}) async {
      onProgress?.call(12);
      onProgress?.call(2048);
      await abortTrigger;
      return null;
    };

    final running = _run(tester, harness);
    for (var i = 0; i < 200 && find.byType(OmiSpinner).evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byType(OmiSpinner), findsOneWidget);
    expect(find.text(l10n.exportingAllData), findsOneWidget);
    expect(find.textContaining(l10n.downloading), findsOneWidget);
    expect(find.textContaining('2.00 KB'), findsOneWidget);
    expect(find.textContaining('%'), findsNothing);

    tester.widget<OmiButton>(find.byType(OmiButton)).onPressed?.call();
    await tester.pump();
    await _finishRun(tester, running);
    expect(harness.params, isNull);
  });

  testWidgets('download failure shows error and try again reuses injected seams', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    harness.downloadImpl = (path, {onProgress, abortTrigger}) async => null;

    await _finishRun(tester, _run(tester, harness));

    expect(harness.exportedCalls, 0);
    expect(find.text(l10n.exportFailedTryAgain), findsOneWidget);
    expect(find.text(l10n.tryAgain), findsOneWidget);
    expect(harness.params, isNull);
    expect(harness.exportDirCalls, 1);
    expect(harness.deletedDirs, [harness.exportDir.path]);

    tester.widget<SnackBarAction>(find.widgetWithText(SnackBarAction, l10n.tryAgain)).onPressed();
    for (var i = 0; i < 200 && (harness.downloadCalls < 2 || DataExport.exportInProgress.value); i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }

    expect(harness.exportDirCalls, 2);
    expect(harness.downloadCalls, 2);
    expect(harness.exportedCalls, 0);
  });

  testWidgets('share result unavailable shows error with try again', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    harness.downloadImpl = _successDownload;
    harness.shareImpl = (params) async => const ShareResult('test', ShareResultStatus.unavailable);

    await _finishRun(tester, _run(tester, harness));

    expect(harness.params, isNotNull);
    expect(harness.exportedCalls, 0);
    expect(find.text(l10n.exportFailedTryAgain), findsOneWidget);
    expect(find.text(l10n.tryAgain), findsOneWidget);
  });

  testWidgets('thrown share exception shows error with try again', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    harness.downloadImpl = _successDownload;
    harness.shareImpl = (params) async => throw StateError('share failed');

    await _finishRun(tester, _run(tester, harness));

    expect(harness.exportedCalls, 0);
    expect(find.text(l10n.exportFailedTryAgain), findsOneWidget);
    expect(find.text(l10n.tryAgain), findsOneWidget);
  });

  testWidgets('dismissing the share sheet is not treated as failure or success', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    harness.downloadImpl = _successDownload;
    harness.shareImpl = (params) async => const ShareResult('test', ShareResultStatus.dismissed);

    await _finishRun(tester, _run(tester, harness));

    expect(harness.params, isNotNull);
    expect(harness.exportedCalls, 0);
    expect(find.text(l10n.exportFailedTryAgain), findsNothing);
    expect(find.byType(SnackBar), findsNothing);
  });

  testWidgets('cancel aborts the download and never shares even if a path returns', (tester) async {
    await _pumpApp(tester);
    var sawAbort = false;
    harness.downloadImpl = (path, {onProgress, abortTrigger}) async {
      onProgress?.call(5);
      await abortTrigger;
      sawAbort = true;
      return _successDownload(path);
    };

    final running = _run(tester, harness);
    for (var i = 0; i < 200 && find.byType(OmiSpinner).evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byType(OmiSpinner), findsOneWidget);
    tester.widget<OmiButton>(find.byType(OmiButton)).onPressed?.call();
    await tester.pump();
    await _finishRun(tester, running);

    expect(sawAbort, isTrue);
    expect(harness.params, isNull);
    expect(harness.exportedCalls, 0);
    expect(harness.deletedDirs, [harness.exportDir.path]);
    expect(find.byType(SnackBar), findsNothing);
    expect(find.byType(Scaffold), findsOneWidget);
    expect(Navigator.of(tester.element(find.byType(Scaffold))).canPop(), isFalse);
  });

  testWidgets('external sheet dismissal aborts export and keeps the settings route', (tester) async {
    await _pumpApp(tester);
    final gate = Completer<String?>();
    var sawAbort = false;
    harness.downloadImpl = (path, {onProgress, abortTrigger}) async {
      unawaited(abortTrigger?.then((_) => sawAbort = true));
      return gate.future;
    };

    final running = _run(tester, harness);
    for (var i = 0; i < 200 && find.byType(OmiSpinner).evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    Navigator.of(tester.element(find.byType(Scaffold))).pop();
    gate.complete(harness.lastPath);
    await _finishRun(tester, running);

    expect(sawAbort, isTrue);
    expect(harness.params, isNull);
    expect(harness.exportedCalls, 0);
    expect(harness.deletedDirs, [harness.exportDir.path]);
    expect(find.byType(Scaffold), findsOneWidget);
    expect(Navigator.of(tester.element(find.byType(Scaffold))).canPop(), isFalse);
  });

  testWidgets('export directory failure dismisses sheet and keeps the settings route', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    harness.exportDirImpl = () async => throw StateError('temp dir unavailable');
    harness.downloadImpl = _successDownload;

    await _finishRun(tester, _run(tester, harness));

    expect(harness.downloadCalls, 0);
    expect(harness.exportedCalls, 0);
    expect(find.text(l10n.exportFailedTryAgain), findsOneWidget);
    expect(find.byType(OmiSpinner), findsNothing);
    expect(find.byType(Scaffold), findsOneWidget);
    expect(Navigator.of(tester.element(find.byType(Scaffold))).canPop(), isFalse);
  });

  testWidgets('account change during export prevents sharing', (tester) async {
    await _pumpApp(tester);
    harness.downloadImpl = (path, {onProgress, abortTrigger}) async {
      harness.currentOwner = 'owner-2';
      return _successDownload(path, onProgress: onProgress, abortTrigger: abortTrigger);
    };

    await _finishRun(tester, _run(tester, harness));

    expect(harness.params, isNull);
    expect(harness.exportedCalls, 0);
    expect(harness.deletedDirs, [harness.exportDir.path]);
  });
}
