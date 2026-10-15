/// A reconnect's initial battery read is not a new charge-start edge.
/// Keep the last observation per device across link loss.
class ChargeStartTracker {
  final Map<String, bool> _charging = {};

  bool observe(String deviceId, bool? charging) {
    if (charging == null) return false;
    final wasCharging = _charging[deviceId] ?? false;
    _charging[deviceId] = charging;
    return charging && !wasCharging;
  }
}
