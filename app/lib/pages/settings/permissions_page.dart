import 'dart:io';

import 'package:flutter/material.dart';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';

class PermissionsPage extends StatefulWidget {
  const PermissionsPage({super.key});

  @override
  State<PermissionsPage> createState() => _PermissionsPageState();
}

class _PermissionsPageState extends State<PermissionsPage> with WidgetsBindingObserver {
  bool _isLoading = true;
  bool _notificationsGranted = false;
  bool _locationGranted = false;
  bool _microphoneGranted = false;
  bool _bluetoothGranted = false;
  bool _backgroundGranted = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _checkPermissions();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _checkPermissions();
    }
  }

  Future<void> _checkPermissions() async {
    final notifications = await Permission.notification.isGranted;
    final location = await Permission.location.isGranted;
    final microphone = await Permission.microphone.isGranted;
    bool bluetooth;
    if (Platform.isIOS) {
      bluetooth = await Permission.bluetooth.isGranted;
    } else {
      final scan = await Permission.bluetoothScan.isGranted;
      final connect = await Permission.bluetoothConnect.isGranted;
      bluetooth = scan && connect;
    }

    bool background = false;
    if (Platform.isAndroid) {
      background = await FlutterForegroundTask.isIgnoringBatteryOptimizations;
    }

    if (mounted) {
      setState(() {
        _notificationsGranted = notifications;
        _locationGranted = location;
        _microphoneGranted = microphone;
        _bluetoothGranted = bluetooth;
        _backgroundGranted = background;
        _isLoading = false;
      });
    }
  }

  Future<void> _handlePermissionTap(Permission permission, bool isGranted, String name) async {
    if (isGranted) {
      await openAppSettings();
    } else {
      final status = await permission.request();
      if (status.isPermanentlyDenied) {
        await openAppSettings();
      }
      await _checkPermissions();
      MixpanelManager().permissionChanged(permission: name, granted: status.isGranted);
    }
  }

  Future<void> _handleBluetoothTap() async {
    if (_bluetoothGranted) {
      await openAppSettings();
    } else {
      if (Platform.isIOS) {
        final status = await Permission.bluetooth.request();
        if (status.isPermanentlyDenied) {
          await openAppSettings();
        }
      } else {
        final scan = await Permission.bluetoothScan.request();
        final connect = await Permission.bluetoothConnect.request();
        if (scan.isPermanentlyDenied || connect.isPermanentlyDenied) {
          await openAppSettings();
        }
      }
      await _checkPermissions();
      MixpanelManager().permissionChanged(permission: 'bluetooth', granted: _bluetoothGranted);
    }
  }

  Future<void> _handleBackgroundTap() async {
    if (_backgroundGranted) {
      await openAppSettings();
    } else {
      await FlutterForegroundTask.requestIgnoreBatteryOptimization();
      await _checkPermissions();
      MixpanelManager().permissionChanged(permission: 'background', granted: _backgroundGranted);
    }
  }

  Future<void> _handleLocationTap() async {
    if (_locationGranted) {
      await openAppSettings();
    } else {
      if (await Permission.location.serviceStatus.isDisabled) {
        await openAppSettings();
        await _checkPermissions();
        MixpanelManager().permissionChanged(permission: 'location', granted: _locationGranted);
        return;
      }
      final status = await Permission.locationWhenInUse.request();
      if (status.isGranted && Platform.isIOS) {
        // iOS-only: chain Always so background location updates work.
        await Permission.locationAlways.request();
      } else if (status.isPermanentlyDenied) {
        await openAppSettings();
      }
      await _checkPermissions();
      MixpanelManager().permissionChanged(permission: 'location', granted: _locationGranted);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: Text(context.l10n.permissions),
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator(color: Colors.white))
          : SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
                    child: Column(
                      children: [
                        _buildPermissionRow(
                          icon: FontAwesomeIcons.solidBell,
                          title: context.l10n.notifications,
                          isGranted: _notificationsGranted,
                          onTap: () =>
                              _handlePermissionTap(Permission.notification, _notificationsGranted, 'notifications'),
                        ),
                        const Divider(height: 1, color: Color(0xFF3C3C43)),
                        _buildPermissionRow(
                          icon: FontAwesomeIcons.locationArrow,
                          title: context.l10n.location,
                          isGranted: _locationGranted,
                          onTap: _handleLocationTap,
                        ),
                        const Divider(height: 1, color: Color(0xFF3C3C43)),
                        _buildPermissionRow(
                          icon: FontAwesomeIcons.bluetooth,
                          title: context.l10n.bluetooth,
                          isGranted: _bluetoothGranted,
                          onTap: _handleBluetoothTap,
                        ),
                        const Divider(height: 1, color: Color(0xFF3C3C43)),
                        _buildPermissionRow(
                          icon: FontAwesomeIcons.microphone,
                          title: context.l10n.microphone,
                          isGranted: _microphoneGranted,
                          onTap: () => _handlePermissionTap(Permission.microphone, _microphoneGranted, 'microphone'),
                        ),
                        if (Platform.isAndroid) ...[
                          const Divider(height: 1, color: Color(0xFF3C3C43)),
                          _buildPermissionRow(
                            icon: FontAwesomeIcons.batteryFull,
                            title: context.l10n.backgroundActivity,
                            isGranted: _backgroundGranted,
                            onTap: _handleBackgroundTap,
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Text(
                      context.l10n.permissionsPageDescription,
                      style: TextStyle(color: Colors.white.withValues(alpha: 0.5), fontSize: 13),
                    ),
                  ),
                ],
              ),
            ),
    );
  }

  Widget _buildPermissionRow({
    required IconData icon,
    required String title,
    required bool isGranted,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
        child: Row(
          children: [
            SizedBox(width: 24, height: 24, child: FaIcon(icon, color: const Color(0xFF8E8E93), size: 20)),
            const SizedBox(width: 16),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w400),
              ),
            ),
            Text(
              isGranted ? context.l10n.permissionEnabled : context.l10n.permissionEnable,
              style: TextStyle(color: isGranted ? Colors.white.withValues(alpha: 0.5) : Colors.white, fontSize: 15),
            ),
            const SizedBox(width: 4),
            const Icon(Icons.chevron_right, color: Color(0xFF3C3C43), size: 20),
          ],
        ),
      ),
    );
  }
}
