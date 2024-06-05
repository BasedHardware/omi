import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/structs/b_t_device_struct.dart';
import 'package:friend_private/backend/storage/sample.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/pages/speaker_id/tabs/instructions.dart';
import 'package:friend_private/pages/speaker_id/tabs/record_sample.dart';
import 'package:friend_private/utils/ble/connected.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';

class SpeakerIdPage extends StatefulWidget {
  const SpeakerIdPage({super.key});

  @override
  State<SpeakerIdPage> createState() => _SpeakerIdPageState();
}

class _SpeakerIdPageState extends State<SpeakerIdPage> with TickerProviderStateMixin {
  TabController? _controller;
  int _currentIdx = 0;
  List<SpeakerIdSample> samples = [];

  BTDeviceStruct? _device;
  StreamSubscription<OnConnectionStateChangedEvent>? _connectionStateListener;

  _init() async {
    samples = await getUserSamplesState(SharedPreferencesUtil().uid);
    _controller = TabController(length: 2 + samples.length, vsync: this);
    var btDevice = BluetoothDevice.fromId(SharedPreferencesUtil().deviceId);
    _device = BTDeviceStruct(id: btDevice.remoteId.str, name: btDevice.platformName);
    _initiateConnectionListener();
    setState(() {});
  }

  _initiateConnectionListener() async {
    if (_connectionStateListener != null) return;
    _connectionStateListener = getConnectionStateListener(
        deviceId: _device!.id,
        onDisconnected: () => setState(() => _device = null),
        onConnected: ((d) => setState(() => _device = d)));
  }

  @override
  void initState() {
    _init();
    super.initState();
  }

  @override
  void dispose() {
    _connectionStateListener?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: FlutterFlowTheme.of(context).primary,
        automaticallyImplyLeading: true,
        title: const Text('Speaker ID'),
        centerTitle: false,
        elevation: 2.0,
      ),
      body: Stack(
        children: [
          const BlurBotWidget(),
          _controller == null
              ? const Center(
                  child: CircularProgressIndicator(),
                )
              : Column(
                  children: [
                    Expanded(
                      child: TabBarView(controller: _controller, children: [
                        const InstructionsTab(),
                        ...samples.map<Widget>((sample) => RecordSampleTab(sample: sample, btDevice: _device)),
                        const InstructionsTab()
                      ]),
                    ),
                    TextButton(
                        onPressed: _controller == null
                            ? null
                            : () async {
                                if (_currentIdx == (_controller?.length ?? 0) - 1) return;
                                if (_currentIdx == 0) {
                                  await startSamplesRecording();
                                }
                                _controller?.animateTo(_currentIdx++);
                                _currentIdx += 1;
                              },
                        child: const Text(
                          'Next',
                          style: TextStyle(color: Colors.white, fontSize: 16),
                        )),
                    const SizedBox(height: 32),
                  ],
                )
        ],
      ),
    );
  }

  startSamplesRecording() async {
    _controller?.animateTo(_currentIdx++);
    _currentIdx += 1;
  }
}
