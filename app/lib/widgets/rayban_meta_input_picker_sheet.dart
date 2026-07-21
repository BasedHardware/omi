import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/discovery/rayban_meta_discoverer.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

typedef BluetoothHfpInputLoader = Future<List<BluetoothHfpInput>> Function();
typedef RayBanMetaDeviceConnector = Future<void> Function(BtDevice device);

class RayBanMetaInputPickerSheet extends StatefulWidget {
  final VoidCallback onConnected;
  final BluetoothHfpInputLoader? inputLoader;
  final RayBanMetaDeviceConnector? connector;

  const RayBanMetaInputPickerSheet({
    super.key,
    required this.onConnected,
    @visibleForTesting this.inputLoader,
    @visibleForTesting this.connector,
  });

  @override
  State<RayBanMetaInputPickerSheet> createState() => _RayBanMetaInputPickerSheetState();
}

class _RayBanMetaInputPickerSheetState extends State<RayBanMetaInputPickerSheet> {
  List<BluetoothHfpInput> _inputs = const [];
  bool _isLoading = true;
  bool _loadFailed = false;
  String? _connectingUid;
  String? _connectionFailedUid;

  @override
  void initState() {
    super.initState();
    _loadInputs();
  }

  Future<void> _loadInputs() async {
    setState(() {
      _isLoading = true;
      _loadFailed = false;
    });
    try {
      final loader = widget.inputLoader ?? RayBanMetaHostAPI().getBluetoothHfpInputs;
      final inputs = await loader();
      if (!mounted) return;
      setState(() {
        _inputs = inputs;
        _isLoading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _inputs = const [];
        _isLoading = false;
        _loadFailed = true;
      });
    }
  }

  Future<void> _connect(BluetoothHfpInput input) async {
    if (_connectingUid != null) return;
    final device = RayBanMetaDiscoverer.audioOnlyDeviceForInput(input);
    setState(() {
      _connectingUid = input.uid;
      _connectionFailedUid = null;
    });

    try {
      final connector = widget.connector ?? _connectWithDeviceService;
      await connector(device);
      if (!mounted) return;
      setState(() => _connectingUid = null);
      widget.onConnected();
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _connectingUid = null;
        _connectionFailedUid = input.uid;
      });
    }
  }

  Future<void> _connectWithDeviceService(BtDevice device) async {
    final preferences = SharedPreferencesUtil();
    final previousDevice = preferences.btDevice;
    final deviceProvider = context.read<DeviceProvider>();
    final deviceService = ServiceManager.instance().device;

    // DeviceService reconnects undiscovered devices through the persisted
    // BtDevice. Seed the selected UID for that normal path, then roll it back
    // if the user-selected microphone cannot connect.
    await preferences.btDeviceSet(device);
    try {
      final connection = await deviceService.ensureConnection(device.id, force: true);
      if (connection == null || connection.status != DeviceConnectionState.connected) {
        throw StateError('Ray-Ban Meta microphone did not connect');
      }
      await deviceProvider.setConnectedDevice(connection.device);
      deviceProvider.setIsConnected(true);
      preferences.deviceName = connection.device.name;
      PlatformManager.instance.analytics.deviceConnected();
    } catch (_) {
      await preferences.btDeviceSet(previousDevice);
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.8),
      decoration: const BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary,
        borderRadius: BorderRadius.only(topLeft: Radius.circular(24), topRight: Radius.circular(24)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              margin: const EdgeInsets.only(top: 12),
              width: 40,
              height: 4,
              decoration: BoxDecoration(color: ResponsiveHelper.textTertiary, borderRadius: BorderRadius.circular(2)),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 16),
              child: Column(
                children: [
                  Text(
                    context.l10n.rayBanMetaMicPickerTitle,
                    style: const TextStyle(
                      color: ResponsiveHelper.textPrimary,
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 10),
                  Text(
                    context.l10n.rayBanMetaMicPickerDescription,
                    style: const TextStyle(color: ResponsiveHelper.textTertiary, fontSize: 15, height: 1.4),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
            Flexible(child: _buildBody(context)),
          ],
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_isLoading) {
      return const Padding(
        padding: EdgeInsets.all(40),
        child: CircularProgressIndicator(color: Colors.white),
      );
    }

    if (_inputs.isEmpty) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(32, 20, 32, 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.mic_off_outlined, size: 44, color: ResponsiveHelper.textTertiary),
            const SizedBox(height: 16),
            Text(
              _loadFailed ? context.l10n.rayBanMetaMicPickerLoadError : context.l10n.rayBanMetaMicPickerEmpty,
              style: const TextStyle(color: ResponsiveHelper.textSecondary, fontSize: 15, height: 1.4),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            OutlinedButton(
              key: const Key('rayban_meta_input_retry'),
              onPressed: _loadInputs,
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.white,
                side: const BorderSide(color: ResponsiveHelper.textTertiary),
              ),
              child: Text(context.l10n.tryAgain),
            ),
          ],
        ),
      );
    }

    return ListView.separated(
      shrinkWrap: true,
      padding: const EdgeInsets.fromLTRB(20, 4, 20, 28),
      itemCount: _inputs.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (context, index) {
        final input = _inputs[index];
        final isConnecting = _connectingUid == input.uid;
        final failed = _connectionFailedUid == input.uid;
        return Column(
          children: [
            Material(
              color: ResponsiveHelper.backgroundTertiary,
              borderRadius: BorderRadius.circular(16),
              child: ListTile(
                key: Key('rayban_meta_input_${input.uid}'),
                enabled: _connectingUid == null,
                onTap: () => _connect(input),
                contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
                leading: const Icon(Icons.bluetooth_audio, color: Colors.white),
                title: Text(
                  input.name,
                  style: const TextStyle(color: ResponsiveHelper.textPrimary, fontWeight: FontWeight.w600),
                ),
                trailing: isConnecting
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.chevron_right, color: ResponsiveHelper.textTertiary),
              ),
            ),
            if (failed) ...[
              const SizedBox(height: 8),
              Text(
                context.l10n.rayBanMetaMicPickerConnectError,
                style: const TextStyle(color: Colors.redAccent, fontSize: 13),
                textAlign: TextAlign.center,
              ),
            ],
          ],
        );
      },
    );
  }
}
