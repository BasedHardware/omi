import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

final Object _contractZoneKey = Object();

class _ContractState {
  String? pending;
}

/// Place this on its own line inside the contract body. Unlike a named
/// argument, Dart's formatter keeps this marker independently removable.
void pendingContract(String package) {
  final state = Zone.current[_contractZoneKey] as _ContractState?;
  if (state == null || state.pending != null || package.isEmpty) {
    throw StateError('pendingContract requires one marker inside a contract body');
  }
  state.pending = package;
  print('PENDING CONTRACT $package (executing)');
}

Future<void> runContract(FutureOr<void> Function() body) async {
  final state = _ContractState();
  try {
    await runZoned(() async => await body(), zoneValues: {_contractZoneKey: state});
  } on TestFailure {
    if (state.pending == null) rethrow;
    return;
  } on UnimplementedError {
    if (state.pending == null) rethrow;
    return;
  }
  if (state.pending != null) {
    throw TestFailure('XPASS CONTRACT ${state.pending}: remove the pending marker');
  }
}

void contractTest(String name, FutureOr<void> Function() body) {
  test('CONTRACT: $name', () => runContract(body));
}
