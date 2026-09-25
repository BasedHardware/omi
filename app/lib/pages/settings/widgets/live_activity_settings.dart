import 'dart:io';

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

class _LiveActivitySettingsState extends State<LiveActivitySettings> {
  static const _channel = MethodChannel(LiveActivityBridge.channelName);
  bool _supported = false;
  bool _saving = false;
  bool _enabled = true;

  @override
  void initState() {
    super.initState();
    _enabled = SharedPreferencesUtil().showCaptureLiveActivity;
    if (Platform.isIOS) _load();
  }

  Future<void> _load() async {
    try {
      final value = await _channel.invokeMapMethod<String, Object?>('availability');
      if (mounted) setState(() => _supported = value?['supported'] == true);
    } on PlatformException {
      // A system presentation is optional on older iOS versions.
    } on MissingPluginException {
      // iOS 15 has no ActivityKit bridge.
    }
  }

  Future<void> _setEnabled(bool value) async {
    setState(() => _saving = true);
    try {
      if (!await SharedPreferencesUtil().setShowCaptureLiveActivity(value)) {
        throw StateError('Preference was not saved');
      }
      if (mounted) setState(() => _enabled = value);
      await _channel.invokeMethod<void>('setEnabled', value);
    } catch (_) {
      if (mounted) OmiFeedback.error(context, context.l10n.somethingWentWrong);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_supported) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.all(OmiSpacing.md),
      child: OmiSettingsGroup(children: [
        OmiSettingsRow.toggle(
          key: const ValueKey('capture_live_activity_toggle'),
          title: context.l10n.showOnLockScreen,
          value: _enabled,
          onChanged: _saving ? null : _setEnabled,
        ),
      ]),
    );
  }
}
