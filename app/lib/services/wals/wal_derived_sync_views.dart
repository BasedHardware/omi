import 'package:flutter/foundation.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_derived_views.dart';

/// Derived sync views computed from a provider's raw [allWals], for SyncProvider
/// stand-ins (hermetic journeys, visual audits, perf scenarios, widget tests):
/// they exercise the same pending selection as the production provider.
mixin WalDerivedSyncViews on ChangeNotifier implements SyncProvider {
  @override
  List<Wal> get allWals;
  WalDerivedViews? _views;
  List<Wal>? _source;
  int _length = -1;
  @override
  WalDerivedViews get derivedWals {
    final rows = allWals;
    if (_views == null || !identical(rows, _source) || rows.length != _length) {
      _views?.dispose();
      _source = rows;
      _length = rows.length;
      _views = WalDerivedViews(rows);
    }
    _views!.refresh();
    return _views!;
  }

  @override
  List<Wal> get uploadedWals => derivedWals.uploaded;
  @override
  List<Wal> get pendingSyncWals => derivedWals.syncing;
  @override
  List<Wal> get attentionWals => derivedWals.attention;
  @override
  List<Wal> get refusedWals => derivedWals.refused;
  @override
  List<Wal> get pendingWorkWals => derivedWals.pendingWork;
  @override
  int get needsAttentionWalsCount => attentionWals.length;
  @override
  int get terminallyFailedWalsCount => refusedWals.length;
  @override
  WalRefusalSummary get refusalSummary => derivedWals.refusalSummary();
  @override
  void dispose() {
    _views?.dispose();
    super.dispose();
  }
}
