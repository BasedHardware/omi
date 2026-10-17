/// Selected capture route, not an entitlement decision. Local speech is an
/// asynchronous consumer: enqueueing to it is never an audio-delivery receipt.
/// CaptureController supplies its resolved route; no preference/service lookup.
abstract final class LocalSttCustody {
  static bool selectedLocalRoute = false;
  static bool get keepsPhoneAudio => selectedLocalRoute;
}
