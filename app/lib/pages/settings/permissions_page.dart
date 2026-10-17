import 'dart:io';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';

import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/ui/ui.dart';

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
      PlatformManager.instance.analytics.permissionChanged(permission: name, granted: status.isGranted);
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
      PlatformManager.instance.analytics.permissionChanged(permission: 'bluetooth', granted: _bluetoothGranted);
    }
  }

  Future<void> _handleBackgroundTap() async {
    if (_backgroundGranted) {
      await openAppSettings();
    } else {
      await FlutterForegroundTask.requestIgnoreBatteryOptimization();
      await _checkPermissions();
      PlatformManager.instance.analytics.permissionChanged(permission: 'background', granted: _backgroundGranted);
    }
  }

  Future<void> _handleLocationTap() async {
    if (_locationGranted) {
      await openAppSettings();
    } else {
      if (await Permission.location.serviceStatus.isDisabled) {
        await openAppSettings();
        await _checkPermissions();
        PlatformManager.instance.analytics.permissionChanged(permission: 'location', granted: _locationGranted);
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
      PlatformManager.instance.analytics.permissionChanged(permission: 'location', granted: _locationGranted);
    }
  }

  @override
  Widget build(BuildContext context) {
    final classic = Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.permissions)),
      body: _isLoading
          ? const OmiLoadingState()
          : ListView(
              padding: const EdgeInsets.all(OmiSpacing.md),
              children: [
                OmiSettingsGroup(
                  footer: context.l10n.permissionsPageDescription,
                  children: [
                    _buildPermissionRow(
                      icon: FontAwesomeIcons.solidBell,
                      title: context.l10n.notifications,
                      isGranted: _notificationsGranted,
                      onTap: () =>
                          _handlePermissionTap(Permission.notification, _notificationsGranted, 'notifications'),
                    ),
                    _buildPermissionRow(
                      icon: FontAwesomeIcons.locationArrow,
                      title: context.l10n.location,
                      isGranted: _locationGranted,
                      onTap: _handleLocationTap,
                    ),
                    _buildPermissionRow(
                      icon: FontAwesomeIcons.bluetooth,
                      title: context.l10n.bluetooth,
                      isGranted: _bluetoothGranted,
                      onTap: _handleBluetoothTap,
                    ),
                    _buildPermissionRow(
                      icon: FontAwesomeIcons.microphone,
                      title: context.l10n.microphone,
                      isGranted: _microphoneGranted,
                      onTap: () => _handlePermissionTap(Permission.microphone, _microphoneGranted, 'microphone'),
                    ),
                    if (Platform.isAndroid)
                      _buildPermissionRow(
                        icon: FontAwesomeIcons.batteryFull,
                        title: context.l10n.backgroundActivity,
                        isGranted: _backgroundGranted,
                        onTap: _handleBackgroundTap,
                      ),
                  ],
                ),
              ],
            ),
    );
    final l10n = context.l10n;
    NativeRow permission(String id, String title, bool granted, Future<void> Function() request) => NativeRow(id, title,
        subtitle: granted ? l10n.permissionEnabled : l10n.permissionEnable, action: (_) => request());
    return IosNativeSurface(
        title: l10n.permissions,
        fallback: classic,
        loading: _isLoading,
        onRefresh: (_) => _checkPermissions(),
        toolbar: [
          NativeRow('permissions_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).pop())
        ],
        sections: [
          if (!_isLoading)
            NativeSection(
                'permissions',
                [
                  permission('notifications', l10n.notifications, _notificationsGranted,
                      () => _handlePermissionTap(Permission.notification, _notificationsGranted, 'notifications')),
                  permission('location', l10n.location, _locationGranted, _handleLocationTap),
                  permission('bluetooth', l10n.bluetooth, _bluetoothGranted, _handleBluetoothTap),
                  permission('microphone', l10n.microphone, _microphoneGranted,
                      () => _handlePermissionTap(Permission.microphone, _microphoneGranted, 'microphone')),
                  if (Platform.isAndroid)
                    permission('background', l10n.backgroundActivity, _backgroundGranted, _handleBackgroundTap),
                ],
                footer: l10n.permissionsPageDescription)
        ]);
  }

  Widget _buildPermissionRow({
    required FaIconData icon,
    required String title,
    required bool isGranted,
    required VoidCallback onTap,
  }) {
    return OmiSettingsRow(
      leading: FaIcon(icon),
      title: title,
      onTap: onTap,
      showChevron: true,
      // "Enable" is the call to action, so it reads brighter than the settled "Enabled".
      trailing: Text(
        isGranted ? context.l10n.permissionEnabled : context.l10n.permissionEnable,
        style: OmiType.subhead.copyWith(color: isGranted ? OmiColors.textSecondary : OmiColors.textPrimary),
      ),
    );
  }
}
