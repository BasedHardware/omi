import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/bridges/live_activity_bridge.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class LiveActivitySettings extends StatefulWidget {
  const LiveActivitySettings({super.key});
  @override
  State<LiveActivitySettings> createState() => _LiveActivitySettingsState();
}

class _LiveActivitySettingsState extends State<LiveActivitySettings> with WidgetsBindingObserver {
  static const _channel = MethodChannel(LiveActivityBridge.channelName);
  bool _supported = false;
  bool _saving = false;
  bool _enabled = true;

  bool get _isIOS => defaultTargetPlatform == TargetPlatform.iOS;

  @override
  void initState() {
    super.initState();
    _enabled = SharedPreferencesUtil().showCaptureLiveActivity;
    WidgetsBinding.instance.addObserver(this);
    if (_isIOS) _load();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Live Activities can be switched off for Omi in iOS Settings.
    if (state == AppLifecycleState.resumed && _isIOS) _load();
  }

  Future<void> _load() async {
    try {
      final value = await _channel.invokeMapMethod<String, Object?>('availability');
      // While iOS has Live Activities off for Omi, this switch would change nothing.
      if (mounted) setState(() => _supported = value?['supported'] == true && value?['authorized'] == true);
    } on PlatformException {
      // A system presentation is optional on older iOS versions.
    } on MissingPluginException {
      // iOS 15 has no ActivityKit bridge.
    }
  }

  Future<void> _setEnabled(bool value) async {
    final previous = _enabled;
    setState(() => _saving = true);
    try {
      if (!await SharedPreferencesUtil().setShowCaptureLiveActivity(value)) {
        // The cache already holds the rejected value, and the next card update would send it.
        await SharedPreferencesUtil().setShowCaptureLiveActivity(previous);
        throw StateError('Preference was not saved');
      }
      if (mounted) setState(() => _enabled = value);
      try {
        await _channel.invokeMethod<void>('setEnabled', value);
      } catch (_) {
        // The native presentation kept the old choice, so the preference does too.
        await SharedPreferencesUtil().setShowCaptureLiveActivity(previous);
        rethrow;
      }
    } catch (_) {
      if (mounted) {
        setState(() => _enabled = previous);
        OmiFeedback.error(context, context.l10n.somethingWentWrong);
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_supported) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.all(OmiSpacing.md),
      child: OmiSettingsGroup(
        children: [
          OmiSettingsRow.toggle(
            key: const ValueKey('capture_live_activity_toggle'),
            title: context.l10n.showOnLockScreen,
            value: _enabled,
            onChanged: _saving ? null : _setEnabled,
          ),
        ],
      ),
    );
  }
}
