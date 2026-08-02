import 'package:flutter_test/flutter_test.dart';
import 'package:omi/self_hosted/sync/self_hosted_wal_sync_adapter.dart';

void main() {
  test('disabled configuration is a no-op', () async {
    final adapter = NoopSelfHostedWalSyncAdapter(enabled: false);

    expect(adapter.enabled, isFalse);
    expect(await adapter.schedule(walId: 'wal-1'), SelfHostedWalSyncResult.disabled);
  });

  test('enabled configuration remains deferred until the Worker upload contract is implemented', () async {
    final adapter = NoopSelfHostedWalSyncAdapter(enabled: true);

    expect(await adapter.schedule(walId: 'wal-1'), SelfHostedWalSyncResult.deferred);
  });
}
