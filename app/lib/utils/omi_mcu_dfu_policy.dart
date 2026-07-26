import 'package:mcumgr_flutter/mcumgr_flutter.dart' as mcumgr;

/// Production MCUboot upgrade policy for Omi pendants.
class OmiMcuDfuPolicy {
  const OmiMcuDfuPolicy._();

  static mcumgr.FirmwareUpgradeConfiguration createConfiguration() {
    return const mcumgr.FirmwareUpgradeConfiguration(
      estimatedSwapTime: Duration.zero,
      // A routine firmware upgrade is not a factory-reset action. Preserve
      // device-owned settings and offline-state metadata across the reboot.
      eraseAppSettings: false,
      pipelineDepth: 1,
    );
  }
}
