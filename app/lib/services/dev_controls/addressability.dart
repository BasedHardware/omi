/// B1 compiling boundary. App UI owns implementation; see ADDRESSABILITY.md.
library;

import 'package:flutter/widgets.dart';

export 'addressability_catalog.dart';

/// Names are shared with the JSON catalog; dynamic IDs never use row positions.
abstract final class AddressKey {
  static String row(String surface, String opaqueId) => throw UnimplementedError('B1 stable row key');
  static bool valid(String value) => throw UnimplementedError('B1 key grammar');
}

enum AuthPhase { unavailable, signedOut, signedIn, reauthentication, cuttingOver }

enum CapturePhase { unavailable, idle, recording, stopping }

enum BlePhase { unavailable, disconnected, connecting, connected }

enum WalPhase { unavailable, ready, draining, failed }

enum LoadPhase { unavailable, loading, ready, failed }

/// Spine B supplies this projection, not its mutable flag store. No values of
/// arbitrary type, experimental payloads, or unregistered IDs cross this seam.
class FlagState {
  const FlagState(this.id, this.effective, this.override);
  final String id;
  final bool effective;
  final bool? override;
}

abstract interface class ControlStateSource {
  AuthPhase get auth;
  CapturePhase get capture;
  BlePhase get ble;
  WalPhase get wal;
  int get walPending;
  Map<String, LoadPhase> get providers;
  List<FlagState> get flags;
  Set<String> get registeredFlags;
  bool get flagsHydrated;
}

abstract interface class AddressableNavigator {
  String? get visibleRoute;
  bool get rootMounted;
  int get pendingTransitions;
  Future<void> navigate(String routeId, {String? recordId});
}

class AddressabilityRefused implements Exception {
  const AddressabilityRefused(this.code);
  final String code;
}

class ControlReadinessTimeout implements Exception {
  const ControlReadinessTimeout(this.condition);
  final String condition;
}

class ControlsV2 {
  ControlsV2(this.source, this.navigator);
  final ControlStateSource source;
  final AddressableNavigator navigator;

  /// Pure projection; never accepts arbitrary provider.toJson() output.
  Map<String, Object?> snapshot() => throw UnimplementedError('B1 bounded state');
  Map<String, Object?> capabilities({String? requestedVersion}) => throw UnimplementedError('B1 negotiation');
  Future<Map<String, Object?>> waitReady(String condition, {required Duration timeout}) =>
      throw UnimplementedError('B1 readiness');
}

/// Production navigation adapter, used both by the eligible VM handler and
/// surface tests. No injected page builders and no alternate test route table.
class AppAddressability implements AddressableNavigator {
  AppAddressability._();
  static final instance = AppAddressability._();

  /// Signed-out onboarding boot never constructs the signed-in HomePage.
  Widget buildShell({String initialRoute = 'home'}) => throw UnimplementedError('B1 existing app shell');
  ControlsV2 get controls => throw UnimplementedError('B1 live provider projection');
  @override
  String? get visibleRoute => throw UnimplementedError('B1 visible route');
  @override
  bool get rootMounted => throw UnimplementedError('B1 mounted route root');
  @override
  int get pendingTransitions => throw UnimplementedError('B1 transitions');
  @override
  Future<void> navigate(String routeId, {String? recordId}) => throw UnimplementedError('B1 production navigation');
}
