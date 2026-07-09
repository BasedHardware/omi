import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/devices/devices_page.dart';
import 'package:omi/pages/meta_wearables/meta_glasses_page.dart';
import 'package:omi/providers/meta_wearables_provider.dart';
import 'package:omi/services/devices/meta_wearables_service.dart';

class MetaWearablesUiProof extends StatelessWidget {
  // Debug-only visual proof screen. Gated to kDebugMode (NOT !kReleaseMode) so
  // a profile/release build can never boot into it — a profile build with the
  // define once stranded the app on the devices proof tab instead of the real
  // onboarding/home flow.
  static const bool enabled = kDebugMode && bool.fromEnvironment('OMI_META_UI_PROOF');

  const MetaWearablesUiProof({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider<MetaWearablesProvider>(
      create: (_) {
        final provider = MetaWearablesProvider(service: const MetaWearablesProofService());
        provider.compatibilityByUuid[MetaWearablesProofService.rayBanMeta.uuid] =
            DeviceCompatibility.deviceUpdateRequired;
        provider.compatibilityByUuid[MetaWearablesProofService.rayBanDisplay.uuid] =
            DeviceCompatibility.sdkUpdateRequired;
        provider.init();
        return provider;
      },
      child: DefaultTabController(
        length: 2,
        child: Scaffold(
          backgroundColor: const Color(0xFF0D0D0D),
          appBar: AppBar(
            title: const Text('Meta UI Proof'),
            bottom: const TabBar(
              tabs: [
                Tab(text: 'Devices proof'),
                Tab(text: 'Glasses proof'),
              ],
            ),
          ),
          body: const TabBarView(
            children: [
              DevicesPage(),
              MetaGlassesPage(),
            ],
          ),
        ),
      ),
    );
  }
}

class MetaWearablesProofService extends MetaWearablesService {
  static const rayBanMeta = DeviceInfo(
    uuid: 'proof-rayban-meta',
    name: 'Proof Ray-Ban Meta',
    kind: DeviceKind.rayBanMeta,
    linkState: DeviceLinkState.connected,
  );

  static const rayBanDisplay = DeviceInfo(
    uuid: 'proof-rayban-display',
    name: 'Proof Ray-Ban Display',
    kind: DeviceKind.rayBanDisplay,
    linkState: DeviceLinkState.connected,
  );

  const MetaWearablesProofService();

  @override
  Stream<RegistrationState> registrationStateStream() => Stream.value(RegistrationState.registered);

  @override
  Stream<DeviceInfo?> activeDeviceStream() => Stream.value(rayBanMeta);

  @override
  Stream<List<DeviceInfo>> devicesStream() => Stream.value(const [rayBanMeta, rayBanDisplay]);

  @override
  Future<MetaWearablesSnapshot> snapshot() async {
    return const MetaWearablesSnapshot(
      registrationState: RegistrationState.registered,
      devices: [rayBanMeta, rayBanDisplay],
      activeDevice: rayBanMeta,
      cameraPermissionState: MetaGlassesCameraPermissionState.granted,
      diagnostics: {'proof': true},
    );
  }

  @override
  Future<int> startPreviewStream({
    String? deviceUUID,
    int fps = 30,
    StreamQuality quality = StreamQuality.medium,
  }) async {
    return 90210;
  }

  @override
  Future<void> stopPreviewStream({String? deviceUUID}) async {}

  @override
  Future<void> openFirmwareUpdate() async {}

  @override
  Future<void> openDATGlassesAppUpdate() async {}
}
