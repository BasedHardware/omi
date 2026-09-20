import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/devices/stored_device_name.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

class RenameDeviceWidget extends StatefulWidget {
  final String deviceId;
  final String advertisedName;
  final Future<bool> Function(String name)? saveToDevice;

  const RenameDeviceWidget({super.key, required this.deviceId, required this.advertisedName, this.saveToDevice});

  @override
  State<RenameDeviceWidget> createState() => _RenameDeviceWidgetState();
}

class _RenameDeviceWidgetState extends State<RenameDeviceWidget> {
  late TextEditingController nameController;
  bool isSaving = false;
  bool saveFailed = false;

  @override
  void initState() {
    nameController = TextEditingController(text: SharedPreferencesUtil().getDeviceCustomName(widget.deviceId) ?? '');
    super.initState();
  }

  @override
  void dispose() {
    nameController.dispose();
    super.dispose();
  }

  Future<void> _save() => _store(nameController.text);

  Future<void> _reset() => _store('');

  Future<void> _store(String name) async {
    setState(() {
      isSaving = true;
      saveFailed = false;
    });
    try {
      final saveToDevice = widget.saveToDevice;
      if (saveToDevice != null && !await saveToDevice(name.trim())) {
        if (mounted) {
          setState(() {
            isSaving = false;
            saveFailed = true;
          });
        }
        return;
      }
      await SharedPreferencesUtil().setDeviceCustomName(widget.deviceId, name);
    } catch (e) {
      Logger.debug('Error saving device name: $e');
      if (mounted) {
        setState(() {
          isSaving = false;
          saveFailed = true;
        });
      }
      return;
    }
    if (mounted) {
      Navigator.of(context).pop(true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final hasCustomName = SharedPreferencesUtil().getDeviceCustomName(widget.deviceId) != null;
    return PopScope(
      canPop: !isSaving,
      child: Dialog(
        backgroundColor: const Color(0xFF1C1C1E),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                context.l10n.deviceName,
                style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              Text(
                widget.saveToDevice != null
                    ? context.l10n.deviceNameStoredOnDevice
                    : context.l10n.deviceNameStoredOnPhone,
                style: TextStyle(color: Colors.grey.shade500, fontSize: 14),
              ),
              const SizedBox(height: 20),
              Container(
                decoration: BoxDecoration(color: const Color(0xFF2C2C2E), borderRadius: BorderRadius.circular(10)),
                child: TextField(
                  key: const Key('rename_device_field'),
                  controller: nameController,
                  autofocus: true,
                  textInputAction: TextInputAction.done,
                  inputFormatters: [
                    LengthLimitingTextInputFormatter(32),
                    _Utf8ByteLimitFormatter(maxStoredDeviceNameBytes),
                  ],
                  onSubmitted: (_) => isSaving ? null : _save(),
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                  decoration: InputDecoration(
                    hintText: widget.advertisedName,
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
              if (saveFailed) ...[
                const SizedBox(height: 12),
                Text(
                  context.l10n.anErrorOccurredTryAgain,
                  key: const Key('rename_device_error'),
                  style: TextStyle(color: Colors.red.shade300, fontSize: 14),
                ),
              ],
              const SizedBox(height: 24),
              Row(
                children: [
                  Expanded(
                    child: GestureDetector(
                      onTap: isSaving ? null : () => Navigator.of(context).pop(false),
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
                      onTap: isSaving ? null : _save,
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(10)),
                        child: Center(
                          child: isSaving
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.black),
                                )
                              : Text(
                                  context.l10n.save,
                                  style:
                                      const TextStyle(color: Colors.black, fontSize: 16, fontWeight: FontWeight.w600),
                                ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              if (hasCustomName) ...[
                const SizedBox(height: 12),
                Center(
                  child: GestureDetector(
                    key: const Key('rename_device_reset'),
                    onTap: isSaving ? null : _reset,
                    child: Text(
                      context.l10n.resetToDefault,
                      style: TextStyle(color: Colors.grey.shade500, fontSize: 14, decoration: TextDecoration.underline),
                    ),
                  ),
                ),
              ],
            ],
          ),
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
