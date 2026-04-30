/// Build-time flags. v2 reuses the legacy `nooto-dev` Firebase project and
/// dev bundle IDs (`com.nooto-app-with-wearable.ios12.development` /
/// `com.togodynamics.nooto.dev`) — see `lib/firebase_options.dart`. Real
/// Firebase auth is on for v2 dev builds.
const bool kEnableFirebaseAuth = true;
