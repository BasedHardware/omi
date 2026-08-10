import 'dart:io';

import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/widgets/dialog.dart';

/// Presents a single recovery prompt for a blocked BLE operation. Providers and
/// transports publish state only; this widget owns BuildContext and dialogs.
class BluetoothGuidanceListener extends StatefulWidget {
  final Widget child;
  final BluetoothReadiness readiness;
  final GlobalKey<NavigatorState> navigatorKey;
  final bool isAndroid;
  final Future<void> Function(BluetoothUse use)? retryBlockedOperation;

  BluetoothGuidanceListener({
    super.key,
    required this.child,
    BluetoothReadiness? readiness,
    GlobalKey<NavigatorState>? navigatorKey,
    bool? isAndroid,
    this.retryBlockedOperation,
  }) : readiness = readiness ?? BluetoothReadiness.instance,
       navigatorKey = navigatorKey ?? globalNavigatorKey,
       isAndroid = isAndroid ?? Platform.isAndroid;

  @override
  State<BluetoothGuidanceListener> createState() => _BluetoothGuidanceListenerState();
}

class _BluetoothGuidanceListenerState extends State<BluetoothGuidanceListener> {
  int? _presentedGuidanceId;
  bool _requestingEnable = false;

  @override
  void initState() {
    super.initState();
    widget.readiness.addListener(_schedulePresentation);
    _schedulePresentation();
  }

  @override
  void didUpdateWidget(covariant BluetoothGuidanceListener oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.readiness == widget.readiness) return;
    oldWidget.readiness.removeListener(_schedulePresentation);
    widget.readiness.addListener(_schedulePresentation);
    _presentedGuidanceId = null;
    _schedulePresentation();
  }

  @override
  void dispose() {
    widget.readiness.removeListener(_schedulePresentation);
    super.dispose();
  }

  void _schedulePresentation() {
    final readiness = widget.readiness;
    final guidance = readiness.guidance;
    if (!mounted || _requestingEnable || guidance == null || guidance.id == _presentedGuidanceId) return;
    _presentedGuidanceId = guidance.id;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || readiness != widget.readiness) return;
      _present(readiness, guidance);
    });
  }

  Future<void> _present(BluetoothReadiness readiness, BluetoothGuidance guidance) async {
    if (!mounted || readiness != widget.readiness || readiness.guidance?.id != guidance.id) return;
    var requestedEnable = false;
    final needsPermission = guidance.state == BluetoothAdapterState.unauthorized;
    await showDialog<void>(
      // This listener is mounted from MaterialApp.builder, above the app's
      // navigator. Always obtain the navigator context from its key so the
      // recovery prompt can be presented in production as well as in tests.
      context: widget.navigatorKey.currentContext ?? context,
      builder: (dialogContext) => getDialog(
        dialogContext,
        () async {
          Navigator.of(dialogContext).pop();
          if (needsPermission) {
            try {
              await openAppSettings();
            } catch (error, stackTrace) {
              Logger.warning('Could not open Bluetooth permission Settings: $error');
              Logger.debug('$stackTrace');
            }
          }
        },
        () async {
          requestedEnable = true;
          _requestingEnable = true;
          Navigator.of(dialogContext).pop();
          try {
            if (await readiness.requestEnable(guidance.use)) {
              await _retryBlockedOperation(guidance.use);
            }
          } catch (error, stackTrace) {
            Logger.warning('Bluetooth recovery retry failed: $error');
            Logger.debug('$stackTrace');
          } finally {
            _requestingEnable = false;
            _schedulePresentation();
          }
        },
        needsPermission ? dialogContext.l10n.permissionsRequired : dialogContext.l10n.enableBluetooth,
        needsPermission ? dialogContext.l10n.permissionsRequiredDesc : dialogContext.l10n.bluetoothNeeded,
        singleButton: needsPermission || !widget.isAndroid || guidance.state != BluetoothAdapterState.off,
        okButtonText: needsPermission
            ? dialogContext.l10n.openSettings
            : widget.isAndroid && guidance.state == BluetoothAdapterState.off
            ? dialogContext.l10n.enableBluetooth
            : null,
      ),
    );
    if (!requestedEnable && readiness == widget.readiness && readiness.guidance?.id == guidance.id) {
      readiness.dismissGuidance(guidance.id);
    }
    _presentedGuidanceId = null;
    _schedulePresentation();
  }

  Future<void> _retryBlockedOperation(BluetoothUse use) async {
    final retry = widget.retryBlockedOperation;
    if (retry != null) {
      await retry(use);
      return;
    }
    final deviceService = ServiceManager.instance().device;
    if (use == BluetoothUse.discovery) {
      await deviceService.discover();
      return;
    }

    final deviceId = SharedPreferencesUtil().btDevice.id;
    if (deviceId.isNotEmpty) {
      await deviceService.ensureConnection(deviceId, force: true);
    }
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
