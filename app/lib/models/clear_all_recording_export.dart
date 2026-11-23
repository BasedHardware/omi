// Keeps the Clear All export active across sheet and Offline Sync page lifetimes.
import 'package:flutter/foundation.dart';

import 'package:omi/services/wals/wal.dart';

class ClearAllRecordingExport extends ChangeNotifier implements ValueListenable<Set<String>?> {
  Set<String>? _walIds;
  bool _disposed = false;

  @override
  Set<String>? get value => _walIds;

  Future<void> run(List<Wal> wals, Future<void> Function(List<Wal>) share) async {
    if (_disposed || _walIds != null) return;
    _walIds = Set<String>.unmodifiable(wals.map((wal) => wal.id));
    notifyListeners();
    try {
      await share(wals);
    } finally {
      _walIds = null;
      if (!_disposed) notifyListeners();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
