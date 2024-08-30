import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/schema/geolocation.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/capture/location_service.dart';
import 'package:friend_private/pages/capture/logic/openglass_mixin.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:location/location.dart';
import 'package:provider/provider.dart';

import 'package:friend_private/pages/capture/logic/websocket_mixin.dart';

class CaptureWidget extends StatefulWidget {
  const CaptureWidget({
    super.key,
  });

  @override
  State<CaptureWidget> createState() => CaptureWidgetState();
}

class CaptureWidgetState extends State<CaptureWidget>
    with AutomaticKeepAliveClientMixin, WidgetsBindingObserver, WebSocketMixin, OpenGlassMixin {
  @override
  bool get wantKeepAlive => true;

  InternetStatus? _internetStatus;

  late StreamSubscription<InternetStatus> _internetListener;

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
      // Should we start the websocket even if no device is connected? Websocket starts when a device is connected
      // if (context.read<DeviceProvider>().connectedDevice != null) {
      //   await context.read<CaptureProvider>().initiateWebsocket();
      // }

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
    // record.dispose();
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
        showInfo: (info) {
          if (info == 'FIM_CHANGE') {
            showDialog(
              context: context,
              barrierDismissible: false,
              builder: (c) => getDialog(
                context,
                () async {
                  context.read<CaptureProvider>().closeWebSocket();
                  var connectedDevice = deviceProvider.connectedDevice;
                  var codec = await getAudioCodec(connectedDevice!.id);
                  context.read<CaptureProvider>().resetState(restartBytesProcessing: true);
                  context.read<CaptureProvider>().initiateWebsocket(codec);
                  Navigator.pop(context);
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
        child: Container(
          child: getTranscriptWidget(
              provider.memoryCreating, provider.segments, provider.photos, deviceProvider.connectedDevice),
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
            provider.closeWebSocket();
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
