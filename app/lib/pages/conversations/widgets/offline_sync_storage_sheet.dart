import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/wals/storage_clear.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Opens Manage Storage the way Settings opens: grouped cards on the page
/// surface, so row subtitles keep their contrast.
Future<void> showOfflineSyncStorageSheet({required BuildContext context, required WidgetBuilder builder}) {
  return showOmiSurfaceSheet<void>(
    context: context,
    surface: () => OmiColors.surface0,
    builder: (sheetContext) => OmiSheetScaffold(
      title: sheetContext.l10n.manageStorage,
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xl),
      child: Builder(builder: builder),
    ),
  );
}

/// Manage Storage: how much audio the phone and the pendant hold, by whether it
/// can be removed safely. Amounts are hours of audio, never file counts: each
/// file is about a minute, so a count of 26,589 read as conversations.
class OfflineSyncStorageSheet extends StatelessWidget {
  final StorageAmounts amounts;
  final VoidCallback onFreeUpSpace;
  final VoidCallback onDeletePending;
  final VoidCallback onDeleteAll;

  /// An extra row for the uploaded-audio group (Auto-Remove), drawn under its
  /// action. It must paint no background of its own, like an [OmiSettingsRow].
  final Widget? footer;

  const OfflineSyncStorageSheet({
    super.key,
    required this.amounts,
    required this.onFreeUpSpace,
    required this.onDeletePending,
    required this.onDeleteAll,
    this.footer,
  });

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final hasPending = amounts.pendingCount > 0;
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          OmiSettingsGroup(children: [
            OmiSettingsRow(
              leading: FaIcon(FontAwesomeIcons.circleCheck, color: OmiColors.success),
              title: l.storageUploadedTitle,
              subtitle: l.storageUploadedSubtitle,
              trailing: _Hours(OmiDuration.compact(amounts.uploadedSeconds, l)),
            ),
            if (amounts.uploadedCount > 0)
              OmiSettingsRow(
                leading: const Icon(Icons.cleaning_services_outlined),
                title: l.storageFreeUpSpace,
                onTap: onFreeUpSpace,
                showChevron: false,
              ),
            if (footer != null) footer!,
          ]),
          const SizedBox(height: OmiSpacing.md),
          OmiSettingsGroup(children: [
            OmiSettingsRow(
              leading: FaIcon(FontAwesomeIcons.clockRotateLeft, color: OmiColors.warning),
              title: l.storageNotUploadedTitle,
              subtitle: hasPending ? storageWhereLine(amounts, l) : null,
              trailing: _Hours(OmiDuration.compact(amounts.pendingSeconds, l)),
            ),
            if (hasPending)
              OmiSettingsRow(
                leading: const Icon(Icons.delete_outline),
                title: l.delete,
                subtitle: l.storageNotUploadedWarning,
                onTap: onDeletePending,
                showChevron: false,
                isDestructive: true,
              ),
          ]),
          if (amounts.allCount > 0) ...[
            const SizedBox(height: OmiSpacing.lg),
            OmiSettingsGroup(children: [
              OmiSettingsRow(
                leading: const Icon(Icons.delete_forever_outlined),
                title: l.storageDeleteEverything,
                onTap: onDeleteAll,
                showChevron: false,
                isDestructive: true,
              ),
            ]),
          ],
        ],
      ),
    );
  }
}

/// Where audio that has not been uploaded is waiting.
String storageWhereLine(StorageAmounts amounts, AppLocalizations l) {
  if (amounts.devicePendingSeconds <= 0) return l.storageOnThisPhone;
  if (amounts.phonePendingSeconds <= 0) return l.storageOnYourOmi;
  return l.storageOnPhoneAndOmi(
    OmiDuration.compact(amounts.phonePendingSeconds, l),
    OmiDuration.compact(amounts.devicePendingSeconds, l),
  );
}

/// The amount a group holds. It is the answer the sheet exists to give, so it
/// reads in primary text rather than the faded settings value style.
class _Hours extends StatelessWidget {
  final String text;

  const _Hours(this.text);

  @override
  Widget build(BuildContext context) => Text(
        text,
        maxLines: 1,
        style: OmiType.body.copyWith(
          color: OmiColors.textPrimary,
          fontWeight: FontWeight.w500,
          fontFeatures: const [FontFeature.tabularFigures()],
        ),
      );
}
