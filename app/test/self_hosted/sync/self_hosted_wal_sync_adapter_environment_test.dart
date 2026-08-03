import 'package:flutter_test/flutter_test.dart';
import 'package:omi/self_hosted/sync/self_hosted_wal_sync_adapter.dart';

const _expectedEnabled = bool.fromEnvironment('WAL_ADAPTER_EXPECTED_ENABLED');
const _scenario = String.fromEnvironment(
  'WAL_ADAPTER_TEST_SCENARIO',
  defaultValue: 'default',
);

void main() {
  test('environment $_scenario uses the expected no-op state', () async {
    final adapter = NoopSelfHostedWalSyncAdapter();

    expect(adapter.enabled, _expectedEnabled);
    expect(
      await adapter.schedule(walId: 'wal-1'),
      _expectedEnabled ? SelfHostedWalSyncResult.deferred : SelfHostedWalSyncResult.disabled,
    );
  });
}
