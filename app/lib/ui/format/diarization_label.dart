// @dart=3.3

/// An opaque storage identity. Resolve it through SpeakerNames before rendering.
/// The representation deliberately refuses string interpolation, including via Object.
extension type DiarizationLabel._(_RawVoice _voice) {
  DiarizationLabel.fromRaw(int value) : _voice = _RawVoice(value);

  /// For wire/storage adapters only; never a display ordinal.
  int get rawForTransport => _voice.value;
}

final class _RawVoice {
  const _RawVoice(this.value);
  final int value;

  @override
  bool operator ==(Object other) => other is _RawVoice && other.value == value;
  @override
  int get hashCode => value.hashCode;
  @override
  String toString() => throw UnsupportedError('Resolve DiarizationLabel through SpeakerNames');
}
