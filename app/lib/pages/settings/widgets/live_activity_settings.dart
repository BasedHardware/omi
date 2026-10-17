import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/bridges/live_activity_bridge.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The Lock Screen Live Activity choice and its iOS availability. One owner serves both the
/// Flutter row and a native settings projection, so both save and roll back the same way.
class LiveActivitySettingsController extends ChangeNotifier with WidgetsBindingObserver {
  LiveActivitySettingsController() : _enabled = SharedPreferencesUtil().showCaptureLiveActivity {
    WidgetsBinding.instance.addObserver(this);
    if (_isIOS) _load();
  }

  static const _channel = MethodChannel(LiveActivityBridge.channelName);
  bool _supported = false;
  bool _saving = false;
  bool _enabled;
  bool _disposed = false;

  bool get supported => _supported;
  bool get saving => _saving;
  bool get enabled => _enabled;

  bool get _isIOS => defaultTargetPlatform == TargetPlatform.iOS;

  void _update(VoidCallback change) {
    if (_disposed) return;
    change();
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
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
      _update(() => _supported = value?['supported'] == true && value?['authorized'] == true);
    } on PlatformException {
      // A system presentation is optional on older iOS versions.
    } on MissingPluginException {
      // iOS 15 has no ActivityKit bridge.
    }
  }

  /// Saves [value], restoring the previous choice when either write fails. Returns whether it stuck.
  Future<bool> setEnabled(bool value) async {
    final previous = _enabled;
    _update(() => _saving = true);
    try {
      if (!await SharedPreferencesUtil().setShowCaptureLiveActivity(value)) {
        // The cache already holds the rejected value, and the next card update would send it.
        await SharedPreferencesUtil().setShowCaptureLiveActivity(previous);
        throw StateError('Preference was not saved');
      }
      _update(() => _enabled = value);
      try {
        await _channel.invokeMethod<void>('setEnabled', value);
      } catch (_) {
        // The native presentation kept the old choice, so the preference does too.
        await SharedPreferencesUtil().setShowCaptureLiveActivity(previous);
        rethrow;
      }
      return true;
    } catch (_) {
      _update(() => _enabled = previous);
      return false;
    } finally {
      _update(() => _saving = false);
    }
  }
}

class LiveActivitySettings extends StatefulWidget {
  const LiveActivitySettings({super.key, this.controller});

  /// Shared with a native projection of the same page; without one the row owns its controller.
  final LiveActivitySettingsController? controller;

  @override
  State<LiveActivitySettings> createState() => _LiveActivitySettingsState();
}

class _LiveActivitySettingsState extends State<LiveActivitySettings> {
  LiveActivitySettingsController? _owned;

  LiveActivitySettingsController get _controller => widget.controller ?? (_owned ??= LiveActivitySettingsController());

  @override
  void initState() {
    super.initState();
    // Start the availability check with the row, as before the controller existed.
    if (widget.controller == null) _owned = LiveActivitySettingsController();
  }

  @override
  void dispose() {
    _owned?.dispose();
    super.dispose();
  }

  Future<void> _setEnabled(bool value) async {
    if (!await _controller.setEnabled(value) && mounted) {
      OmiFeedback.error(context, context.l10n.somethingWentWrong);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _controller,
      builder: (context, _) {
        final settings = _controller;
        if (!settings.supported) return const SizedBox.shrink();
        return Padding(
          padding: const EdgeInsets.all(OmiSpacing.md),
          child: OmiSettingsGroup(
            children: [
              OmiSettingsRow.toggle(
                key: const ValueKey('capture_live_activity_toggle'),
                title: context.l10n.showOnLockScreen,
                value: settings.enabled,
                onChanged: settings.saving ? null : _setEnabled,
              ),
            ],
          ),
        );
      },
    );
  }
}
