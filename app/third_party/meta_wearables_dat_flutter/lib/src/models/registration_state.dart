/// State of the registration lifecycle between a host app and the Meta AI app.
///
/// Mirrors `RegistrationState` from Meta's iOS DAT SDK and Android DAT SDK so
/// that values transit the platform channel as plain integers without lossy
/// translation. Surfaced by [MetaWearablesDat.registrationStateStream] and
/// [MetaWearablesDat.getRegistrationState].
enum RegistrationState {
  /// The Meta AI app is not installed, or Developer Mode is disabled. The
  /// host app cannot start registration in this state.
  unavailable(0),

  /// The Meta AI app is installed and Developer Mode is enabled, but the
  /// host app has not yet registered a device.
  available(1),

  /// Registration is in progress. The user has been deep-linked into the
  /// Meta AI app and has not yet returned.
  registering(2),

  /// A device is registered and ready to use.
  registered(3);

  const RegistrationState(this.value);

  /// The integer used on the platform channel.
  final int value;

  /// Maps a platform-channel integer to a [RegistrationState].
  static RegistrationState fromInt(int? value) {
    switch (value) {
      case 0:
        return RegistrationState.unavailable;
      case 1:
        return RegistrationState.available;
      case 2:
        return RegistrationState.registering;
      case 3:
        return RegistrationState.registered;
      case _:
        return RegistrationState.unavailable;
    }
  }
}
