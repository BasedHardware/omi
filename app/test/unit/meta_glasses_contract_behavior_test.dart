import 'package:flutter_test/flutter_test.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:omi/l10n/app_localizations_en.dart';
import 'package:omi/providers/meta_wearables_provider.dart';
import 'package:omi/services/devices/meta_wearables_service.dart';
import 'package:omi/utils/meta_wearables_device_label.dart';

void main() {
  group('MetaWearablesProvider.openCompatibilityUpdate', () {
    const device = DeviceInfo(
      uuid: 'mock-ray-ban',
      name: 'Mock Ray-Ban',
      kind: DeviceKind.rayBanMeta,
      linkState: DeviceLinkState.connected,
    );

    for (final scenario in <_CompatibilityScenario>[
      const _CompatibilityScenario(DeviceCompatibility.deviceUpdateRequired, firmwareCalls: 1),
      const _CompatibilityScenario(DeviceCompatibility.sdkUpdateRequired, datAppCalls: 1),
      const _CompatibilityScenario(DeviceCompatibility.compatible),
      const _CompatibilityScenario(DeviceCompatibility.unknown),
    ]) {
      test('${scenario.compatibility} routes to the expected update action', () async {
        final service = _RecordingMetaWearablesService();
        final provider = MetaWearablesProvider(service: service)
          ..compatibilityByUuid[device.uuid] = scenario.compatibility;

        await provider.openCompatibilityUpdate(device);

        expect(service.firmwareCalls, scenario.firmwareCalls);
        expect(service.datAppCalls, scenario.datAppCalls);
        provider.dispose();
      });
    }
  });

  test('metaWearablesDeviceKindLabel maps every DAT device kind to English l10n', () {
    final l10n = AppLocalizationsEn();

    expect(metaWearablesDeviceKindLabel(l10n, DeviceKind.rayBanMeta), l10n.metaGlassesTypeRayBanMeta);
    expect(metaWearablesDeviceKindLabel(l10n, DeviceKind.rayBanDisplay), l10n.metaGlassesTypeRayBanDisplay);
    expect(metaWearablesDeviceKindLabel(l10n, DeviceKind.oakleyMeta), l10n.metaGlassesTypeOakleyMeta);
    expect(metaWearablesDeviceKindLabel(l10n, DeviceKind.unknown), l10n.metaGlasses);
  });
}

class _CompatibilityScenario {
  final DeviceCompatibility compatibility;
  final int firmwareCalls;
  final int datAppCalls;

  const _CompatibilityScenario(this.compatibility, {this.firmwareCalls = 0, this.datAppCalls = 0});
}

class _RecordingMetaWearablesService extends MetaWearablesService {
  int firmwareCalls = 0;
  int datAppCalls = 0;

  @override
  Future<void> openFirmwareUpdate() async {
    firmwareCalls += 1;
  }

  @override
  Future<void> openDATGlassesAppUpdate() async {
    datAppCalls += 1;
  }
}
