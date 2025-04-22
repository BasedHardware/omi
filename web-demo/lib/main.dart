import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:flutter_sound/flutter_sound.dart';

const String AUDIO_SERVICE_UUID = '0000abcd-0000-1000-8000-00805f9b34fb';
const String AUDIO_CHARACTERISTIC_UUID = '0000dcba-0000-1000-8000-00805f9b34fb';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Omi Flutter Demo',
      home: const MyHomePage(),
    );
  }
}

class MyHomePage extends StatefulWidget {
  const MyHomePage({super.key});

  @override
  State<MyHomePage> createState() => _MyHomePageState();
}

class _MyHomePageState extends State<MyHomePage> {
  final FlutterBluePlus flutterBlue = FlutterBluePlus.instance;
  final FlutterSoundPlayer _player = FlutterSoundPlayer();
  BluetoothDevice? _device;
  BluetoothCharacteristic? _audioChar;
  bool _connecting = false;

  @override
  void initState() {
    super.initState();
    _player.openAudioSession().then((value) {});
  }

  @override
  void dispose() {
    _player.closeAudioSession();
    super.dispose();
  }

  Future<void> _connectAndStream() async {
    setState(() { _connecting = true; });
    await Permission.bluetoothScan.request();
    await Permission.bluetoothConnect.request();
    flutterBlue.startScan(timeout: const Duration(seconds: 5));
    flutterBlue.scanResults.listen((results) async {
      for (var r in results) {
        if (r.device.name.startsWith('Omi')) {
          _device = r.device;
          flutterBlue.stopScan();
          break;
        }
      }
      if (_device != null) {
        try {
          await _device!.connect();
          final services = await _device!.discoverServices();
          for (var service in services) {
            if (service.uuid.toString() == AUDIO_SERVICE_UUID) {
              for (var c in service.characteristics) {
                if (c.uuid.toString() == AUDIO_CHARACTERISTIC_UUID) {
                  _audioChar = c;
                  break;
                }
              }
            }
          }
          if (_audioChar != null) {
            await _audioChar!.setNotifyValue(true);
            _audioChar!.value.listen((data) {
              // Feed raw PCM directly to the player
              _player.feedFromStream(data);
            });
          }
        } catch (e) {
          debugPrint('Connection error: $e');
        }
      }
    });
    setState(() { _connecting = false; });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Omi Flutter Demo')),
      body: Center(
        child: ElevatedButton(
          onPressed: _connecting ? null : _connectAndStream,
          child: Text(_connecting ? 'Connecting...' : 'Connect & Stream'),
        ),
      ),
    );
  }
}
```
