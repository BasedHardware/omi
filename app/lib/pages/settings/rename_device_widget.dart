import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/devices/device_custom_names.dart';
import 'package:omi/services/devices/stored_device_name.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

/// Opens the rename sheet for [deviceId]. Resolves `true` when a name was saved or reset.
Future<bool?> showRenameDeviceSheet(
  BuildContext context, {
  required String deviceId,
  required String advertisedName,
  Future<bool> Function(String name)? saveToDevice,
  VoidCallback? onSaved,
}) {
  return showOmiEditSheet<bool>(
    context: context,
    builder: (_) => RenameDeviceWidget(
      deviceId: deviceId,
      advertisedName: advertisedName,
      saveToDevice: saveToDevice,
      onSaved: onSaved,
    ),
  );
}

class RenameDeviceWidget extends StatefulWidget {
  final String deviceId;
  final String advertisedName;
  final Future<bool> Function(String name)? saveToDevice;

  /// Called once the name is stored, even when the sheet was dismissed while the save was in flight.
  final VoidCallback? onSaved;

  const RenameDeviceWidget({
    super.key,
    required this.deviceId,
    required this.advertisedName,
    this.saveToDevice,
    this.onSaved,
  });

  @override
  State<RenameDeviceWidget> createState() => _RenameDeviceWidgetState();
}

class _RenameDeviceWidgetState extends State<RenameDeviceWidget> {
  late final TextEditingController nameController;
  late final String _originalName;
  bool isSaving = false;
  bool saveFailed = false;

  bool get _isDirty => nameController.text.trim() != _originalName;

  @override
  void initState() {
    super.initState();
    _originalName = SharedPreferencesUtil().getDeviceCustomName(widget.deviceId) ?? '';
    nameController = TextEditingController(text: _originalName);
  }

  @override
  void dispose() {
    nameController.dispose();
    super.dispose();
  }

  Future<void> _save() => _store(nameController.text);

  Future<void> _reset() => _store('');

  Future<void> _store(String name) async {
    if (isSaving) return;
    final deviceId = widget.deviceId;
    final saveToDevice = widget.saveToDevice;
    final onSaved = widget.onSaved;
    setState(() {
      isSaving = true;
      saveFailed = false;
    });
    try {
      if (saveToDevice != null && !await saveToDevice(name.trim())) {
        _showFailure();
        return;
      }
      await SharedPreferencesUtil().setDeviceCustomName(deviceId, name);
    } catch (e) {
      Logger.debug('Error saving device name: $e');
      _showFailure();
      return;
    }
    onSaved?.call();
    if (mounted) {
      Navigator.of(context).pop(true);
    }
  }

  void _showFailure() {
    if (!mounted) return;
    setState(() {
      isSaving = false;
      saveFailed = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final hasCustomName = SharedPreferencesUtil().getDeviceCustomName(widget.deviceId) != null;
    return OmiEditSheet(
      title: l10n.deviceName,
      isDirty: _isDirty,
      enabled: !isSaving,
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.saveToDevice != null ? l10n.deviceNameStoredOnDevice : l10n.deviceNameStoredOnPhone,
              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
            ),
            const SizedBox(height: OmiSpacing.sm),
            TextField(
              key: const Key('rename_device_field'),
              controller: nameController,
              enabled: !isSaving,
              autofocus: true,
              textInputAction: TextInputAction.done,
              inputFormatters: [
                LengthLimitingTextInputFormatter(32),
                _Utf8ByteLimitFormatter(maxStoredDeviceNameBytes),
              ],
              onChanged: (_) => setState(() {}),
              onSubmitted: (_) => _save(),
              style: OmiType.body,
              cursorColor: OmiColors.accent,
              decoration: InputDecoration(
                hintText: widget.advertisedName,
                hintStyle: OmiType.body.copyWith(color: OmiColors.textTertiary),
                filled: true,
                fillColor: OmiColors.surface2,
                contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
                border: const OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none),
              ),
            ),
            const SizedBox(height: OmiSpacing.lg),
            if (saveFailed) ...[
              Semantics(
                liveRegion: true,
                child: Text(
                  l10n.anErrorOccurredTryAgain,
                  key: const Key('rename_device_error'),
                  style: OmiType.footnote.copyWith(color: OmiColors.danger),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(height: OmiSpacing.xs),
            ],
            Row(
              children: [
                Expanded(
                  child: OmiButton.secondary(
                    label: l10n.cancel,
                    expand: true,
                    onPressed: isSaving ? null : () => Navigator.of(context).pop(false),
                  ),
                ),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: OmiButton(
                    key: const Key('rename_device_save'),
                    label: l10n.save,
                    expand: true,
                    isLoading: isSaving,
                    onPressed: _save,
                  ),
                ),
              ],
            ),
            if (hasCustomName) ...[
              const SizedBox(height: OmiSpacing.xs),
              OmiButton.tertiary(
                key: const Key('rename_device_reset'),
                label: l10n.resetToDefault,
                expand: true,
                onPressed: isSaving ? null : _reset,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Utf8ByteLimitFormatter extends TextInputFormatter {
  final int maxBytes;

  _Utf8ByteLimitFormatter(this.maxBytes);

  @override
  TextEditingValue formatEditUpdate(TextEditingValue oldValue, TextEditingValue newValue) {
    return utf8.encode(newValue.text).length > maxBytes ? oldValue : newValue;
  }
}
