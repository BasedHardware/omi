import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/user_data_export.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/data_export.dart';
import 'package:omi/pages/settings/data_export_files.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';

final class _ExportTokenGateway implements AuthTokenGateway {
  _ExportTokenGateway(this._harness);

  final _Harness _harness;
  int refreshCalls = 0;
  int signOutCalls = 0;

  @override
  AuthUserSnapshot? get currentUser {
    final owner = _harness.currentOwner;
    return owner == null ? null : AuthUserSnapshot(uid: owner);
  }

  @override
  Future<RefreshedAuthToken?> forceRefresh() async {
    refreshCalls++;
    return RefreshedAuthToken(token: 'token-${_harness.currentOwner}', expirationTime: DateTime.now());
  }

  @override
  Future<void> signOut() async {
    signOutCalls++;
  }
}

class _Harness {
  late final Directory exportDir;
  late final AuthService authService;
  String? lastPath;
  ShareParams? params;
  String? currentOwner = 'owner-1';
  int downloadCalls = 0;
  int exportDirCalls = 0;
  int exportedCalls = 0;
  final deletedDirs = <String>[];
  Future<Directory> Function()? exportDirImpl;
  Future<ShareResult> Function(ShareParams)? shareImpl;
  Future<void> Function(Directory directory)? shareLeaseImpl;
  Future<int> Function(Set<String> protectedPaths)? sweepImpl;
  Set<String>? protectedPathsSeen;
  final sharedPaths = <String>[];
  Future<String?> Function(
    String path, {
    void Function(int)? onProgress,
    Future<void>? abortTrigger,
    AuthSessionSnapshot? authorizationSnapshot,
  })? downloadImpl;

  void switchOwnerTo(String? uid) {
    currentOwner = uid;
    authService.handleAuthUserChanged(uid);
  }
}

Future<void> _pumpApp(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Builder(
        builder: (context) => Scaffold(
          body: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [TextButton(onPressed: () {}, child: const Text('export'))],
            ),
          ),
        ),
      ),
    ),
  );
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
      if (dir != null) {
        harness.deletedDirs.add(dir.path);
        if (dir.existsSync()) dir.deleteSync(recursive: true);
      }
    },
    download: (path, {onProgress, abortTrigger, authorizationSnapshot}) {
      harness.lastPath = path;
      harness.downloadCalls++;
      return harness.downloadImpl!(
        path,
        onProgress: onProgress,
        abortTrigger: abortTrigger,
        authorizationSnapshot: authorizationSnapshot,
      );
    },
    share: (params) {
      harness.params = params;
      harness.sharedPaths.add(params.files!.single.path);
      return (harness.shareImpl ?? (p) async => const ShareResult('test', ShareResultStatus.success))(params);
    },
    ownerId: () => harness.currentOwner,
    authService: harness.authService,
    sweepStaleExports: (protectedPaths) {
      harness.protectedPathsSeen = protectedPaths;
      return harness.sweepImpl?.call(protectedPaths) ?? Future<int>.value(0);
    },
    shareLease: (dir) => harness.shareLeaseImpl?.call(dir) ?? Future<void>.value(),
    onExported: () => harness.exportedCalls++,
  );
}

Future<void> _finishRun(WidgetTester tester, Future<void> running) async {
  for (var i = 0; i < 5 && !DataExport.exportInProgress.value; i++) {
    await tester.pump(const Duration(milliseconds: 20));
  }
  for (var i = 0; i < 400 && DataExport.exportInProgress.value; i++) {
    await tester.pump(const Duration(milliseconds: 20));
    if (i % 5 == 0) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
    }
  }
  expect(DataExport.exportInProgress.value, isFalse, reason: 'export still in progress');
  await tester.runAsync(() => running);
  for (var i = 0; i < 50 && find.byType(OmiSpinner).evaluate().isNotEmpty; i++) {
    await tester.pump(const Duration(milliseconds: 20));
  }
  await tester.pump(const Duration(milliseconds: 300));
}

Future<String?> _successDownload(
  String path, {
  void Function(int)? onProgress,
  Future<void>? abortTrigger,
  AuthSessionSnapshot? authorizationSnapshot,
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
    harness.exportDir = Directory.systemTemp.createTempSync('omi-export-widget-');
    harness.authService = AuthService.forTesting(
      tokenGateway: _ExportTokenGateway(harness),
      refreshDelay: (_) async {},
    );
    DataExport.exportInProgress.value = false;
    DataExport.debugClearRetainedExportDirectory();
  });

  tearDown(() {
    DataExport.exportInProgress.value = false;
    DataExport.debugClearRetainedExportDirectory();
    if (harness.exportDir.existsSync()) {
      harness.exportDir.deleteSync(recursive: true);
    }
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
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) => gate.future;

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
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) async {
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
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) async => null;

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
    expect(harness.deletedDirs, [harness.exportDir.path]);
  });

  testWidgets('cancel aborts the download and never shares even if a path returns', (tester) async {
    await _pumpApp(tester);
    var sawAbort = false;
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) async {
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
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) async {
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
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) async {
      harness.switchOwnerTo('owner-2');
      return _successDownload(path, onProgress: onProgress, abortTrigger: abortTrigger);
    };

    await _finishRun(tester, _run(tester, harness));

    expect(harness.params, isNull);
    expect(harness.exportedCalls, 0);
    expect(harness.deletedDirs, [harness.exportDir.path]);
  });

  testWidgets('owner swap A-B-A during export still prevents sharing', (tester) async {
    await _pumpApp(tester);
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) async {
      harness.switchOwnerTo('owner-2');
      harness.switchOwnerTo('owner-1');
      return _successDownload(path, onProgress: onProgress, abortTrigger: abortTrigger);
    };

    await _finishRun(tester, _run(tester, harness));

    expect(harness.params, isNull);
    expect(harness.exportedCalls, 0);
    expect(harness.deletedDirs, [harness.exportDir.path]);
  });

  testWidgets('failed share retains the file and retry shares the same path', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    harness.exportDirImpl = () async {
      await harness.exportDir.create(recursive: true);
      return harness.exportDir;
    };
    final sharedPaths = <String>[];
    var shareCalls = 0;
    harness.shareImpl = (params) async {
      shareCalls++;
      sharedPaths.add(params.files!.single.path);
      if (shareCalls == 1) throw StateError('share sheet failed');
      return const ShareResult('test', ShareResultStatus.success);
    };
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) async {
      await File(path).create(recursive: true);
      await File(path).writeAsString('{"ok": true}');
      return path;
    };

    await _finishRun(tester, _run(tester, harness));

    expect(shareCalls, 1);
    expect(harness.downloadCalls, 1);
    expect(harness.deletedDirs, isEmpty);
    expect(find.text(l10n.exportFailedTryAgain), findsOneWidget);

    tester.widget<SnackBarAction>(find.widgetWithText(SnackBarAction, l10n.tryAgain)).onPressed();
    for (var i = 0; i < 200 && shareCalls < 2; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    for (var i = 0; i < 200 && DataExport.exportInProgress.value; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }

    expect(shareCalls, 2);
    expect(sharedPaths.length, 2);
    expect(sharedPaths[0], sharedPaths[1]);
    expect(harness.downloadCalls, 1);
    expect(harness.exportDirCalls, 1);
    expect(harness.deletedDirs, isEmpty);
    expect(harness.exportedCalls, 1);
  });

  testWidgets('unavailable share retains the file and retry shares the same path', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    var shareCalls = 0;
    harness.shareImpl = (params) async {
      shareCalls++;
      if (shareCalls == 1) return const ShareResult('test', ShareResultStatus.unavailable);
      return const ShareResult('test', ShareResultStatus.success);
    };
    harness.downloadImpl = _successDownload;

    await _finishRun(tester, _run(tester, harness));
    expect(find.text(l10n.exportFailedTryAgain), findsOneWidget);

    tester.widget<SnackBarAction>(find.widgetWithText(SnackBarAction, l10n.tryAgain)).onPressed();
    for (var i = 0; i < 200 && shareCalls < 2; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    for (var i = 0; i < 200 && DataExport.exportInProgress.value; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }

    expect(shareCalls, 2);
    expect(harness.downloadCalls, 1);
    expect(harness.exportedCalls, 1);
  });

  testWidgets('dismissed retry share deletes the retained archive', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    harness.exportDirImpl = () async {
      await harness.exportDir.create(recursive: true);
      return harness.exportDir;
    };
    var shareCalls = 0;
    String? sharedPath;
    harness.shareImpl = (params) async {
      shareCalls++;
      sharedPath = params.files!.single.path;
      return shareCalls == 1
          ? const ShareResult('test', ShareResultStatus.unavailable)
          : const ShareResult('test', ShareResultStatus.dismissed);
    };
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) async {
      await File(path).writeAsString('{"ok": true}');
      return path;
    };

    await _finishRun(tester, _run(tester, harness));
    expect(find.text(l10n.exportFailedTryAgain), findsOneWidget);
    expect(File(sharedPath!).existsSync(), isTrue);

    tester.widget<SnackBarAction>(find.widgetWithText(SnackBarAction, l10n.tryAgain)).onPressed();
    for (var i = 0; i < 200 && shareCalls < 2; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    for (var i = 0; i < 200 && DataExport.exportInProgress.value; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }

    expect(shareCalls, 2);
    expect(harness.deletedDirs, [harness.exportDir.path]);
    expect(File(sharedPath!).existsSync(), isFalse);
    expect(harness.exportedCalls, 0);
  });

  testWidgets('changed-session retry does not share and removes the retained file', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    harness.exportDirImpl = () async {
      await harness.exportDir.create(recursive: true);
      return harness.exportDir;
    };
    var shareCalls = 0;
    harness.shareImpl = (params) async {
      shareCalls++;
      if (shareCalls == 1) throw StateError('share sheet failed');
      return const ShareResult('test', ShareResultStatus.success);
    };
    String? retainedPath;
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) async {
      await File(path).create(recursive: true);
      retainedPath = path;
      return path;
    };

    await _finishRun(tester, _run(tester, harness));
    expect(shareCalls, 1);
    expect(find.text(l10n.exportFailedTryAgain), findsOneWidget);
    expect(File(retainedPath!).existsSync(), isTrue);

    harness.switchOwnerTo('owner-2');
    harness.switchOwnerTo('owner-1');
    final retry = tester.widget<SnackBarAction>(find.widgetWithText(SnackBarAction, l10n.tryAgain));
    await tester.runAsync(() async {
      retry.onPressed();
      for (var i = 0; i < 500 && DataExport.exportInProgress.value; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }
    });
    for (var i = 0; i < 200 && DataExport.exportInProgress.value; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    await tester.pump(const Duration(milliseconds: 100));

    expect(shareCalls, 1);
    expect(File(retainedPath!).existsSync(), isFalse);
  });

  testWidgets('truncated 200 body shows retry UI and never shares', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    harness.exportDirImpl = () async {
      await harness.exportDir.create(recursive: true);
      return harness.exportDir;
    };
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) {
      return exportUserDataToFile(
        path,
        abortTrigger: abortTrigger,
        authorizationSnapshot: authorizationSnapshot,
        authService: harness.authService,
        request: () async => http.StreamedResponse(
          Stream.fromIterable([utf8.encode('{"profile": {},')]),
          200,
          headers: {'content-type': 'application/json'},
        ),
      );
    };

    await _finishRun(tester, _run(tester, harness));

    expect(harness.params, isNull);
    expect(harness.exportedCalls, 0);
    expect(find.text(l10n.exportFailedTryAgain), findsOneWidget);
    expect(find.text(l10n.tryAgain), findsOneWidget);
    expect(File('${harness.exportDir.path}/omi-export.json').existsSync(), isFalse);
  });

  testWidgets('stale captured retry never shares a newer export under another session', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    final dirA = harness.exportDir;
    dirA.createSync(recursive: true);
    var sharesA = 0;
    harness.exportDirImpl = () async => dirA;
    harness.shareImpl = (params) async {
      if (params.files!.single.path.startsWith(dirA.path)) {
        sharesA++;
        throw StateError('share failed');
      }
      throw StateError('share failed');
    };
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) async {
      await File(path).create(recursive: true);
      return path;
    };

    await _finishRun(tester, _run(tester, harness));
    expect(find.text(l10n.exportFailedTryAgain), findsOneWidget);
    final pathA = harness.lastPath!;
    final retryA = tester.widget<SnackBarAction>(find.widgetWithText(SnackBarAction, l10n.tryAgain)).onPressed;

    harness.switchOwnerTo('owner-2');
    final dirB = Directory.systemTemp.createTempSync('omi-export-widget-b-');
    addTearDown(() {
      if (dirB.existsSync()) dirB.deleteSync(recursive: true);
    });
    harness.exportDirImpl = () async => dirB;
    await _finishRun(tester, _run(tester, harness));
    final pathB = harness.lastPath!;
    expect(pathB, isNot(pathA));
    expect(find.text(l10n.exportFailedTryAgain), findsOneWidget);
    expect(harness.protectedPathsSeen, isNot(contains(dirA.path)));
    expect(harness.deletedDirs, contains(dirA.path));

    final sharesB = harness.sharedPaths.where((p) => p.startsWith(dirB.path)).length;
    await tester.runAsync(() async {
      retryA.call();
      for (var i = 0; i < 500 && DataExport.exportInProgress.value; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }
    });
    for (var i = 0; i < 200 && DataExport.exportInProgress.value; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    await tester.pump(const Duration(milliseconds: 100));

    expect(harness.sharedPaths.where((p) => p.startsWith(dirB.path)).length, sharesB);
    expect(sharesA, 1);
    expect(File(pathA).existsSync(), isFalse);
    expect(File(pathB).existsSync(), isTrue);
    expect(find.text(l10n.exportFailedTryAgain), findsOneWidget);
  });

  testWidgets('same-session captured retry shares its own retained file, not the newer one', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    final dirA = harness.exportDir;
    dirA.createSync(recursive: true);
    final dirs = <Directory>[dirA, Directory.systemTemp.createTempSync('omi-export-widget-b-')];
    addTearDown(() {
      for (final d in dirs) {
        if (d.existsSync()) d.deleteSync(recursive: true);
      }
    });
    var runIndex = 0;
    harness.exportDirImpl = () async => dirs[runIndex.clamp(0, 1)];
    harness.shareImpl = (params) async => throw StateError('share failed');
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) async {
      await File(path).create(recursive: true);
      return path;
    };

    await _finishRun(tester, _run(tester, harness));
    final pathA = harness.lastPath!;
    final retryA = tester.widget<SnackBarAction>(find.widgetWithText(SnackBarAction, l10n.tryAgain)).onPressed;

    runIndex = 1;
    await _finishRun(tester, _run(tester, harness));
    final pathB = harness.lastPath!;
    expect(pathB, isNot(pathA));

    harness.shareImpl = (params) async => const ShareResult('test', ShareResultStatus.success);
    await tester.runAsync(() async {
      retryA.call();
      for (var i = 0; i < 500 && DataExport.exportInProgress.value; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }
    });
    for (var i = 0; i < 200 && DataExport.exportInProgress.value; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    await tester.pump(const Duration(milliseconds: 100));

    expect(harness.sharedPaths.last, pathA);
    expect(harness.sharedPaths.where((p) => p == pathB).length, 1);
    expect(harness.downloadCalls, 2);
  });

  testWidgets('session churn while the share lease write awaits never shares', (tester) async {
    await _pumpApp(tester);
    final leaseGate = Completer<void>();
    var leaseCalls = 0;
    harness.shareLeaseImpl = (dir) {
      leaseCalls++;
      return leaseGate.future;
    };
    harness.downloadImpl = _successDownload;

    final running = _run(tester, harness);
    for (var i = 0; i < 300 && leaseCalls == 0; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    expect(leaseCalls, 1);
    expect(harness.params, isNull);

    harness.switchOwnerTo('owner-2');
    harness.switchOwnerTo('owner-1');
    leaseGate.complete();
    await _finishRun(tester, running);

    expect(harness.params, isNull);
    expect(harness.exportedCalls, 0);
    expect(harness.deletedDirs, [harness.exportDir.path]);
  });

  testWidgets('run sweeps a stale canonical directory through the default helper', (tester) async {
    await _pumpApp(tester);
    final tempRoot = Directory.systemTemp.createTempSync('omi-export-sweep-root-');
    addTearDown(() {
      if (tempRoot.existsSync()) tempRoot.deleteSync(recursive: true);
    });
    final stale = Directory('${tempRoot.path}/omi-export-3f8b8c4a-1111-4111-8111-abcdefabcdef');
    stale.createSync(recursive: true);
    File('${stale.path}/omi-export.json').writeAsStringSync('{}');
    final staleLease = File('${stale.path}/$exportShareLeaseFileName');
    staleLease.writeAsStringSync('');
    staleLease.setLastModifiedSync(DateTime.now().subtract(const Duration(days: 2)));
    harness.sweepImpl = (protectedPaths) => cleanupStaleExportDirectories(tempRoot, protectedPaths: protectedPaths);
    harness.downloadImpl = _successDownload;

    await _finishRun(tester, _run(tester, harness));

    expect(stale.existsSync(), isFalse);
    expect(harness.exportedCalls, 1);
  });

  testWidgets('captured share retry is a no-op after the settings route unmounts', (tester) async {
    await _pumpApp(tester);
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    harness.exportDirImpl = () async => harness.exportDir;
    harness.shareImpl = (params) async => throw StateError('share failed');
    harness.downloadImpl = _successDownload;

    await _finishRun(tester, _run(tester, harness));
    final retry = tester.widget<SnackBarAction>(find.widgetWithText(SnackBarAction, l10n.tryAgain)).onPressed;

    await tester.pumpWidget(const SizedBox());
    await tester.pump();

    retry();
    for (var i = 0; i < 50; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }

    expect(DataExport.exportInProgress.value, isFalse);
    expect(harness.sharedPaths.length, 1);
    expect(harness.downloadCalls, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a second run during a held share does not sweep, delete, or download', (tester) async {
    await _pumpApp(tester);
    final dirA = harness.exportDir;
    dirA.createSync(recursive: true);
    harness.exportDirImpl = () async => dirA;
    var sweepCalls = 0;
    harness.sweepImpl = (protectedPaths) async {
      sweepCalls++;
      return 0;
    };
    final shareGate = Completer<ShareResult>();
    harness.shareImpl = (params) => shareGate.future;
    harness.downloadImpl = (path, {onProgress, abortTrigger, authorizationSnapshot}) async {
      await File(path).create(recursive: true);
      return path;
    };

    final running = _run(tester, harness);
    for (var i = 0; i < 300 && harness.sharedPaths.isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 20));
      if (i % 5 == 0) {
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
      }
    }
    expect(harness.sharedPaths, isNotEmpty);
    expect(DataExport.exportInProgress.value, isTrue);

    await _run(tester, harness);
    expect(sweepCalls, 1);
    expect(harness.downloadCalls, 1);
    expect(harness.exportDirCalls, 1);
    expect(harness.deletedDirs, isEmpty);
    expect(File(harness.sharedPaths.single).existsSync(), isTrue);

    shareGate.complete(const ShareResult('test', ShareResultStatus.success));
    await _finishRun(tester, running);
    expect(harness.exportedCalls, 1);
  });
}
