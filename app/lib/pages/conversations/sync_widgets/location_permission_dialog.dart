import 'package:flutter/material.dart';
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
            title: const Row(
              children: [
                Icon(Icons.location_on, size: 24, color: Colors.orange),
                SizedBox(width: 12),
                Expanded(
                  child: Text('Location Permission Required', style: TextStyle(color: Colors.white, fontSize: 18)),
                ),
              ],
            ),
            content: Text(
              'Fast Transfer requires location permission to verify WiFi connection. '
              'Please grant location permission to continue.',
              style: TextStyle(color: Colors.grey.shade300, fontSize: 14),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: Text('Cancel', style: TextStyle(color: Colors.grey.shade500)),
              ),
              TextButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Open Settings', style: TextStyle(color: Colors.orange, fontWeight: FontWeight.w600)),
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
