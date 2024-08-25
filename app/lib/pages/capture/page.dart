import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/capture/location_service.dart';
import 'package:friend_private/pages/capture/logic/openglass_mixin.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/pages/home/page.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/memories/process.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:location/location.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

import 'logic/phone_recorder_mixin.dart';
import 'logic/websocket_mixin.dart';

class CapturePage extends StatefulWidget {
  final Function(ServerMemory) updateMemory;

  const CapturePage({
    super.key,
    required this.updateMemory,
  });

  @override
  State<CapturePage> createState() => CapturePageState();
}

class CapturePageState extends State<CapturePage>
    with AutomaticKeepAliveClientMixin, WidgetsBindingObserver, PhoneRecorderMixin, WebSocketMixin, OpenGlassMixin {
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

  InternetStatus? _internetStatus;

  late StreamSubscription<InternetStatus> _internetListener;
  bool isGlasses = false;
  String conversationId = const Uuid().v4(); // used only for transcript segment plugins

  Future<void> initiateFriendAudioStreaming() async {
    var provider = context.read<DeviceProvider>();
    if (provider.connectedDevice == null) return;
    BleAudioCodec codec = await getAudioCodec(provider.connectedDevice!.id);
    if (SharedPreferencesUtil().deviceCodec != codec) {
      SharedPreferencesUtil().deviceCodec = codec;
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (c) => getDialog(
          context,
          () => routeToPage(context, const HomePageWrapper(), replace: true),
          () => {},
          'Firmware change detected!',
          'You are currently using a different firmware version than the one you were using before. Please restart the app to apply the changes.',
          singleButton: true,
          okButtonText: 'Restart',
        ),
      );
      return;
    }

    await context.read<CaptureProvider>().streamAudioToWs(provider.connectedDevice!.id, codec);
  }

  Future<void> startOpenGlass() async {
    var provider = context.read<DeviceProvider>();
    if (provider.connectedDevice == null) return;
    isGlasses = await hasPhotoStreamingCharacteristic(provider.connectedDevice!.id);
    if (!isGlasses) return;
    await openGlassProcessing(provider.connectedDevice!, (p) => setState(() {}), setHasTranscripts);
    closeWebSocket();
  }

  void resetState({bool restartBytesProcessing = true, BTDeviceStruct? btDevice}) async {
    var provider = context.read<CaptureProvider>();
    // print('inside of resetState');
    // debugPrint('resetState: $restartBytesProcessing');
    // provider.closeBleStream();
    // provider.cancelMemoryCreationTimer();
    // if (!restartBytesProcessing && (provider.segments.isNotEmpty || photos.isNotEmpty)) {
    //   var res = await provider.createMemory(forcedCreation: true);
    //   if (res != null && !res) {
    //     if (mounted) {
    //       ScaffoldMessenger.of(context).showSnackBar(
    //         const SnackBar(
    //           content: Text(
    //             'Memory creation failed. It\' stored locally and will be retried soon.',
    //             style: TextStyle(color: Colors.white, fontSize: 14),
    //           ),
    //         ),
    //       );
    //     }
    //   }
    // }
    // await provider.resetState(restartBytesProcessing: restartBytesProcessing, btDevice: btDevice);
    // if (restartBytesProcessing) {
    startOpenGlass();
    initiateFriendAudioStreaming();
    // }
  }

  void restartWebSocket() {
    var provider = context.read<DeviceProvider>();
    debugPrint('restartWebSocket');
    closeWebSocket();
    context.read<CaptureProvider>().streamAudioToWs(provider.connectedDevice!.id, SharedPreferencesUtil().deviceCodec);
  }

  setHasTranscripts(bool hasTranscripts) {
    context.read<CaptureProvider>().setHasTranscripts(hasTranscripts);
  }

  processCachedTranscript() async {
    // TODO: only applies to friend, not openglass, fix it
    var segments = SharedPreferencesUtil().transcriptSegments;
    if (segments.isEmpty) return;
    processTranscriptContent(
      segments: segments,
      sendMessageToChat: null,
      triggerIntegrations: false,
      language: SharedPreferencesUtil().recordingsLanguage,
    );
    SharedPreferencesUtil().transcriptSegments = [];
    // TODO: include created at and finished at for this cached transcript
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
    startOpenGlass();
    initiateFriendAudioStreaming();
    processCachedTranscript();

    FlutterForegroundTask.addTaskDataCallback(_onReceiveTaskData);
    WidgetsBinding.instance.addObserver(this);
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      await context.read<CaptureProvider>().initiateWebsocket();
      var shouldRestart = context.read<CaptureProvider>().restartAudioProcessing;
      if (shouldRestart) {
        startOpenGlass();
        initiateFriendAudioStreaming();
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
            'Enable Location Services?  🌍',
            'We need your location permissions to add a location tag to your memories. This will help you remember where they happened.\n\nFor location to work in background, you\'ll have to set Location Permission to "Always Allow" in Settings',
            singleButton: false,
            okButtonText: 'Continue',
          ),
        );
      }
    });
    _internetListener = InternetConnection().onStatusChange.listen((InternetStatus status) {
      switch (status) {
        case InternetStatus.connected:
          _internetStatus = InternetStatus.connected;
          break;
        case InternetStatus.disconnected:
          _internetStatus = InternetStatus.disconnected;
          // so if you have a memory in progress, it doesn't get created, and you don't lose the remaining bytes.
          context.read<CaptureProvider>().cancelMemoryCreationTimer();
          break;
      }
    });
    super.initState();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    record.dispose();
    _internetListener.cancel();
    // websocketChannel
    closeWebSocket();

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
        showError: (error) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                error,
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
          );
        },
        showInfo: (info) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                info,
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
          );
        },
        child: Stack(
          children: [
            ListView(children: [
              speechProfileWidget(context, setState, restartWebSocket),
              ...getConnectionStateWidgets(
                  context, provider.hasTranscripts, deviceProvider.connectedDevice, wsConnectionState, _internetStatus),
              getTranscriptWidget(provider.memoryCreating, provider.segments, photos, deviceProvider.connectedDevice),
              ...connectionStatusWidgets(context, provider.segments, wsConnectionState, _internetStatus),
              const SizedBox(height: 16)
            ]),
            getPhoneMicRecordingButton(_recordingToggled, recordingState)
          ],
        ),
      );
    });
  }

  _recordingToggled() async {
    if (recordingState == RecordingState.record) {
      if (Platform.isAndroid) {
        stopStreamRecordingOnAndroid();
      } else {
        await stopStreamRecording(wsConnectionState, websocketChannel);
      }
      setState(() => recordingState = RecordingState.stop);
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
            Navigator.pop(context);
            setState(() => recordingState = RecordingState.initialising);
            closeWebSocket();
            //   await initiateWebsocket(BleAudioCodec.pcm16, 16000);
            if (Platform.isAndroid) {
              await streamRecordingOnAndroid(wsConnectionState, websocketChannel);
            } else {
              await startStreamRecording(wsConnectionState, websocketChannel);
            }
          },
          'Limited Capabilities',
          'Recording with your phone microphone has a few limitations, including but not limited to: speaker profiles, background reliability.',
          okButtonText: 'Ok, I understand',
        ),
      );
    }
  }
}
