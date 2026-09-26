import 'package:flutter/material.dart';

import 'package:omi/services/dev_controls/addressability_catalog.dart';
import 'package:omi/services/devices/device_name_policy.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Dialog that renames the connected Omi. [onRename] performs the BLE write
/// and returns true only when the device confirmed the new name; the dialog
/// pops with `true` on success and stays open (with an error) otherwise.
class RenameDeviceWidget extends StatefulWidget {
  const RenameDeviceWidget({super.key, required this.initialName, required this.onRename});

  final String initialName;
  final Future<bool> Function(String name) onRename;

  @override
  State<RenameDeviceWidget> createState() => _RenameDeviceWidgetState();
}

class _RenameDeviceWidgetState extends State<RenameDeviceWidget> {
  late final TextEditingController _controller;
  String? _errorText;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialName);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  String _describe(DeviceNameError error) {
    switch (error) {
      case DeviceNameError.empty:
        return context.l10n.deviceNameCannotBeEmpty;
      case DeviceNameError.tooLong:
        return context.l10n.deviceNameTooLong(OmiDeviceNamePolicy.maxBytes);
      case DeviceNameError.invalidCharacters:
        return context.l10n.deviceNameInvalidCharacters;
    }
  }

  Future<void> _save() async {
    if (_isSaving) return;

    final name = OmiDeviceNamePolicy.normalize(_controller.text);
    final validationError = OmiDeviceNamePolicy.validate(name);
    if (validationError != null) {
      setState(() => _errorText = _describe(validationError));
      return;
    }

    if (name == widget.initialName) {
      Navigator.of(context).pop(false);
      return;
    }

    setState(() {
      _isSaving = true;
      _errorText = null;
    });

    bool renamed;
    try {
      renamed = await widget.onRename(name);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isSaving = false;
        _errorText = context.l10n.deviceRenameFailed;
      });
      return;
    }
    if (!mounted) return;

    if (renamed) {
      Navigator.of(context).pop(true);
      return;
    }
    setState(() {
      _isSaving = false;
      _errorText = context.l10n.deviceRenameFailed;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: OmiColors.surface1,
      shape: const RoundedRectangleBorder(borderRadius: OmiRadius.lgAll),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(context.l10n.renameDevice, style: OmiType.title3),
            const SizedBox(height: 8),
            Text(
              context.l10n.renameDeviceDescription,
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
            const SizedBox(height: 20),
            Container(
              decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
              child: TextField(
                key: OmiKeys.settingsRenameField,
                controller: _controller,
                autofocus: true,
                enabled: !_isSaving,
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _save(),
                onChanged: (_) {
                  if (_errorText != null) setState(() => _errorText = null);
                },
                style: OmiType.callout,
                decoration: InputDecoration(
                  hintText: context.l10n.deviceName,
                  hintStyle: OmiType.callout.copyWith(color: OmiColors.textTertiary),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: const OutlineInputBorder(
                    borderRadius: OmiRadius.mdAll,
                    borderSide: BorderSide(color: OmiColors.border),
                  ),
                ),
              ),
            ),
            if (_errorText != null) ...[
              const SizedBox(height: 10),
              Text(
                _errorText!,
                key: const Key('rename_device_error'),
                style: OmiType.footnote.copyWith(color: OmiColors.danger),
              ),
            ],
            const SizedBox(height: 24),
            Row(
              children: [
                Expanded(
                  child: OmiButton.secondary(
                    key: OmiKeys.settingsRenameCancel,
                    label: context.l10n.cancel,
                    expand: true,
                    onPressed: _isSaving ? null : () => Navigator.of(context).pop(false),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OmiButton(
                    key: OmiKeys.settingsRenameSave,
                    label: context.l10n.save,
                    expand: true,
                    isLoading: _isSaving,
                    onPressed: _isSaving ? null : _save,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
