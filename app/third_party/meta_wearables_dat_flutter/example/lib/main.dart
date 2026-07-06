// Minimal example for the meta_wearables_dat_flutter plugin. Walks the
// happy-path: request Android permissions, register glasses, request
// camera permission, start a video stream into a Flutter Texture, stop.
//
// For the polished demo (mock devices, photo capture, full UX) see
// `samples/camera_access/` in the repo.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  RegistrationState _registrationState = RegistrationState.unavailable;
  DeviceInfo? _activeDevice;
  StreamSessionState _sessionState = StreamSessionState.stopped;
  VideoStreamSize? _videoSize;
  int? _textureId;
  String? _lastError;

  StreamSubscription<RegistrationState>? _registrationSub;
  StreamSubscription<DeviceInfo?>? _activeDeviceSub;
  StreamSubscription<StreamSessionState>? _sessionStateSub;
  StreamSubscription<VideoStreamSize>? _videoSizeSub;

  // Attached to MaterialApp.scaffoldMessengerKey so async handlers can
  // show snack bars without needing a BuildContext that lives inside the
  // MaterialApp subtree.
  final GlobalKey<ScaffoldMessengerState> _messengerKey = GlobalKey<ScaffoldMessengerState>();

  @override
  void initState() {
    super.initState();
    _registrationSub = MetaWearablesDat.registrationStateStream().listen(
      (s) => setState(() => _registrationState = s),
    );
    _activeDeviceSub = MetaWearablesDat.activeDeviceStream().listen(
      (d) => setState(() => _activeDevice = d),
    );
    _sessionStateSub = MetaWearablesDat.streamSessionStateStream().listen(
      (s) => setState(() => _sessionState = s),
    );
    _videoSizeSub = MetaWearablesDat.videoStreamSizeStream().listen(
      (s) => setState(() => _videoSize = s),
    );
  }

  @override
  void dispose() {
    _registrationSub?.cancel();
    _activeDeviceSub?.cancel();
    _sessionStateSub?.cancel();
    _videoSizeSub?.cancel();
    super.dispose();
  }

  Future<void> _safeCall(
    Future<void> Function() body, {
    required String label,
  }) async {
    try {
      await body();
    } on DatError catch (e) {
      _showError('$label: ${e.code} ${e.message}');
    } on PlatformException catch (e) {
      _showError('$label: ${e.code} ${e.message ?? ''}');
    } catch (e) {
      _showError('$label: $e');
    }
  }

  void _showError(String msg) {
    if (!mounted) return;
    setState(() => _lastError = msg);
    _messengerKey.currentState?.showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _requestAndroidPermissions() => _safeCall(
        () async {
          final granted = await MetaWearablesDat.requestAndroidPermissions();
          _messengerKey.currentState?.showSnackBar(
            SnackBar(content: Text('Android permissions: $granted')),
          );
        },
        label: 'requestAndroidPermissions',
      );

  Future<void> _connectGlasses() => _safeCall(MetaWearablesDat.startRegistration, label: 'startRegistration');

  Future<void> _disconnectGlasses() => _safeCall(
        MetaWearablesDat.startUnregistration,
        label: 'startUnregistration',
      );

  Future<void> _requestCameraPermission() => _safeCall(
        () async {
          final granted = await MetaWearablesDat.requestCameraPermission();
          _messengerKey.currentState?.showSnackBar(
            SnackBar(content: Text('Camera permission: $granted')),
          );
        },
        label: 'requestCameraPermission',
      );

  Future<void> _startStreaming() => _safeCall(
        () async {
          final id = await MetaWearablesDat.startStreamSession();
          setState(() => _textureId = id);
        },
        label: 'startStreamSession',
      );

  Future<void> _stopStreaming() => _safeCall(
        () async {
          await MetaWearablesDat.stopStreamSession();
          setState(() => _textureId = null);
        },
        label: 'stopStreamSession',
      );

  @override
  Widget build(BuildContext context) {
    final registered = _registrationState == RegistrationState.registered;
    final registering = _registrationState == RegistrationState.registering;

    return MaterialApp(
      scaffoldMessengerKey: _messengerKey,
      home: Scaffold(
        appBar: AppBar(title: const Text('meta_wearables_dat_flutter example')),
        body: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Registration: ${_registrationState.name}'),
                Text('Active device: ${_activeDevice?.name ?? 'none'}'),
                Text('Session: ${_sessionState.name}'
                    '${_videoSize != null ? '  ${_videoSize!.width}x${_videoSize!.height}' : ''}'),
                const Divider(height: 32),
                FilledButton(
                  onPressed: _requestAndroidPermissions,
                  child: const Text('Request Android permissions'),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: FilledButton(
                        onPressed: registering || registered ? null : _connectGlasses,
                        child: const Text('Connect glasses'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: OutlinedButton(
                        onPressed: registered ? _disconnectGlasses : null,
                        child: const Text('Disconnect'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                FilledButton.tonal(
                  onPressed: registered ? _requestCameraPermission : null,
                  child: const Text('Request camera permission'),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: FilledButton(
                        onPressed: _textureId == null && registered ? _startStreaming : null,
                        child: const Text('Start streaming'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: OutlinedButton(
                        onPressed: _textureId == null ? null : _stopStreaming,
                        child: const Text('Stop'),
                      ),
                    ),
                  ],
                ),
                if (_textureId != null) ...[
                  const SizedBox(height: 16),
                  AspectRatio(
                    aspectRatio: _videoSize?.aspectRatio ?? 9 / 16,
                    child: Container(
                      color: Colors.black,
                      child: Texture(textureId: _textureId!),
                    ),
                  ),
                ],
                if (_lastError != null) ...[
                  const SizedBox(height: 16),
                  Text(
                    _lastError!,
                    style: const TextStyle(color: Colors.red),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
