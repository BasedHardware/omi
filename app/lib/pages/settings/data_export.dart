import 'package:flutter/material.dart';

import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// "Export All Data": writes the account's data to a JSON file and opens the share sheet.
///
/// Lives in Settings > Data & Privacy (D4); the delete-account flow points people
/// here. [exportInProgress] is true while an export runs, so every row that starts one can show a
/// spinner and ignore repeat taps.
class DataExport {
  DataExport._();

  static final ValueNotifier<bool> exportInProgress = ValueNotifier(false);

  /// Runs the export. [shareOrigin] anchors the iPad share popover (it must be non-empty there).
  static Future<void> run(BuildContext context, {Rect? shareOrigin}) async {
    if (exportInProgress.value) return;
    exportInProgress.value = true;
    final l10n = context.l10n;
    final exportTitle = l10n.exportAllData;
    final failed = l10n.exportFailedTryAgain;
    OmiFeedback.progress(context, l10n.exportStartedMayTakeFewSeconds);
    try {
      final directory = await getApplicationDocumentsDirectory();
      final exportedPath = await exportUserDataToFile('${directory.path}/omi-export.json');
      if (!context.mounted) return;
      if (exportedPath == null) {
        OmiFeedback.error(context, failed,
            actionLabel: l10n.tryAgain, onAction: () => run(context, shareOrigin: shareOrigin));
        return;
      }
      OmiFeedback.hide(context);
      final result = await SharePlus.instance.share(
        ShareParams(
          files: [XFile(exportedPath)],
          subject: exportTitle,
          text: exportTitle,
          sharePositionOrigin: shareOrigin ?? _originOf(context),
        ),
      );
      if (result.status == ShareResultStatus.success) Logger.debug('Export shared');
      PlatformManager.instance.analytics.exportMemories();
    } catch (e) {
      Logger.error('Export failed: $e');
      if (context.mounted) OmiFeedback.error(context, failed);
    } finally {
      exportInProgress.value = false;
    }
  }

  static Rect _originOf(BuildContext context) {
    final box = context.findRenderObject() as RenderBox?;
    if (box != null && box.hasSize && box.size.width > 0 && box.size.height > 0) {
      return box.localToGlobal(Offset.zero) & box.size;
    }
    return const Rect.fromLTWH(0, 0, 100, 100);
  }
}
