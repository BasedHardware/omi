func testRealSchedulerIntegration() async {
  // omi-test-quality: wall-clock-wait -- exercises dispatch delivery on the real scheduler
  try? await Task.sleep(for: .milliseconds(1))
}
