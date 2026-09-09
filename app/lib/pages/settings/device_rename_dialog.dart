import 'package:flutter/material.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Dialog to set a local display name for a paired Omi device.
///
/// The name is stored on-device (SharedPreferences, keyed by device id) and
/// does not change the BLE-advertised name, so device-type detection and scan
/// filtering keep working. Pass an empty name (or save empty input) to clear
/// the custom name and fall back to the advertised one.
class DeviceRenameDialog extends StatefulWidget {
  final String deviceId;
  final String currentName;

  const DeviceRenameDialog({super.key, required this.deviceId, required this.currentName});

  @override
  State<DeviceRenameDialog> createState() => _DeviceRenameDialogState();
}

class _DeviceRenameDialogState extends State<DeviceRenameDialog> {
  late final TextEditingController nameController;

  @override
  void initState() {
    super.initState();
    final custom = SharedPreferencesUtil().deviceCustomName(widget.deviceId);
    nameController = TextEditingController(text: custom.isNotEmpty ? custom : widget.currentName);
  }

  @override
  void dispose() {
    nameController.dispose();
    super.dispose();
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
              context.l10n.deviceRenameTitle,
              style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            Text(
              context.l10n.deviceRenameDescription,
              style: TextStyle(color: Colors.grey.shade500, fontSize: 14),
            ),
            const SizedBox(height: 20),
            Container(
              decoration: BoxDecoration(color: const Color(0xFF2C2C2E), borderRadius: BorderRadius.circular(10)),
              child: TextField(
                controller: nameController,
                autofocus: true,
                maxLength: 32,
                style: const TextStyle(color: Colors.white, fontSize: 16),
                decoration: InputDecoration(
                  counterText: '',
                  hintText: context.l10n.deviceRenameHint,
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
            const SizedBox(height: 24),
            Row(
              children: [
                Expanded(
                  child: GestureDetector(
                    onTap: () => Navigator.of(context).pop(),
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
                    onTap: () {
                      final name = nameController.text.trim();
                      if (name.length < 2) {
                        AppSnackbar.showSnackbarError(context.l10n.deviceRenameTooShort);
                        return;
                      }
                      SharedPreferencesUtil().setDeviceCustomName(widget.deviceId, name);
                      AppSnackbar.showSnackbar(context.l10n.deviceRenameSaved);
                      Navigator.of(context).pop(name);
                    },
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(10)),
                      child: Center(
                        child: Text(
                          context.l10n.save,
                          style: const TextStyle(color: Colors.black, fontSize: 16, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
            if (SharedPreferencesUtil().deviceCustomName(widget.deviceId).isNotEmpty) ...[
              const SizedBox(height: 12),
              Center(
                child: GestureDetector(
                  onTap: () {
                    SharedPreferencesUtil().clearDeviceCustomName(widget.deviceId);
                    AppSnackbar.showSnackbar(context.l10n.deviceRenameReset);
                    Navigator.of(context).pop('');
                  },
                  child: Text(
                    context.l10n.deviceRenameResetAction,
                    style: TextStyle(color: Colors.grey.shade500, fontSize: 14, decoration: TextDecoration.underline),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
