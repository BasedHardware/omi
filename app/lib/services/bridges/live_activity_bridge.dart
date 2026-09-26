import 'package:flutter/services.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/capture_system_surface.dart';
import 'package:uuid/uuid.dart';

class LiveActivityBridge implements CaptureSystemSurfaceSink {
  LiveActivityBridge({MethodChannel? channel, SharedPreferencesUtil? preferences})
      : channel = channel ?? const MethodChannel(channelName),
        preferences = preferences ?? SharedPreferencesUtil();

  static const channelName = 'com.omi.ios/liveActivity';
  static LiveActivityBridge? _current;
  final String _ownerId = const Uuid().v4();
  final MethodChannel channel;
  final SharedPreferencesUtil preferences;

  @override
  Future<void> start(Future<Map<String, Object?>> Function(Map<String, Object?>) action) async {
    _current = this;
    channel.setMethodCallHandler((call) async {
      if (!identical(_current, this)) throw StateError('Capture owner changed');
      if (call.method != 'action' || call.arguments is! Map) throw MissingPluginException();
      return action(Map<String, Object?>.from(call.arguments as Map));
    });
    await channel.invokeMethod<void>('ready', _ownerId);
  }

  @override
  Future<void> publish(Map<String, Object?> snapshot) => channel.invokeMethod<void>('publish', {
        ...snapshot,
        'ownerId': _ownerId,
        'enabled': preferences.showCaptureLiveActivity,
      });

  @override
  Future<void> close() async {
    if (!identical(_current, this)) return;
    _current = null;
    channel.setMethodCallHandler(null);
    await channel.invokeMethod<void>('detach', _ownerId);
  }
}
