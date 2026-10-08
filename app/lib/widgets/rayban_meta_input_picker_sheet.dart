import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/discovery/rayban_meta_discoverer.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/ui/ui.dart';

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
    this.native = false,
  });

  /// Draws the native presentation, with the classic picker in the shared shell as its fallback.
  /// The same State loads the inputs and owns the connection either way.
  final bool native;

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

  /// A native row tap: the input [uid] it projected must still be in the current list, so a row
  /// from before a reload never connects whatever input took its place.
  Future<void> _connectProjected(String uid) async {
    final input = _inputs.where((input) => input.uid == uid).firstOrNull;
    if (input == null || _isLoading) return;
    await _connect(input);
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
    } catch (_) {
      await preferences.btDeviceSet(previousDevice);
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.native) return _classic(context);
    final l10n = context.l10n;
    return IosNativeSurface(
      title: l10n.rayBanMetaMicPickerTitle,
      loading: _isLoading,
      // Pull to refresh reloads like the classic Try Again; never while a microphone connects.
      onRefresh: _connectingUid == null && !_isLoading ? (_) => _loadInputs() : null,
      fallback: OmiSheetScaffold(title: l10n.rayBanMetaMicPickerTitle, child: _classic(context)),
      toolbar: [
        NativeRow('rayban_input_close', l10n.close, symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        NativeSection('rayban_input_description', [
          NativeRow('rayban_input_description_text', l10n.rayBanMetaMicPickerDescription, kind: 'label'),
        ]),
        if (!_isLoading && _inputs.isEmpty)
          NativeSection('rayban_input_empty', [
            NativeRow(
              'rayban_input_empty_text',
              _loadFailed ? l10n.rayBanMetaMicPickerLoadError : l10n.rayBanMetaMicPickerEmpty,
              kind: 'label',
              symbol: 'mic.slash',
            ),
            NativeRow('rayban_input_retry', l10n.tryAgain, symbol: 'arrow.clockwise', action: (_) => _loadInputs()),
          ]),
        if (!_isLoading && _inputs.isNotEmpty)
          NativeSection('rayban_inputs', [
            for (final (index, input) in _inputs.indexed)
              NativeRow(
                'rayban_input:$index',
                input.name.characters.length <= 120 ? input.name : '${input.name.characters.take(119)}…',
                subtitle: _connectingUid == input.uid
                    ? l10n.deviceConnecting
                    : _connectionFailedUid == input.uid
                        ? l10n.rayBanMetaMicPickerConnectError
                        : '',
                symbol: 'headphones',
                enabled: _connectingUid == null,
                action: (_) => _connectProjected(input.uid),
              ),
          ]),
      ],
    );
  }

  Widget _classic(BuildContext context) {
    return ConstrainedBox(
      constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.7),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.xs, 0, OmiSpacing.xs, OmiSpacing.md),
            child: Text(
              context.l10n.rayBanMetaMicPickerDescription,
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
              textAlign: TextAlign.center,
            ),
          ),
          Flexible(child: _buildBody(context)),
        ],
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_isLoading) {
      return const Padding(padding: EdgeInsets.all(40), child: OmiSpinner());
    }

    if (_inputs.isEmpty) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(32, 20, 32, 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ExcludeSemantics(child: Icon(Icons.mic_off_outlined, size: 44, color: OmiColors.textTertiary)),
            const SizedBox(height: OmiSpacing.md),
            Text(
              _loadFailed ? context.l10n.rayBanMetaMicPickerLoadError : context.l10n.rayBanMetaMicPickerEmpty,
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: OmiSpacing.lg),
            OmiButton.secondary(
              key: const Key('rayban_meta_input_retry'),
              label: context.l10n.tryAgain,
              size: OmiButtonSize.compact,
              onPressed: _loadInputs,
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
              color: OmiColors.surface2,
              borderRadius: OmiRadius.lgAll,
              child: ListTile(
                key: Key('rayban_meta_input_${input.uid}'),
                enabled: _connectingUid == null,
                onTap: () => _connect(input),
                contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
                leading: Icon(Icons.bluetooth_audio, color: OmiColors.textPrimary),
                title: Text(input.name, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
                trailing: isConnecting
                    ? const OmiSpinner(size: OmiSpinnerSize.small)
                    : Icon(Icons.chevron_right, color: OmiColors.textTertiary),
              ),
            ),
            if (failed) ...[
              const SizedBox(height: 8),
              Text(
                context.l10n.rayBanMetaMicPickerConnectError,
                style: OmiType.footnote.copyWith(color: OmiColors.danger),
                textAlign: TextAlign.center,
              ),
            ],
          ],
        );
      },
    );
  }
}
