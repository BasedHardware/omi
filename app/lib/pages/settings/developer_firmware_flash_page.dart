import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
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
    final classic = Scaffold(
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
                      Icon(Icons.warning_amber_rounded, color: OmiColors.warning),
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
                  valueColor: AlwaysStoppedAnimation<Color>(OmiColors.accent),
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
                      Icon(Icons.check_circle, color: OmiColors.success, size: 64),
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
                  decoration: BoxDecoration(color: OmiColors.dangerSurface, borderRadius: OmiRadius.smAll),
                  child: Text(_error!, style: OmiType.footnote.copyWith(color: OmiColors.danger)),
                ),
              ],
            ],
          ),
        ),
      ),
    );
    return PopScope(
      // Leaving mid-flash would kill the update manager and can leave the device half-written.
      canPop: !flashing,
      child: !nativePresentationEnabled ? classic : Scaffold(body: _nativeSurface(classic, flashing)),
    );
  }

  /// The same four states natively: ready, flashing, flashed and failed. Only the picked file's display
  /// name crosses; its path stays with this State.
  Widget _nativeSurface(Widget classic, bool flashing) {
    final l10n = context.l10n;
    final progress = installProgress.clamp(0, 100);
    final error = _error;
    return IosNativeSurface(
      title: l10n.flashFirmware,
      fallback: classic,
      toolbar: flashing
          ? const []
          : [
              NativeRow('flash_back', l10n.back,
                  symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
            ],
      sections: [
        NativeSection('flash_file', [
          NativeRow('flash_file_name', widget.fileName,
              kind: 'label', subtitle: l10n.firmwareFlashTarget(widget.device.name), symbol: 'doc.zipper'),
        ]),
        if (!_confirmed)
          NativeSection('flash_ready', [
            NativeRow('flash_warning', l10n.customFirmwareWarning, kind: 'label', symbol: 'exclamationmark.triangle'),
            NativeRow('flash_start', l10n.flashFirmware,
                symbol: 'bolt',
                destructive: true,
                // The flash outlives this command; its progress arrives in later snapshots.
                action: (_) => unawaited(_startFlash())),
          ]),
        if (_confirmed && !isInstalled)
          NativeSection('flash_progress_section', [
            NativeRow('flash_progress', l10n.installingFirmware,
                kind: 'progress', subtitle: '$progress%', value: progress.toDouble(), maximumValue: 100),
          ]),
        if (isInstalled)
          NativeSection('flash_result', [
            NativeRow('flash_success', l10n.firmwareFlashed,
                kind: 'label', subtitle: l10n.deviceWillRestart, symbol: 'checkmark.circle'),
          ]),
        if (error != null)
          NativeSection('flash_error_section', [
            NativeRow('flash_error', _nativeErrorText(error),
                kind: 'label', symbol: 'xmark.octagon', destructive: true),
          ]),
      ],
    );
  }

  /// The classic page's diagnostic, with the picked file's private path reduced to its display name
  /// and bounded so a long stack-like message cannot bloat the snapshot.
  String _nativeErrorText(String error) {
    final text = error.replaceAll(widget.zipFilePath, widget.fileName).characters;
    return text.length <= 500 ? text.toString() : '${text.take(499)}…';
  }
}
