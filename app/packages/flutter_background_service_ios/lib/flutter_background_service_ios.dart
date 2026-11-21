library flutter_background_service_ios;

import 'dart:async';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_background_service_platform_interface/flutter_background_service_platform_interface.dart';

@pragma('vm:entry-point')
Future<void> foregroundEntrypoint(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  final service = IOSServiceInstance._();
  final int handle = int.parse(args.first);
  final callbackHandle = CallbackHandle.fromRawHandle(handle);
  final onStart = PluginUtilities.getCallbackFromHandle(callbackHandle);
  if (onStart != null) {
    onStart(service);
  }
}

@pragma('vm:entry-point')
Future<void> backgroundEntrypoint(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  final service = IOSServiceInstance._();
  final int handle = int.parse(args.first);
  final callbackHandle = CallbackHandle.fromRawHandle(handle);
  final onStart =
      PluginUtilities.getCallbackFromHandle(callbackHandle) as FutureOr<bool> Function(ServiceInstance instance)?;
  if (onStart != null) {
    final result = await onStart(service);
    await service._setBackgroundFetchResult(result);
  }
}

class FlutterBackgroundServiceIOS extends FlutterBackgroundServicePlatform {
  /// Registers this class as the default instance of [FlutterBackgroundServicePlatform].
  static void registerWith() {
    FlutterBackgroundServicePlatform.instance = FlutterBackgroundServiceIOS();
  }

  static const MethodChannel _channel = const MethodChannel(
    'id.flutter/background_service_ios',
    JSONMethodCodec(),
  );

  Future<dynamic> _handle(MethodCall call) async {
    switch (call.method) {
      case "onReceiveData":
        _streamController.sink.add(call.arguments);
        break;
      default:
    }

    return true;
  }

  Future<bool> start() async {
    final result = await _channel.invokeMethod('start');
    return result ?? false;
  }

  Future<bool> configure({
    required IosConfiguration iosConfiguration,
    required AndroidConfiguration androidConfiguration,
  }) async {
    _channel.setMethodCallHandler(_handle);

    final CallbackHandle? foregroundHandle = iosConfiguration.onForeground == null
        ? null
        : PluginUtilities.getCallbackHandle(iosConfiguration.onForeground!);

    final CallbackHandle? backgroundHandle = iosConfiguration.onBackground == null
        ? null
        : PluginUtilities.getCallbackHandle(iosConfiguration.onBackground!);

    final result = await _channel.invokeMethod(
      "configure",
      {
        "background_handle": backgroundHandle?.toRawHandle(),
        "foreground_handle": foregroundHandle?.toRawHandle(),
        "auto_start": iosConfiguration.autoStart,
      },
    );

    return result ?? false;
  }

  Future<bool> isServiceRunning() async {
    var result = await _channel.invokeMethod("isServiceRunning");
    return result ?? false;
  }

  final _streamController = StreamController.broadcast(sync: true);

  void dispose() {
    _streamController.close();
  }

  @override
  void invoke(String method, [Map<String, dynamic>? args]) {
    _channel.invokeMethod("sendData", {
      'method': method,
      'args': args,
    });
  }

  @override
  Stream<Map<String, dynamic>?> on(String method) {
    return _streamController.stream.transform(
      StreamTransformer.fromHandlers(
        handleData: (data, sink) {
          if (data['method'] == method) {
            sink.add(data['args']);
          }
        },
      ),
    );
  }
}

class IOSServiceInstance extends ServiceInstance {
  static const MethodChannel _channel = const MethodChannel(
    'id.flutter/background_service_ios_bg',
    JSONMethodCodec(),
  );

  IOSServiceInstance._() {
    _channel.setMethodCallHandler(_handleMethodCall);
  }

  final _controller = StreamController.broadcast(sync: true);
  Future<void> _handleMethodCall(MethodCall call) async {
    switch (call.method) {
      case "onReceiveData":
        _controller.sink.add(call.arguments);
        break;
      default:
    }
  }

  @override
  void invoke(String method, [Map<String, dynamic>? args]) {
    _channel.invokeMethod('sendData', {
      'method': method,
      'args': args,
    });
  }

  @override
  Future<void> stopSelf() async {
    await _channel.invokeMethod("stopService");
  }

  @override
  Stream<Map<String, dynamic>?> on(String method) {
    return _controller.stream.transform(
      StreamTransformer.fromHandlers(
        handleData: (data, sink) {
          if (data['method'] == method) {
            sink.add(data['args']);
          }
        },
      ),
    );
  }

  Future<void> _setBackgroundFetchResult(bool value) async {
    await _channel.invokeMethod('setBackgroundFetchResult', value);
  }
}
