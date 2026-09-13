import 'package:flutter/material.dart';

import 'package:omi/services/devices/device_name_policy.dart';
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

    final renamed = await widget.onRename(name);
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
      backgroundColor: const Color(0xFF1C1C1E),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              context.l10n.renameDevice,
              style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            Text(context.l10n.renameDeviceDescription, style: TextStyle(color: Colors.grey.shade500, fontSize: 14)),
            const SizedBox(height: 20),
            Container(
              decoration: BoxDecoration(color: const Color(0xFF2C2C2E), borderRadius: BorderRadius.circular(10)),
              child: TextField(
                key: const Key('rename_device_field'),
                controller: _controller,
                autofocus: true,
                enabled: !_isSaving,
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _save(),
                onChanged: (_) {
                  if (_errorText != null) setState(() => _errorText = null);
                },
                style: const TextStyle(color: Colors.white, fontSize: 16),
                decoration: InputDecoration(
                  hintText: context.l10n.deviceName,
                  hintStyle: TextStyle(color: Colors.grey.shade600, fontSize: 16),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: const BorderSide(color: Colors.white24, width: 1),
                  ),
                ),
              ),
            ),
            if (_errorText != null) ...[
              const SizedBox(height: 10),
              Text(
                _errorText!,
                key: const Key('rename_device_error'),
                style: const TextStyle(color: Colors.redAccent, fontSize: 13),
              ),
            ],
            const SizedBox(height: 24),
            Row(
              children: [
                Expanded(
                  child: GestureDetector(
                    key: const Key('rename_device_cancel'),
                    onTap: _isSaving ? null : () => Navigator.of(context).pop(false),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      decoration: BoxDecoration(
                        color: const Color(0xFF2A2A2E),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Center(
                        child: Text(
                          context.l10n.cancel,
                          style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: GestureDetector(
                    key: const Key('rename_device_save'),
                    onTap: _save,
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(10)),
                      child: Center(
                        child: _isSaving
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black),
                              )
                            : Text(
                                context.l10n.save,
                                style: const TextStyle(color: Colors.black, fontSize: 16, fontWeight: FontWeight.w600),
                              ),
                      ),
                    ),
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
