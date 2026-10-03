import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:uuid/uuid.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/pages/settings/data_export_files.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/backend/preferences.dart';

typedef ExportDownload = Future<String?> Function(
  String filePath, {
  void Function(int bytesReceived)? onProgress,
  Future<void>? abortTrigger,
  AuthSessionSnapshot? authorizationSnapshot,
});

typedef ShareLeaseTouch = Future<void> Function(Directory directory);

/// "Export All Data": downloads the account's streaming export to a JSON file
/// under a temporary directory and opens the share sheet.
///
/// Lives in Settings > Data & Privacy (D4); the delete-account flow points people
/// here. [exportInProgress] is true while an export runs, so every row that starts one can show a
/// spinner and ignore repeat taps.
class DataExport {
  DataExport._();

  static final ValueNotifier<bool> exportInProgress = ValueNotifier(false);
  static Directory? _lastSharedDirectory;
  static _RetainedExportShare? _retainedShare;
  static bool _shareInFlight = false;

  @visibleForTesting
  static void debugClearRetainedExportDirectory() {
    _lastSharedDirectory = null;
    _retainedShare = null;
  }

  /// Runs the export. [shareOrigin] anchors the iPad share popover (it must be non-empty there).
  static Future<void> run(
    BuildContext context, {
    Rect? shareOrigin,
    Future<Directory> Function()? exportDirectory,
    Future<void> Function(Directory? directory)? cleanupDirectory,
    ExportDownload? download,
    Future<ShareResult> Function(ShareParams params)? share,
    String? Function()? ownerId,
    void Function()? onExported,
    AuthService? authService,
    StaleExportSweep? sweepStaleExports,
    ShareLeaseTouch? shareLease,
  }) async {
    if (!context.mounted || exportInProgress.value) return;
    exportInProgress.value = true;
    final l10n = context.l10n;
    final exportTitle = l10n.exportAllData;
    final failed = l10n.exportFailedTryAgain;
    final readOwner = ownerId ?? () => SharedPreferencesUtil().uid;
    final service = authService ?? AuthService.instance;
    final ownerAtStart = readOwner();
    final snapshot =
        ownerAtStart == null || ownerAtStart.isEmpty ? null : service.captureSessionSnapshot(expectedUid: ownerAtStart);
    final abort = Completer<void>();
    final bytesReceived = ValueNotifier<int>(0);
    var bytesDisposed = false;
    final sheetReady = Completer<BuildContext>();
    ModalRoute<dynamic>? sheetRoute;
    NavigatorState? sheetNavigator;
    var sheetClosed = false;
    var downloadDone = false;
    var cancelled = false;
    Directory? exportDir;

    void disposeBytes() {
      if (!bytesDisposed) {
        bytesDisposed = true;
        bytesReceived.dispose();
      }
    }

    void reportError({void Function()? retry}) {
      if (context.mounted) {
        OmiFeedback.error(
          context,
          failed,
          actionLabel: l10n.tryAgain,
          onAction: retry ??
              () => run(
                    context,
                    shareOrigin: shareOrigin,
                    exportDirectory: exportDirectory,
                    cleanupDirectory: cleanupDirectory,
                    download: download,
                    share: share,
                    ownerId: ownerId,
                    onExported: onExported,
                    authService: authService,
                    sweepStaleExports: sweepStaleExports,
                    shareLease: shareLease,
                  ),
        );
      }
    }

    if (snapshot == null) {
      exportInProgress.value = false;
      disposeBytes();
      reportError();
      return;
    }

    StreamSubscription<int>? generationWatch;
    generationWatch = service.sessionGenerationEvents.listen((_) {
      if (!service.isSessionSnapshotCurrent(snapshot) && !abort.isCompleted) {
        abort.complete();
      }
    });

    late Future<void> sheetDone;
    Future<void>? closingSheet;
    Future<void> closeCapturedSheet() async {
      if (!sheetClosed) {
        sheetClosed = true;
        final route = sheetRoute;
        if (route != null && route.isActive) {
          if (route.isCurrent) {
            sheetNavigator?.pop();
          } else {
            sheetNavigator?.removeRoute(route);
          }
        }
      }
      try {
        final routeCompleted = sheetRoute?.completed;
        await Future.wait<dynamic>([sheetDone, if (routeCompleted != null) routeCompleted]);
      } catch (_) {}
      disposeBytes();
    }

    Future<void> closeSheet() {
      return closingSheet ??= closeCapturedSheet();
    }

    sheetDone = showOmiSheet<void>(
      context: context,
      title: exportTitle,
      builder: (ctx) {
        if (!sheetReady.isCompleted) sheetReady.complete(ctx);
        sheetRoute ??= ModalRoute.of(ctx);
        sheetNavigator ??= Navigator.of(ctx);
        return _ExportProgressContent(
          bytesReceived: bytesReceived,
          onCancel: () {
            cancelled = true;
            if (!abort.isCompleted) abort.complete();
            unawaited(closeSheet());
          },
        );
      },
    );
    unawaited(
      sheetDone.then((_) {
        if (!sheetClosed && !downloadDone && !abort.isCompleted) {
          cancelled = true;
          abort.complete();
        }
      }),
    );

    Future<void> cleanup() async {
      final dir = exportDir;
      exportDir = null;
      if (dir != null && _lastSharedDirectory?.path == dir.path) _lastSharedDirectory = null;
      await (cleanupDirectory ?? _deleteQuietly)(dir);
    }

    try {
      await Future.any([sheetReady.future, sheetDone]);
      if (!sheetReady.isCompleted) {
        cancelled = true;
        disposeBytes();
        await cleanup();
        return;
      }
      final retainedShare = _retainedShare;
      var retainedShareNeedsSweepProtection = false;
      if (retainedShare != null) {
        final retainedSessionIsCurrent =
            readOwner() == retainedShare.snapshot.ownerUid && service.isSessionSnapshotCurrent(retainedShare.snapshot);
        if (retainedSessionIsCurrent) {
          retainedShareNeedsSweepProtection = true;
        } else {
          if (identical(_retainedShare, retainedShare)) _retainedShare = null;
          if (_shareInFlight) {
            // An Android receiver may still be reading the file after share() returns.
            retainedShareNeedsSweepProtection = true;
          } else {
            await (cleanupDirectory ?? _deleteQuietly)(retainedShare.directory);
          }
        }
      }
      await sweepStaleExportDirectories(
        sweepStaleExports,
        protectedPaths: {
          if (_lastSharedDirectory != null) _lastSharedDirectory!.path,
          if (retainedShareNeedsSweepProtection) retainedShare!.directory.path,
        },
      );
      exportDir =
          exportDirectory != null ? await exportDirectory() : await _newExportDir(await getTemporaryDirectory());
      final filePath = '${exportDir!.path}/omi-export.json';
      final exportedPath = await (download ?? exportUserDataToFile)(
        filePath,
        onProgress: (bytes) {
          if (!bytesDisposed && !cancelled) bytesReceived.value = bytes;
        },
        abortTrigger: abort.future,
        authorizationSnapshot: snapshot,
      );
      downloadDone = true;
      await closeSheet();

      if (exportedPath == null) {
        await cleanup();
        if (!cancelled) reportError();
        return;
      }

      if (cancelled || !context.mounted || readOwner() != ownerAtStart || !service.isSessionSnapshotCurrent(snapshot)) {
        if (!service.isSessionSnapshotCurrent(snapshot)) {
          Logger.debug('Export session changed during download; not sharing');
        }
        await cleanup();
        return;
      }

      final touchLease = shareLease ?? touchExportShareLease;
      _RetainedExportShare? retained;
      void retainForRetry() {
        retained = _RetainedExportShare(filePath: exportedPath, directory: exportDir!, snapshot: snapshot);
        _retainedShare = retained;
        exportDir = null;
      }

      void reportShareError() => reportError(
            retry: () => _retryShare(
              context,
              retained!,
              shareOrigin: shareOrigin,
              share: share,
              onExported: onExported,
              authService: service,
              exportDirectory: exportDirectory,
              cleanupDirectory: cleanupDirectory,
              download: download,
              ownerId: ownerId,
              sweepStaleExports: sweepStaleExports,
              shareLease: shareLease,
            ),
          );

      ShareResult result;
      try {
        await touchLease(exportDir!);
        if (cancelled || !context.mounted || !service.isSessionSnapshotCurrent(snapshot)) {
          if (!service.isSessionSnapshotCurrent(snapshot)) {
            Logger.debug('Export session changed before share; not sharing');
          }
          await cleanup();
          return;
        }
        _shareInFlight = true;
        try {
          result = await (share ?? SharePlus.instance.share)(
            ShareParams(
              files: [XFile(exportedPath, mimeType: 'application/json')],
              title: exportTitle,
              subject: exportTitle,
              sharePositionOrigin: _sanitizedOrigin(context, shareOrigin),
            ),
          );
        } finally {
          _shareInFlight = false;
        }
        await touchLease(exportDir!);
      } catch (e) {
        Logger.error('Export share failed: ${e.runtimeType}');
        retainForRetry();
        reportShareError();
        return;
      }

      if (result.status == ShareResultStatus.unavailable) {
        retainForRetry();
        reportShareError();
        return;
      }

      if (result.status == ShareResultStatus.success) {
        (onExported ?? () => PlatformManager.instance.analytics.exportMemories())();
        _lastSharedDirectory = exportDir;
        exportDir = null;
      } else {
        // A dismissed sheet did not hand the file to a receiver, so it can be removed.
        await cleanup();
      }
    } catch (e) {
      Logger.error('Export failed: ${e.runtimeType}');
      await cleanup();
      await closeSheet();
      if (!cancelled) reportError();
    } finally {
      await generationWatch.cancel();
      exportInProgress.value = false;
    }
  }

  static Future<void> _retryShare(
    BuildContext context,
    _RetainedExportShare retained, {
    Rect? shareOrigin,
    required Future<ShareResult> Function(ShareParams params)? share,
    required void Function()? onExported,
    required AuthService authService,
    required Future<Directory> Function()? exportDirectory,
    required Future<void> Function(Directory? directory)? cleanupDirectory,
    required ExportDownload? download,
    required String? Function()? ownerId,
    required StaleExportSweep? sweepStaleExports,
    required ShareLeaseTouch? shareLease,
  }) async {
    if (!context.mounted || exportInProgress.value) return;
    exportInProgress.value = true;
    try {
      final l10n = context.l10n;
      final touchLease = shareLease ?? touchExportShareLease;

      void showRetryError(void Function() onAction) {
        if (!context.mounted) return;
        OmiFeedback.error(context, l10n.exportFailedTryAgain, actionLabel: l10n.tryAgain, onAction: onAction);
      }

      void reportRetryError() => showRetryError(
            () => _retryShare(
              context,
              retained,
              shareOrigin: shareOrigin,
              share: share,
              onExported: onExported,
              authService: authService,
              exportDirectory: exportDirectory,
              cleanupDirectory: cleanupDirectory,
              download: download,
              ownerId: ownerId,
              sweepStaleExports: sweepStaleExports,
              shareLease: shareLease,
            ),
          );

      void offerFreshExport() => showRetryError(
            () => run(
              context,
              shareOrigin: shareOrigin,
              exportDirectory: exportDirectory,
              cleanupDirectory: cleanupDirectory,
              download: download,
              share: share,
              ownerId: ownerId,
              onExported: onExported,
              authService: authService,
              sweepStaleExports: sweepStaleExports,
              shareLease: shareLease,
            ),
          );

      if (!authService.isSessionSnapshotCurrent(retained.snapshot)) {
        if (identical(_retainedShare, retained)) _retainedShare = null;
        if (!_shareInFlight) {
          await (cleanupDirectory ?? _deleteQuietly)(retained.directory);
        }
        offerFreshExport();
        return;
      }
      if (!context.mounted) return;

      ShareResult result;
      try {
        await touchLease(retained.directory);
        if (!authService.isSessionSnapshotCurrent(retained.snapshot)) {
          if (identical(_retainedShare, retained)) _retainedShare = null;
          if (!_shareInFlight) {
            await (cleanupDirectory ?? _deleteQuietly)(retained.directory);
          }
          offerFreshExport();
          return;
        }
        if (!context.mounted) return;
        _shareInFlight = true;
        try {
          result = await (share ?? SharePlus.instance.share)(
            ShareParams(
              files: [XFile(retained.filePath, mimeType: 'application/json')],
              title: l10n.exportAllData,
              subject: l10n.exportAllData,
              sharePositionOrigin: _sanitizedOrigin(context, shareOrigin),
            ),
          );
        } finally {
          _shareInFlight = false;
        }
        await touchLease(retained.directory);
      } catch (e) {
        Logger.error('Export share retry failed: ${e.runtimeType}');
        reportRetryError();
        return;
      }

      if (result.status == ShareResultStatus.unavailable) {
        reportRetryError();
        return;
      }

      if (result.status == ShareResultStatus.success) {
        (onExported ?? () => PlatformManager.instance.analytics.exportMemories())();
        _lastSharedDirectory = retained.directory;
      } else {
        // A dismissed retry sheet did not hand the retained archive to a
        // receiver, so remove it instead of protecting it as a shared export.
        await (cleanupDirectory ?? _deleteQuietly)(retained.directory);
      }
      if (identical(_retainedShare, retained)) _retainedShare = null;
    } finally {
      exportInProgress.value = false;
    }
  }

  static Future<Directory> _newExportDir(Directory tempRoot) async {
    final dir = Directory('${tempRoot.path}/omi-export-${const Uuid().v4()}');
    await dir.create(recursive: true);
    return dir;
  }

  static Future<void> _deleteQuietly(Directory? directory) async {
    if (directory == null) return;
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } catch (_) {}
  }

  static Rect _sanitizedOrigin(BuildContext context, Rect? shareOrigin) {
    final candidate = shareOrigin ?? _originOf(context);
    if (candidate.isFinite && !candidate.isEmpty) return candidate;
    return const Rect.fromLTWH(0, 0, 100, 100);
  }

  static Rect _originOf(BuildContext context) {
    final box = context.findRenderObject() as RenderBox?;
    if (box != null && box.hasSize && box.size.width > 0 && box.size.height > 0) {
      return box.localToGlobal(Offset.zero) & box.size;
    }
    return const Rect.fromLTWH(0, 0, 100, 100);
  }
}

class _RetainedExportShare {
  const _RetainedExportShare({required this.filePath, required this.directory, required this.snapshot});

  final String filePath;
  final Directory directory;
  final AuthSessionSnapshot snapshot;
}

class _ExportProgressContent extends StatelessWidget {
  const _ExportProgressContent({required this.bytesReceived, required this.onCancel});

  final ValueNotifier<int> bytesReceived;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Center(child: OmiSpinner(label: l10n.exportingAllData)),
        const SizedBox(height: OmiSpacing.sm),
        ValueListenableBuilder<int>(
          valueListenable: bytesReceived,
          builder: (context, bytes, _) => Text(
            '${l10n.downloading} ${WavBytesUtil.formatBytes(bytes)}',
            textAlign: TextAlign.center,
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
          ),
        ),
        const SizedBox(height: OmiSpacing.lg),
        Center(
          child: OmiButton.secondary(label: l10n.cancel, onPressed: onCancel),
        ),
      ],
    );
  }
}
