import 'package:flutter/material.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:permission_handler/permission_handler.dart';

class LocationPermissionHelper {
  static Future<bool> checkAndRequest(BuildContext context) async {
    var status = await Permission.locationWhenInUse.status;

    if (status.isGranted) {
      return true;
    }

    if (status.isDenied) {
      status = await Permission.locationWhenInUse.request();
      if (status.isGranted) {
        return true;
      }
    }

    if (status.isPermanentlyDenied || status.isDenied) {
      if (context.mounted) {
        final shouldOpenSettings = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            backgroundColor: const Color(0xFF1C1C1E),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            title: Row(
              children: [
                const Icon(Icons.location_on, size: 24, color: Colors.orange),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(context.l10n.locationPermissionRequired,
                      style: const TextStyle(color: Colors.white, fontSize: 18)),
                ),
              ],
            ),
            content: Text(
              context.l10n.locationPermissionContent,
              style: TextStyle(color: Colors.grey.shade300, fontSize: 14),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: Text(context.l10n.cancel, style: TextStyle(color: Colors.grey.shade500)),
              ),
              TextButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: Text(context.l10n.openSettings,
                    style: const TextStyle(color: Colors.orange, fontWeight: FontWeight.w600)),
              ),
            ],
          ),
        );

        if (shouldOpenSettings == true) {
          await openAppSettings();
        }
      }
      return false;
    }

    return false;
  }
}
