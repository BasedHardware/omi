import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/schema/geolocation.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/providers/onboarding_provider.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:provider/provider.dart';

class LiteCaptureWidget extends StatefulWidget {
  const LiteCaptureWidget({super.key});

  @override
  State<LiteCaptureWidget> createState() => LiteCaptureWidgetState();
}

class LiteCaptureWidgetState extends State<LiteCaptureWidget>
    with AutomaticKeepAliveClientMixin, WidgetsBindingObserver {
  @override
  bool get wantKeepAlive => true;

  setHasTranscripts(bool hasTranscripts) {
    context.read<CaptureProvider>().setHasTranscripts(hasTranscripts);
  }

  void _onReceiveTaskData(dynamic data) {
    if (data is Map<String, dynamic>) {
      if (data.containsKey('latitude') && data.containsKey('longitude')) {
        if (mounted) {
          context.read<CaptureProvider>().setGeolocation(Geolocation(
                latitude: data['latitude'],
                longitude: data['longitude'],
                accuracy: data['accuracy'],
                altitude: data['altitude'],
                time: DateTime.parse(data['time']),
              ));
        }
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
      if (context.read<DeviceProvider>().connectedDevice != null) {
        context.read<OnboardingProvider>().stopFindDeviceTimer();
      }
      if (mounted) {
        final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
        if (!connectivityProvider.isConnected) {
          context.read<CaptureProvider>().cancelMemoryCreationTimer();
        }
      }
    });

    super.initState();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<BleAudioCodec> _getAudioCodec(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return BleAudioCodec.pcm8;
    }
    return connection.getAudioCodec();
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
                  var connectedDevice = deviceProvider.connectedDevice;
                  var codec = await _getAudioCodec(connectedDevice!.id);
                  await context.read<CaptureProvider>().changeAudioRecordProfile(codec);
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
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
          );
        },
        child: getLiteTranscriptWidget(
          provider.segments,
          [],
          deviceProvider.connectedDevice,
        ),
      );
    });
  }
}
