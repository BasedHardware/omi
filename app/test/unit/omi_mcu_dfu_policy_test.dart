import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/omi_mcu_dfu_policy.dart';

void main() {
  test('routine MCU firmware upgrades preserve pendant application settings', () {
    final configuration = OmiMcuDfuPolicy.createConfiguration();

    expect(configuration.eraseAppSettings, isFalse);
    expect(configuration.estimatedSwapTime, Duration.zero);
    expect(configuration.pipelineDepth, 1);
  });
}
