/// Phone calls are hidden from the mobile app for now. Every entry point (Settings row and search,
/// the Memories header button, the record-options and pendant sheets) checks this one switch.
abstract final class PhoneCallsFeature {
  static const bool visible = false;
}
