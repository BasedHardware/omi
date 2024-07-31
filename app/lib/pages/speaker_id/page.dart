import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/api_requests/api/server.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/schema/sample.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/pages/speaker_id/tabs/completed.dart';
import 'package:friend_private/pages/speaker_id/tabs/instructions.dart';
import 'package:friend_private/pages/speaker_id/tabs/record_sample.dart';
import 'package:friend_private/utils/ble/connected.dart';
import 'package:friend_private/utils/ble/scan.dart';
import 'package:friend_private/widgets/dialog.dart';

class SpeakerIdPage extends StatefulWidget {
  final bool onbording;

  const SpeakerIdPage({super.key, this.onbording = false});

  @override
  State<SpeakerIdPage> createState() => _SpeakerIdPageState();
}

class _SpeakerIdPageState extends State<SpeakerIdPage> with TickerProviderStateMixin {
  TabController? _controller;
  int _currentIdx = 0;
  List<SpeakerIdSample> _samples = [];

  BTDeviceStruct? _device;
  StreamSubscription<OnConnectionStateChangedEvent>? _connectionStateListener;

  _init() async {
    _device = await getConnectedDevice();
    _device ??= await scanAndConnectDevice(timeout: true);
    _samples = await getUserSamplesState(SharedPreferencesUtil().uid);
    _controller = TabController(length: 2 + _samples.length, vsync: this);
    _initiateConnectionListener();
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) {
      if (_device == null) {
        showDialog(
          context: context,
          barrierDismissible: false,
          builder: (c) => getDialog(
            context,
            () {
              Navigator.of(context).pop();
              Navigator.of(context).pop();
            },
            () => {},
            'Device Disconnected',
            'Please make sure your device is turned on and nearby, and try again.',
            singleButton: true,
          ),
        );
      }
    });
    setState(() {});
  }

  _initiateConnectionListener() async {
    if (_device == null || _connectionStateListener != null) return;
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
      canPop: true,
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.primary,
          automaticallyImplyLeading: true,
          title: const Text(
            'Speech Profile',
            style: TextStyle(color: Colors.white, fontSize: 20),
          ),
          actions: [
            !widget.onbording
                ? const SizedBox()
                : TextButton(
                    onPressed: () {
                      Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (c) => const HomePageWrapper()));
                    },
                    child: const Text(
                      'Skip',
                      style: TextStyle(color: Colors.white, decoration: TextDecoration.underline),
                    ),
                  ),
          ],
          centerTitle: true,
          elevation: 0,
          leading: widget.onbording
              ? const SizedBox()
              : IconButton(
                  icon: const Icon(Icons.arrow_back_ios_new),
                  onPressed: () {
                    if (_currentIdx > 0 && _currentIdx < (_controller?.length ?? 0) - 1) {
                      showDialog(
                        context: context,
                        builder: (context) => getDialog(
                          context,
                          () => Navigator.pop(context),
                          () {
                            Navigator.pop(context);
                            Navigator.pop(context);
                          },
                          'Are you sure?',
                          'You will lose all the samples you have recorded so far.',
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
                        InstructionsTab(
                          goNext: _goNext,
                          deviceFound: _device != null,
                        ),
                        ..._samples.mapIndexed<Widget>((index, sample) => RecordSampleTab(
                              sample: sample,
                              btDevice: _device,
                              sampleIdx: index,
                              totalSamples: _samples.length,
                              goNext: _goNext,
                              onRecordCompleted: () {
                                setState(() {
                                  sample.displayNext = true;
                                });
                              },
                            )),
                        CompletionTab(
                          goNext: _goNext,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),
                ],
              ),
      ),
    );
  }

  _goNext() async {
    if (_currentIdx == _controller!.length - 1) {
      if (widget.onbording) {
        Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (c) => const HomePageWrapper()));
      } else {
        Navigator.pop(context);
      }
      return;
    }
    if (_currentIdx == 0) {
      if (widget.onbording) {
        MixpanelManager().speechProfileStartedOnboarding();
      } else {
        MixpanelManager().speechProfileStarted();
      }
    }
    _currentIdx += 1;
    _controller?.animateTo(_currentIdx);
    setState(() {});
  }
}
