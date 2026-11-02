import 'dart:async';
import 'dart:developer' as developer;
import 'dart:io';

/// Test-target-only cleanup. A VM RPC reaches this exact process and cannot
/// target another app/PID. Do not exit while tests or their teardown still run.
void registerHeavyProcessExit({required bool Function() testsComplete}) {
  developer.registerExtension('ext.omi.heavy.exit', (_, __) async {
    if (!testsComplete()) {
      return developer.ServiceExtensionResponse.error(
          developer.ServiceExtensionResponse.extensionError, 'Harness tests have not finished');
    }
    // Return the authenticated RPC acknowledgement before ending the process.
    // The host has already saved receipts. Never remove the app or its files.
    Timer(const Duration(milliseconds: 250), () => exit(0));
    return developer.ServiceExtensionResponse.result('{"exiting":true}');
  });
}
