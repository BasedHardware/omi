import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/devices/add_device_page.dart';
import 'package:omi/pages/devices/devices_page.dart';
import 'package:omi/pages/home/device.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_search_index.dart';

/// Recording from (Rev 3 "WSource"), opened from the device chip on Today: every source that can
/// listen, with its state, one live at a time. Tapping this phone switches to it (a listening
/// wearable asks first, as the capture rules require); tapping the wearable opens its page.
Future<void> showRecordingSourceSheet(BuildContext context) {
  OmiHaptics.selection();
  return showOmiSheet<void>(
    context: context,
    title: context.l10n.recordingFrom,
    builder: (sheetContext) => _RecordingSourceBody(hostContext: context),
  );
}

class _RecordingSourceBody extends StatelessWidget {
  const _RecordingSourceBody({required this.hostContext});

  /// The page that opened the sheet: navigation continues from there once the sheet is closed.
  final BuildContext hostContext;

  void _closeThen(BuildContext sheetContext, void Function(BuildContext host) next) {
    Navigator.pop(sheetContext);
    if (hostContext.mounted) next(hostContext);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final hasPaired = context.select<DeviceProvider, bool>((d) => (d.pairedDevice?.id ?? '').isNotEmpty);
    return Column(
      key: const ValueKey('recording_source_sheet'),
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
          child: OmiBalancedText(l10n.recordingFromSubtitle,
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
        ),
        const SizedBox(height: OmiSpacing.md),
        DeviceSourcesGroup(
          onDeviceTap: () => _closeThen(context, (host) => routeToPage(host, const ConnectedDevice())),
          onUsePhone: () => _closeThen(context, PhoneCapture.start),
        ),
        if (!hasPaired) ...[
          const SizedBox(height: OmiSpacing.sm),
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                key: const ValueKey('recording_source_add_device'),
                leading: const Icon(Icons.add_rounded),
                title: l10n.addADevice,
                onTap: () => _closeThen(context, (host) => routeToPage(host, const AddDevicePage())),
              ),
            ],
          ),
        ],
        const SizedBox(height: OmiSpacing.lg),
        OmiButton.secondary(
          key: const ValueKey('recording_source_manage'),
          label: l10n.manageDevices,
          expand: true,
          onPressed: () =>
              _closeThen(context, (host) => openSettingsDestination(host, SettingsDestination.deviceGroup)),
        ),
        const SizedBox(height: OmiSpacing.md),
      ],
    );
  }
}
