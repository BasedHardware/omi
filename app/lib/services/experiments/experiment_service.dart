import 'dart:async';
import 'package:flutter/foundation.dart';
import 'experiment_definition.dart';
export 'experiment_definition.dart';

typedef ExperimentEmitter = void Function(String event, Map<String, Object> properties);

/// Memory-only assignments, fenced by identity/consent generation. The service
/// never persists identities, flag payloads, user content, or QA assignments.
class ExperimentService extends ChangeNotifier {
  ExperimentService(
      {required this.provider,
      required Iterable<ExperimentDefinition<dynamic>> definitions,
      required this.emit,
      DateTime Function()? now,
      this.cacheTtl = const Duration(minutes: 5),
      this.loadTimeout = const Duration(milliseconds: 800),
      this.allowQaOverrides = false})
      : _now = now ?? DateTime.now,
        _definitions = {for (final definition in definitions) definition.key: definition} {
    if (_definitions.length != definitions.length || _definitions.length > 16) {
      throw ArgumentError('Experiment registry must be unique and bounded to 16 definitions');
    }
  }
  static const enabledFlag = 'mobile-experiments-enabled';
  final ExperimentFlagProvider provider;
  final ExperimentEmitter emit;
  final Duration cacheTtl;
  final Duration loadTimeout;
  final bool allowQaOverrides;
  final DateTime Function() _now;
  final Map<String, ExperimentDefinition<dynamic>> _definitions;
  final Set<ExperimentLease<dynamic>> _leases = {};
  final Map<String, String> _qa = {};
  ExperimentContext? _context;
  ExperimentFlagSnapshot? _snapshot;
  Future<ExperimentFlagSnapshot?>? _pending;
  int _generation = 0;
  bool _killed = false;
  bool _disposed = false;

  int get generation => _generation;
  bool get eligible => !_disposed && !_killed && _context?.analyticsEnabled == true && _context!.identityKey.isNotEmpty;

  /// Call before SDK identify/reset; never wait for that asynchronous transition.
  /// Calling with the same context intentionally fences A -> signed-out -> A.
  void updateContext(ExperimentContext context) {
    _context = context;
    _generation++;
    _snapshot = null;
    _pending = null;
    _qa.clear();
    _revokeAll();
    notifyListeners();
  }

  void setKillSwitch(bool disabled) {
    _killed = disabled;
    if (disabled) {
      _generation++;
      _pending = null;
      _snapshot = null;
      _revokeAll();
    }
    notifyListeners();
  }

  void setQaOverride(String key, String? variant) {
    if (kReleaseMode || !allowQaOverrides) throw StateError('QA overrides unavailable');
    final definition = _definitions[key];
    if (definition == null || (variant != null && !definition.variants.containsKey(variant))) {
      throw ArgumentError('Unregistered QA variant');
    }
    if (variant == null) {
      _qa.remove(key);
    } else {
      _qa[key] = variant;
    }
    // Overrides apply only to the next lease; never repaint an active surface.
  }

  bool _fresh(ExperimentFlagSnapshot snapshot) =>
      snapshot.authoritative &&
      snapshot.identityKey == _context?.identityKey &&
      !snapshot.fetchedAt.isAfter(_now()) &&
      _now().difference(snapshot.fetchedAt) < cacheTtl;

  Future<void> refresh() async {
    await _load(force: true);
  }

  Future<ExperimentFlagSnapshot?> _load({bool force = false}) {
    if (!eligible) return Future.value(null);
    if (!force && _snapshot != null && _fresh(_snapshot!)) return Future.value(_snapshot);
    if (_pending != null) return _pending!;
    final generation = _generation;
    final context = _context!;
    final completer = Completer<ExperimentFlagSnapshot?>();
    _pending = completer.future;
    () async {
      ExperimentFlagSnapshot? result;
      try {
        final snapshot = await provider.fetch(context).timeout(loadTimeout);
        if (generation == _generation && eligible && _fresh(snapshot)) {
          applySnapshot(snapshot);
          result = snapshot;
        }
      } catch (_) {
        // Fixed reason only: exception text may contain HTTP bodies or identity.
        if (generation == _generation && eligible) _diagnostic('unavailable');
      } finally {
        if (generation == _generation) _pending = null;
        completer.complete(result);
      }
    }();
    return completer.future;
  }

  /// Refresh may revoke a disabled trial, but never switches an active variant.
  void applySnapshot(ExperimentFlagSnapshot snapshot) {
    if (!eligible || !_fresh(snapshot)) return;
    _snapshot = snapshot;
    for (final lease in _leases.toList()) {
      if (snapshot.values[enabledFlag] != true || !_allowed(lease.definition, snapshot)) lease._revoke();
    }
  }

  bool _allowed(ExperimentDefinition<dynamic> definition, ExperimentFlagSnapshot snapshot) {
    final raw = snapshot.values[definition.key];
    final variant = definition.variantKey(raw);
    return definition.variants.containsKey(variant) &&
        (definition.layer == null || snapshot.values['mobile-layer-${definition.layer}'] == definition.key) &&
        _now().isBefore(definition.expiresAt);
  }

  Future<ExperimentLease<T>> open<T>(ExperimentDefinition<T> definition, {required String surface}) async {
    if (!identical(_definitions[definition.key], definition) || !definition.surfaces.contains(surface)) {
      throw ArgumentError('Experiment/surface must be registered');
    }
    final generation = _generation;
    ExperimentLease<T> fallback(String reason) {
      if (eligible) _diagnostic(reason, definition: definition, surface: surface);
      return _lease(definition, surface, definition.defaultVariant, generation, assigned: false);
    }

    final context = _context;
    if (!eligible || context == null) return fallback('disabled');
    if (!definition.namespaces.contains(context.namespace) ||
        context.appBuild < definition.minimumBuild ||
        (definition.maximumBuild != null && context.appBuild > definition.maximumBuild!) ||
        !_now().isBefore(definition.expiresAt)) {
      return fallback('ineligible');
    }
    final qa = _qa[definition.key];
    if (qa != null) return _lease(definition, surface, qa, generation, assigned: false, qa: true);
    final snapshot = await _load();
    if (generation != _generation || !eligible) return fallback('context_changed');
    if (snapshot == null || !_fresh(snapshot)) return fallback('unavailable');
    if (snapshot.values[enabledFlag] != true) return fallback('disabled');
    if (!_allowed(definition, snapshot)) return fallback('unallocated');
    final lease = _lease(definition, surface, definition.variantKey(snapshot.values[definition.key])!, generation,
        assigned: true);
    _send('experiment_assigned', lease.properties);
    return lease;
  }

  ExperimentLease<T> _lease<T>(ExperimentDefinition<T> definition, String surface, String variant, int generation,
      {required bool assigned, bool qa = false}) {
    final lease = ExperimentLease<T>._(this, definition, surface, variant, generation, assigned, qa);
    _leases.add(lease);
    return lease;
  }

  void _diagnostic(String reason, {ExperimentDefinition<dynamic>? definition, String? surface}) {
    _send('experiment_diagnostic', {
      'reason': reason,
      if (definition != null) 'experiment_key': definition.key,
      if (surface != null) 'surface': surface
    });
  }

  void _send(String event, Map<String, Object> properties) {
    if (!eligible) return;
    try {
      emit(event, properties);
    } catch (_) {/* Telemetry never breaks product UI. */}
  }

  void _revokeAll() {
    for (final lease in _leases.toList()) {
      lease._revoke();
    }
  }

  /// Only exposed leases still owned by mounted/active callers contribute.
  /// Max 16 registry keys; no arbitrary remote flag names or values propagate.
  Map<String, Object> outcomeProperties() {
    if (!eligible || _snapshot == null || !_fresh(_snapshot!)) return {};
    final result = <String, Object>{};
    final conflicts = <String>{};
    for (final lease in _leases) {
      if (!lease._canAttribute || !lease._exposed) continue;
      final key = '\$feature/${lease.definition.key}';
      if (result.containsKey(key) && result[key] != lease.variantKey) conflicts.add(key);
      result[key] = lease.variantKey;
    }
    // Ambiguous overlapping surfaces must never falsely attribute an outcome.
    for (final key in conflicts) {
      result.remove(key);
    }
    return result;
  }

  @override
  void dispose() {
    _disposed = true;
    _generation++;
    _revokeAll();
    _leases.clear();
    super.dispose();
  }
}

class ExperimentLease<T> extends ChangeNotifier {
  ExperimentLease._(
      this._service, this.definition, this.surface, this._variantKey, this._generation, this.assigned, this.qa);
  final ExperimentService _service;
  final ExperimentDefinition<T> definition;
  final String surface;
  final String _variantKey;
  final int _generation;
  final bool assigned;
  final bool qa;
  bool _revoked = false;
  bool _closed = false;
  bool _exposed = false;
  String get variantKey => _revoked ? definition.defaultVariant : _variantKey;
  T get variant => definition.variants[variantKey] as T;
  bool get _canAttribute =>
      !_closed &&
      !_revoked &&
      assigned &&
      !qa &&
      _generation == _service.generation &&
      _service.eligible &&
      _service._now().isBefore(definition.expiresAt);
  Map<String, Object> get properties => {
        'experiment_key': definition.key,
        'experiment_version': definition.version,
        'variant': variantKey,
        'surface': surface,
        'holdout': definition.holdoutVariants.contains(variantKey),
        'experiment_qa': qa
      };

  /// Call only after the chosen UI painted, or immediately when a feature is used.
  void expose() {
    if (_exposed || !_canAttribute || _service._snapshot == null || !_service._fresh(_service._snapshot!)) return;
    _exposed = true;
    _service._send('experiment_exposed', {...properties, '\$feature/${definition.key}': variantKey});
    _service._send('\$feature_flag_called', {
      ...properties,
      '\$feature_flag': definition.key,
      '\$feature_flag_response': variantKey,
      '\$feature/${definition.key}': variantKey
    });
  }

  void _revoke() {
    if (!_closed && !_revoked) {
      _revoked = true;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    if (_closed) return;
    _closed = true;
    _service._leases.remove(this);
    super.dispose();
  }
}
