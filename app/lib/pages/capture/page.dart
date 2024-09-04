import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/geolocation.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/capture/location_service.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:location/location.dart';
import 'package:provider/provider.dart';

import '../../providers/websocket_provider.dart';

class CapturePage extends StatefulWidget {
  const CapturePage({
    super.key,
  });

  @override
  State<CapturePage> createState() => CapturePageState();
}

class CapturePageState extends State<CapturePage> with AutomaticKeepAliveClientMixin, WidgetsBindingObserver {
  @override
  bool get wantKeepAlive => true;

  /// ----

  // List<TranscriptSegment> segments = List.filled(100, '')
  //     .mapIndexed((i, e) => TranscriptSegment(
  //           text:
  //               '''[00:00:00 - 00:02:23] Speaker 0: The tech giants already know these techniques.
  //               My goal is to unlock their secrets for the benefit of businesses who to design and help users develop healthy habits.
  //               To that end, there's so much I wanted to put in this book that just didn't fit. Before you reading, please take a moment to download these
  //               supplementary materials included free with the purchase of this audiobook. Please go to nirandfar.com forward slash hooked.
  //               Near is spelled like my first name, speck, n I r. Andfar.com/hooked. There you will find the hooked model workbook, an ebook of case studies,
  //               and a free email course about product psychology. Also, if you'd like to connect with me, you can reach me through my blog at nirafar.com.
  //               You can schedule office hours to discuss your questions. Look forward to hearing from you as you build habits for good.
  //
  //               Introduction. 79% of smartphone owners check their device within 15 minutes of waking up every morning. Perhaps most startling,
  //               fully 1 third of Americans say they would rather give up sex than lose their cell phones. A 2011 university study suggested people check their
  //               phones 34 times per day. However, industry insiders believe that number is closer to an astounding 150 daily sessions. We are hooked.
  //               It's the poll to visit YouTube, Facebook, or Twitter for just a few minutes only to find yourself still capping and scrolling an hour later.
  //               It's the urge you likely feel throughout your day but hardly notice. Cognitive psychologists define habits as, quote, automatic behaviors triggered
  //               by situational cues. Things we do with little or no conscious thought. The products and services we use habitually alter our everyday behavior.
  //               Just as their designers intended. Our actions have been engineered. How do companies producing little more than bits of code displayed on a screen
  //               seemingly control users' minds? What makes some products so habit forming? Forming habit is imperative for the survival of many products.
  //
  //               As infinite distractions compete for our attention, companies are learning to master novel tactics that stay relevant in users' minds.
  //               Amassing millions of users is no longer good enough. Companies increasingly find that their economic value is a function of the strength of the habits they create.
  //
  //               In order to win the loyalty of their users and create a product that's regularly used, companies must learn not only what compels users to click,
  //               but also what makes them click. Although some companies are just waking up to this new reality, others are already cashing in. By mastering habit
  //               forming product design, companies profiles in this book make their goods indispensable. First to mind wins. Companies that form strong user habits enjoy
  //               several benefits to their bottom line. These companies attach their product to internal triggers. A result, users show up without any external prompting.
  //               Instead of relying on expensive marketing, how did forming companies link their services to users' daily routines and emotions.
  //               A habit is at work when users feel a tad bored and instantly open Twitter. Feel a hang of loneliness, and before rational thought occurs,
  //               they're scrolling through their Facebook feeds.''',
  //           speaker: 'SPEAKER_0${i % 2}',
  //           isUser: false,
  //           start: 0,
  //           end: 10,
  //         ))
  //     .toList();

  setHasTranscripts(bool hasTranscripts) {
    context.read<CaptureProvider>().setHasTranscripts(hasTranscripts);
  }

  void _onReceiveTaskData(dynamic data) {
    if (data is Map<String, dynamic>) {
      if (data.containsKey('latitude') && data.containsKey('longitude')) {
        context.read<CaptureProvider>().setGeolocation(Geolocation(
              latitude: data['latitude'],
              longitude: data['longitude'],
              accuracy: data['accuracy'],
              altitude: data['altitude'],
              time: DateTime.parse(data['time']),
            ));
      } else {
        if (mounted) {
          context.read<CaptureProvider>().setGeolocation(null);
        }
      }
    }
  }

  @override
  void initState() {
    WavBytesUtil.clearTempWavFiles();

    FlutterForegroundTask.addTaskDataCallback(_onReceiveTaskData);
    WidgetsBinding.instance.addObserver(this);
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      await context.read<CaptureProvider>().processCachedTranscript();
      if (context.read<DeviceProvider>().connectedDevice != null) {
        context.read<OnboardingProvider>().stopFindDeviceTimer();
      }
      if (await LocationService().displayPermissionsDialog()) {
        await showDialog(
          context: context,
          builder: (c) => getDialog(
            context,
            () => Navigator.of(context).pop(),
            () async {
              await requestLocationPermission();
              await LocationService().requestBackgroundPermission();
              if (mounted) Navigator.of(context).pop();
            },
            'Enable Location?  🌍',
            'Allow location access to tag your memories. Set to "Always Allow" in Settings',
            singleButton: false,
            okButtonText: 'Continue',
          ),
        );
      }
      final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
      if (!connectivityProvider.isConnected) {
        context.read<CaptureProvider>().cancelMemoryCreationTimer();
      }
    });

    super.initState();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    // context.read<WebSocketProvider>().closeWebSocket();
    super.dispose();
  }

  Future requestLocationPermission() async {
    LocationService locationService = LocationService();
    bool serviceEnabled = await locationService.enableService();
    if (!serviceEnabled) {
      debugPrint('Location service not enabled');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Location services are disabled. Enable them for a better experience.',
              style: TextStyle(color: Colors.white, fontSize: 14),
            ),
          ),
        );
      }
    } else {
      PermissionStatus permissionGranted = await locationService.requestPermission();
      SharedPreferencesUtil().locationEnabled = permissionGranted == PermissionStatus.granted;
      MixpanelManager().setUserProperty('Location Enabled', SharedPreferencesUtil().locationEnabled);
      if (permissionGranted == PermissionStatus.denied) {
        debugPrint('Location permission not granted');
      } else if (permissionGranted == PermissionStatus.deniedForever) {
        debugPrint('Location permission denied forever');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'If you change your mind, you can enable location services in your device settings.',
                style: TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
          );
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Consumer2<CaptureProvider, DeviceProvider>(builder: (context, provider, deviceProvider, child) {
      return MessageListener<CaptureProvider>(
        showInfo: (info) {
          // This probably will never be called because this has been handled even before we start the audio stream. But it's here just in case.
          if (info == 'FIM_CHANGE') {
            showDialog(
              context: context,
              barrierDismissible: false,
              builder: (c) => getDialog(
                context,
                () async {
                  context.read<WebSocketProvider>().closeWebSocket();
                  var connectedDevice = deviceProvider.connectedDevice;
                  var codec = await getAudioCodec(connectedDevice!.id);
                  context.read<CaptureProvider>().resetState(restartBytesProcessing: true);
                  context.read<CaptureProvider>().initiateWebsocket(codec);
                  if (Navigator.canPop(context)) {
                    Navigator.pop(context);
                  }
                },
                () => {},
                'Firmware change detected!',
                'You are currently using a different firmware version than the one you were using before. Please restart the app to apply the changes.',
                singleButton: true,
                okButtonText: 'Restart',
              ),
            );
          }
        },
        showError: (error) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                error,
                style: TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
          );
        },
        child: Stack(
          children: [
            ListView(children: [
              speechProfileWidget(context),
              ...getConnectionStateWidgets(context, provider.hasTranscripts, deviceProvider.connectedDevice,
                  context.read<WebSocketProvider>().wsConnectionState),
              getTranscriptWidget(
                  provider.memoryCreating, provider.segments, provider.photos, deviceProvider.connectedDevice),
              ...connectionStatusWidgets(
                  context, provider.segments, context.read<WebSocketProvider>().wsConnectionState),
              const SizedBox(height: 16)
            ]),
            getPhoneMicRecordingButton(() => _recordingToggled(provider), provider.recordingState),
          ],
        ),
      );
    });
  }

  _recordingToggled(CaptureProvider provider) async {
    var recordingState = provider.recordingState;
    if (recordingState == RecordingState.record) {
      if (Platform.isAndroid) {
        provider.stopStreamRecordingOnAndroid();
      } else {
        provider.stopStreamRecording();
      }
      provider.updateRecordingState(RecordingState.stop);
      context.read<CaptureProvider>().cancelMemoryCreationTimer();
      await context.read<CaptureProvider>().createMemory();
    } else if (recordingState == RecordingState.initialising) {
      debugPrint('initialising, have to wait');
    } else {
      showDialog(
        context: context,
        builder: (c) => getDialog(
          context,
          () => Navigator.pop(context),
          () async {
            provider.updateRecordingState(RecordingState.initialising);
            context.read<WebSocketProvider>().closeWebSocket();
            await provider.initiateWebsocket(BleAudioCodec.pcm16, 16000);
            if (Platform.isAndroid) {
              await provider.streamRecordingOnAndroid();
            } else {
              await provider.startStreamRecording();
            }
            Navigator.pop(context);
          },
          'Limited Capabilities',
          'Recording with your phone microphone has a few limitations, including but not limited to: speaker profiles, background reliability.',
          okButtonText: 'Ok, I understand',
        ),
      );
    }
  }
}
