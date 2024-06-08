import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/storage/sample.dart';
import 'package:friend_private/pages/speaker_id/tabs/completed.dart';
import 'package:friend_private/pages/speaker_id/tabs/instructions.dart';
import 'package:friend_private/pages/speaker_id/tabs/record_sample.dart';
import 'package:friend_private/utils/ble/connected.dart';

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
    debugPrint('_init _controller.length: ${_controller?.length}');
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
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.surface,
          automaticallyImplyLeading: true,
          title: const Text('Speech Profile'),
          centerTitle: false,
          elevation: 0,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new),
            onPressed: () {
              if (_currentIdx > 0 && _currentIdx < (_controller?.length ?? 0) - 1) {
                showDialog(
                  context: context,
                  builder: (context) => AlertDialog(
                    title: const Text('Are you sure?'),
                    content: const Text('You will lose all the samples you have recorded so far.'),
                    actions: [
                      TextButton(
                        onPressed: () {
                          Navigator.pop(context);
                        },
                        child: const Text('Cancel'),
                      ),
                      TextButton(
                        onPressed: () {
                          Navigator.pop(context);
                          Navigator.pop(context);
                        },
                        child: const Text('Yes'),
                      ),
                    ],
                  ),
                );
                return;
              }
              Navigator.pop(context);
            },
          ),
        ),
        body: _controller == null
            ? const Center(
                child: CircularProgressIndicator(
                  color: Colors.white,
                ),
              )
            : Column(
                children: [
                  Expanded(
                    child: TabBarView(
                      controller: _controller,
                      physics: const NeverScrollableScrollPhysics(),
                      children: [
                        const InstructionsTab(),
                        ...samples.mapIndexed<Widget>((index, sample) => RecordSampleTab(
                              sample: sample,
                              btDevice: _device,
                              sampleIdx: index,
                              totalSamples: samples.length,
                              onRecordCompleted: () {
                                setState(() {
                                  sample.displayNext = true;
                                });
                              },
                            )),
                        const CompletionTab(),
                      ],
                    ),
                  ),
                  _currentIdx == 0 || _currentIdx == _controller!.length - 1 || (samples[_currentIdx - 1].displayNext)
                      ? Padding(
                          padding: const EdgeInsets.symmetric(vertical: 16.0),
                          child: ElevatedButton(
                            onPressed: _controller == null
                                ? null
                                : () async {
                                    debugPrint('Current Index: $_currentIdx');
                                    if (_currentIdx == _controller!.length - 1) {
                                      Navigator.pop(context);
                                      return;
                                    }
                                    _currentIdx += 1;
                                    _controller?.animateTo(_currentIdx);
                                    setState(() {});
                                  },
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.deepPurple,
                              padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(8), // Rounded corners
                              ),
                              textStyle: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            child: Text(
                              _currentIdx == 0
                                  ? 'START'
                                  : _currentIdx == _controller!.length - 1
                                      ? 'Great  :)'
                                      : 'NEXT',
                            ),
                          ),
                        )
                      : const SizedBox.shrink(),
                  const SizedBox(height: 48),
                ],
              ),
      ),
    );
  }
}
