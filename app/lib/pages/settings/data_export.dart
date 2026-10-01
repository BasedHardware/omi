import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:uuid/uuid.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/backend/preferences.dart';

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

  @visibleForTesting
  static void debugClearRetainedExportDirectory() {
    _lastSharedDirectory = null;
  }

  /// Runs the export. [shareOrigin] anchors the iPad share popover (it must be non-empty there).
  static Future<void> run(
    BuildContext context, {
    Rect? shareOrigin,
    Future<Directory> Function()? exportDirectory,
    Future<void> Function(Directory? directory)? cleanupDirectory,
    Future<String?> Function(
      String filePath, {
      void Function(int bytesReceived)? onProgress,
      Future<void>? abortTrigger,
    })? download,
    Future<ShareResult> Function(ShareParams params)? share,
    String? Function()? ownerId,
    void Function()? onExported,
  }) async {
    if (exportInProgress.value) return;
    exportInProgress.value = true;
    final l10n = context.l10n;
    final exportTitle = l10n.exportAllData;
    final failed = l10n.exportFailedTryAgain;
    final readOwner = ownerId ?? () => SharedPreferencesUtil().uid;
    final ownerAtStart = readOwner();
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

    void reportError() {
      if (context.mounted) {
        OmiFeedback.error(
          context,
          failed,
          actionLabel: l10n.tryAgain,
          onAction: () => run(
            context,
            shareOrigin: shareOrigin,
            exportDirectory: exportDirectory,
            cleanupDirectory: cleanupDirectory,
            download: download,
            share: share,
            ownerId: ownerId,
            onExported: onExported,
          ),
        );
      }
    }

    if (ownerAtStart == null || ownerAtStart.isEmpty) {
      exportInProgress.value = false;
      disposeBytes();
      reportError();
      return;
    }

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
        await Future.wait<dynamic>([
          sheetDone,
          if (routeCompleted != null) routeCompleted,
        ]);
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
    unawaited(sheetDone.then((_) {
      if (!sheetClosed && !downloadDone && !abort.isCompleted) {
        cancelled = true;
        abort.complete();
      }
    }));

    Future<void> cleanup() async {
      final dir = exportDir;
      exportDir = null;
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
      final previousShared = _lastSharedDirectory;
      _lastSharedDirectory = null;
      await (cleanupDirectory ?? _deleteQuietly)(previousShared);
      exportDir =
          exportDirectory != null ? await exportDirectory() : await _newExportDir(await getTemporaryDirectory());
      final filePath = '${exportDir!.path}/omi-export.json';
      final exportedPath = await (download ?? exportUserDataToFile)(
        filePath,
        onProgress: (bytes) {
          if (!bytesDisposed && !cancelled) bytesReceived.value = bytes;
        },
        abortTrigger: abort.future,
      );
      downloadDone = true;
      await closeSheet();

      if (exportedPath == null) {
        await cleanup();
        if (!cancelled) reportError();
        return;
      }

      if (cancelled || !context.mounted || readOwner() != ownerAtStart) {
        if (readOwner() != ownerAtStart) {
          Logger.debug('Export owner changed during download; not sharing');
        }
        await cleanup();
        return;
      }

      ShareResult result;
      try {
        result = await (share ?? SharePlus.instance.share)(
          ShareParams(
            files: [XFile(exportedPath, mimeType: 'application/json')],
            title: exportTitle,
            subject: exportTitle,
            sharePositionOrigin: _sanitizedOrigin(context, shareOrigin),
          ),
        );
      } catch (e) {
        Logger.error('Export share failed: ${e.runtimeType}');
        await cleanup();
        reportError();
        return;
      }

      if (result.status == ShareResultStatus.unavailable) {
        await cleanup();
        reportError();
        return;
      }

      if (result.status == ShareResultStatus.success) {
        (onExported ?? () => PlatformManager.instance.analytics.exportMemories())();
      }
      _lastSharedDirectory = exportDir;
      exportDir = null;
      await cleanup();
    } catch (e) {
      Logger.error('Export failed: ${e.runtimeType}');
      await cleanup();
      await closeSheet();
      if (!cancelled) reportError();
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
        Center(child: OmiButton.secondary(label: l10n.cancel, onPressed: onCancel)),
      ],
    );
  }
}
