import 'package:flutter/foundation.dart';
import 'package:hive/hive.dart';

import 'package:nooto_v2/plan/plan_storage.dart';

/// Three pivots for the Plan list.
///
///   * [byDate] — original behavior. Buckets by Overdue / Today / This Week
///     / Later / Anytime.
///   * [byProject] — Jira items grouped by `metadata.project_key`. Transcript
///     items always at the bottom under FROM CONVERSATIONS.
///   * [byStatus] — Jira items grouped by status, ordered by status_type
///     (todo → indeterminate → done). Transcript items at the bottom.
enum PlanPivot { byDate, byProject, byStatus }

extension PlanPivotLabel on PlanPivot {
  String get label {
    switch (this) {
      case PlanPivot.byDate:
        return 'By Date';
      case PlanPivot.byProject:
        return 'By Project';
      case PlanPivot.byStatus:
        return 'By Status';
    }
  }
}

/// Persistence + load helpers for the Plan pivot. The picker UI itself
/// lives in `PlanPivotTitle` (collapsed into the AppBar title per the
/// design review) — this class is just the storage seam.
///
/// We keep the type as a holder rather than free functions so call sites
/// read symmetrically (`PlanPivotPicker.loadSaved()`, `.persist(p)`) and
/// so future read/write side-effects (telemetry, reconciliation) have an
/// obvious home.
class PlanPivotPicker {
  PlanPivotPicker._();

  /// Reads the saved pivot from Hive. Returns [PlanPivot.byDate] when the
  /// box isn't open (test paths) or the saved value isn't a known enum name.
  static PlanPivot loadSaved() {
    try {
      final box = Hive.box<dynamic>(PlanBoxes.prefs);
      final raw = box.get(PlanBoxes.pivotKey);
      if (raw is String) {
        for (final pivot in PlanPivot.values) {
          if (pivot.name == raw) return pivot;
        }
      }
    } catch (e) {
      // Box not open — happens in widget tests that don't init Hive. Default
      // to byDate; loadSaved is a hint, not a hard requirement.
      debugPrint('[PlanPivotPicker] loadSaved failed: $e');
    }
    return PlanPivot.byDate;
  }

  /// Persists the picked pivot to Hive. Best-effort: a failed write logs and
  /// returns. The in-memory selection is the source of truth for the
  /// current session.
  static Future<void> persist(PlanPivot pivot) async {
    try {
      await Hive.box<dynamic>(PlanBoxes.prefs).put(PlanBoxes.pivotKey, pivot.name);
    } catch (e) {
      debugPrint('[PlanPivotPicker] persist failed: $e');
    }
  }
}
