import 'dart:io';

import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/dialog.dart';

/// Presents a single recovery prompt for a blocked BLE operation. Providers and
/// transports publish state only; this widget owns BuildContext and dialogs.
class BluetoothGuidanceListener extends StatefulWidget {
  final Widget child;
  final BluetoothReadiness readiness;

  BluetoothGuidanceListener({super.key, required this.child, BluetoothReadiness? readiness})
      : readiness = readiness ?? BluetoothReadiness.instance;

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
    _schedulePresentation();
  }

  @override
  void dispose() {
    widget.readiness.removeListener(_schedulePresentation);
    super.dispose();
  }

  void _schedulePresentation() {
    final guidance = widget.readiness.guidance;
    if (!mounted || _requestingEnable || guidance == null || guidance.id == _presentedGuidanceId) return;
    _presentedGuidanceId = guidance.id;
    WidgetsBinding.instance.addPostFrameCallback((_) => _present(guidance));
  }

  Future<void> _present(BluetoothGuidance guidance) async {
    if (!mounted || widget.readiness.guidance?.id != guidance.id) return;
    var requestedEnable = false;
    final needsPermission = guidance.state == BluetoothAdapterState.unauthorized;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => getDialog(
        dialogContext,
        () async {
          Navigator.of(dialogContext).pop();
          if (needsPermission) await openAppSettings();
        },
        () async {
          requestedEnable = true;
          _requestingEnable = true;
          Navigator.of(dialogContext).pop();
          try {
            if (await widget.readiness.requestEnable(guidance.use)) {
              await _retryBlockedOperation(guidance.use);
            }
          } finally {
            _requestingEnable = false;
            _schedulePresentation();
          }
        },
        needsPermission ? context.l10n.permissionsRequired : context.l10n.enableBluetooth,
        needsPermission ? context.l10n.permissionsRequiredDesc : context.l10n.bluetoothNeeded,
        singleButton: needsPermission || !Platform.isAndroid || guidance.state != BluetoothAdapterState.off,
        okButtonText: needsPermission
            ? context.l10n.openSettings
            : Platform.isAndroid && guidance.state == BluetoothAdapterState.off
                ? context.l10n.enableBluetooth
                : null,
      ),
    );
    if (!requestedEnable && widget.readiness.guidance?.id == guidance.id) {
      widget.readiness.dismissGuidance(guidance.id);
    }
    _presentedGuidanceId = null;
    _schedulePresentation();
  }

  Future<void> _retryBlockedOperation(BluetoothUse use) async {
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
