import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:provider/provider.dart';

class LiteCaptureWidget extends StatefulWidget {
  const LiteCaptureWidget({super.key});

  @override
  State<LiteCaptureWidget> createState() => LiteCaptureWidgetState();
}

class LiteCaptureWidgetState extends State<LiteCaptureWidget> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  setHasTranscripts(bool hasTranscripts) {
    context.read<CaptureProvider>().setHasTranscripts(hasTranscripts);
  }

  @override
  void initState() {
    WavBytesUtil.clearTempWavFiles();
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      if (context.read<DeviceProvider>().connectedDevice != null) {
        context.read<OnboardingProvider>().stopScanDevices();
      }
      if (mounted) {
        final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
        if (!connectivityProvider.isConnected) {
          context.read<CaptureProvider>().cancelConversationCreationTimer();
        }
      }
    });

    super.initState();
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
      return getLiteTranscriptWidget(
        provider.segments,
        [],
        deviceProvider.connectedDevice,
      );
    });
  }
}
