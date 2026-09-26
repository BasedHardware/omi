import 'dart:io';

import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/services/services.dart';
import 'package:omi/ui/feedback/omi_dialogs.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

/// Presents a single recovery prompt for a blocked BLE operation. Providers and
/// transports publish state only; this widget owns BuildContext and dialogs.
class BluetoothGuidanceListener extends StatefulWidget {
  final Widget child;
  final BluetoothReadiness readiness;
  final GlobalKey<NavigatorState> navigatorKey;
  final bool isAndroid;
  final Future<void> Function(BluetoothUse use)? retryBlockedOperation;

  /// Queue the prompt joins. Defaults to [PromptQueue.instance] when [navigatorKey] is the app's.
  final PromptQueue? promptQueue;

  BluetoothGuidanceListener({
    super.key,
    required this.child,
    BluetoothReadiness? readiness,
    GlobalKey<NavigatorState>? navigatorKey,
    bool? isAndroid,
    this.retryBlockedOperation,
    this.promptQueue,
  })  : readiness = readiness ?? BluetoothReadiness.instance,
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

  /// The app-wide prompt queue when this listener drives the app's navigator; otherwise (tests, an
  /// embedded navigator) a queue of its own that presents on [BluetoothGuidanceListener.navigatorKey].
  PromptQueue get _queue {
    final injected = widget.promptQueue;
    if (injected != null) return injected;
    if (identical(widget.navigatorKey, globalNavigatorKey) && globalNavigatorKey.currentState != null) {
      return PromptQueue.instance;
    }
    return _localQueue ??=
        PromptQueue(contextProvider: () => widget.navigatorKey.currentContext ?? (mounted ? context : null));
  }

  PromptQueue? _localQueue;

  void _schedulePresentation() {
    final readiness = widget.readiness;
    final guidance = readiness.guidance;
    if (!mounted || _requestingEnable || guidance == null || guidance.id == _presentedGuidanceId) return;
    _presentedGuidanceId = guidance.id;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || readiness != widget.readiness) return;
      // One modal at a time with the other startup prompts (docs/ux-contract.md §14).
      _queue.enqueue(
        'bluetooth-guidance-${guidance.id}',
        PromptPriority.high,
        show: (promptContext) => _present(readiness, guidance, promptContext),
      );
    });
  }

  Future<void> _present(BluetoothReadiness readiness, BluetoothGuidance guidance, BuildContext promptContext) async {
    // Resolved while it waited in the queue: nothing to ask.
    if (!mounted || readiness != widget.readiness || readiness.guidance?.id != guidance.id) {
      if (_presentedGuidanceId == guidance.id) _presentedGuidanceId = null;
      return;
    }
    var requestedEnable = false;
    final needsPermission = guidance.state == BluetoothAdapterState.unauthorized;
    final canEnableHere = !needsPermission && widget.isAndroid && guidance.state == BluetoothAdapterState.off;
    await showDialog<void>(
      // This listener is mounted from MaterialApp.builder, above the app's navigator; the queue hands
      // over the navigator's context so the prompt can be presented in production and in tests.
      context: promptContext,
      builder: (dialogContext) {
        final l10n = dialogContext.l10n;
        return OmiAlertDialog(
          title: needsPermission ? l10n.permissionsRequired : l10n.enableBluetooth,
          message: needsPermission ? l10n.permissionsRequiredDesc : l10n.bluetoothNeeded,
          actions: [
            if (needsPermission) ...[
              OmiDialogAction(label: l10n.notNow, onPressed: () => Navigator.of(dialogContext).pop()),
              OmiDialogAction(
                label: l10n.openSettings,
                isDefault: true,
                onPressed: () async {
                  Navigator.of(dialogContext).pop();
                  try {
                    await openAppSettings();
                  } catch (error, stackTrace) {
                    Logger.warning('Could not open Bluetooth permission Settings: $error');
                    Logger.debug('$stackTrace');
                  }
                },
              ),
            ] else if (canEnableHere) ...[
              OmiDialogAction(label: l10n.notNow, onPressed: () => Navigator.of(dialogContext).pop()),
              OmiDialogAction(
                label: l10n.enableBluetooth,
                isDefault: true,
                onPressed: () async {
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
              ),
            ] else
              // iOS (or a state the app cannot fix): the reader turns Bluetooth on in Control Center.
              OmiDialogAction(label: l10n.ok, isDefault: true, onPressed: () => Navigator.of(dialogContext).pop()),
          ],
        );
      },
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
