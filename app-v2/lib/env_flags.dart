/// Build-time flags. Phase 1 ships with `kEnableFirebaseAuth=false` so the
/// chat flow can be exercised on the emulator without registering new bundle
/// IDs in Firebase first. Flip to `true` once Task #12 (Firebase v2 bundle
/// registrations) is done.
const bool kEnableFirebaseAuth = false;
