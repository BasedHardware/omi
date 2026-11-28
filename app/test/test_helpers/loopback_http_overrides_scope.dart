import 'dart:io';

/// Enables real HttpClient requests only for a suite using loopback fixtures.
/// Flutter's default mock override is restored when the suite completes.
class LoopbackHttpOverridesScope {
  HttpOverrides? _previous;
  bool _active = false;

  void enable() {
    if (_active) throw StateError('Loopback HTTP scope is already enabled');
    _previous = HttpOverrides.current;
    HttpOverrides.global = null;
    _active = true;
  }

  void restore() {
    if (!_active) return;
    HttpOverrides.global = _previous;
    _previous = null;
    _active = false;
  }
}
