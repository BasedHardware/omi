import 'package:flutter/material.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/firmware_mixin.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Flashes a firmware ZIP the developer picked (Developer Settings → Firmware).
class DeveloperFirmwareFlashPage extends StatefulWidget {
  const DeveloperFirmwareFlashPage(
      {super.key, required this.zipFilePath, required this.fileName, required this.device});

  final String zipFilePath;
  final String fileName;
  final BtDevice device;

  @override
  State<DeveloperFirmwareFlashPage> createState() => _DeveloperFirmwareFlashPageState();
}

class _DeveloperFirmwareFlashPageState extends State<DeveloperFirmwareFlashPage> with FirmwareMixin {
  bool _confirmed = false;
  String? _error;

  @override
  void dispose() {
    killMcuUpdateManager();
    super.dispose();
  }

  Future<void> _startFlash() async {
    setState(() {
      _confirmed = true;
      _error = null;
    });
    try {
      // Manual flash always uses MCU DFU — modern firmware ZIPs contain manifest.json, which
      // NordicDfu (legacy) cannot parse.
      await startMCUDfu(widget.device, zipFilePath: widget.zipFilePath);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final flashing = _confirmed && !isInstalled && _error == null;
    return PopScope(
      // Leaving mid-flash would kill the update manager and can leave the device half-written.
      canPop: !flashing,
      child: Scaffold(
        appBar: AppBar(
          leading: flashing ? const SizedBox.shrink() : const OmiBackButton(),
          title: Text(l10n.flashFirmware),
        ),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(OmiSpacing.xl),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                OmiSettingsGroup(
                  children: [
                    OmiSettingsRow(
                      leading: const Icon(Icons.insert_drive_file_outlined),
                      title: widget.fileName,
                      subtitle: l10n.firmwareFlashTarget(widget.device.name),
                    ),
                  ],
                ),
                const SizedBox(height: OmiSpacing.xl),
                if (!_confirmed) ...[
                  Container(
                    padding: const EdgeInsets.all(OmiSpacing.md),
                    decoration: BoxDecoration(
                      color: OmiColors.warning.withValues(alpha: 0.12),
                      borderRadius: OmiRadius.mdAll,
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(Icons.warning_amber_rounded, color: OmiColors.warning),
                        const SizedBox(width: OmiSpacing.sm),
                        Expanded(
                          child: Text(
                            l10n.customFirmwareWarning,
                            style: OmiType.footnote.copyWith(color: OmiColors.warning),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Spacer(),
                  OmiButton(label: l10n.flashFirmware, onPressed: _startFlash, expand: true),
                ],
                if (_confirmed && !isInstalled) ...[
                  Text(l10n.installingFirmware, style: OmiType.headline),
                  const SizedBox(height: OmiSpacing.md),
                  LinearProgressIndicator(
                    value: installProgress / 100,
                    backgroundColor: OmiColors.surface2,
                    valueColor: const AlwaysStoppedAnimation<Color>(OmiColors.accent),
                    minHeight: 8,
                    borderRadius: OmiRadius.smAll,
                  ),
                  const SizedBox(height: OmiSpacing.xs),
                  Text('$installProgress%', style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                ],
                if (isInstalled)
                  Padding(
                    padding: const EdgeInsets.only(top: OmiSpacing.xxl),
                    child: Column(
                      children: [
                        const Icon(Icons.check_circle, color: OmiColors.success, size: 64),
                        const SizedBox(height: OmiSpacing.md),
                        Text(l10n.firmwareFlashed, style: OmiType.title3),
                        const SizedBox(height: OmiSpacing.xs),
                        Text(l10n.deviceWillRestart, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                      ],
                    ),
                  ),
                if (_error != null) ...[
                  const SizedBox(height: OmiSpacing.md),
                  Container(
                    padding: const EdgeInsets.all(OmiSpacing.sm),
                    decoration: const BoxDecoration(color: OmiColors.dangerSurface, borderRadius: OmiRadius.smAll),
                    child: Text(_error!, style: OmiType.footnote.copyWith(color: OmiColors.danger)),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
