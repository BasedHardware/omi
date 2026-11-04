import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';

/// Reports the visible Home row count. The server keeps the daily peak.
/// Identical counts inside a minute are dropped so a rebuild storm does not post.
/// A failed report is dropped. It never invents a row count.
class HomeRowsHealth {
  static void Function(int rowCount) report = _post;
  static int? _lastCount;
  static DateTime? _lastAt;
  static const _quiet = Duration(minutes: 1);

  static void note(int rowCount, {DateTime? now}) {
    if (rowCount < 0) return;
    final at = now ?? DateTime.now();
    final same = _lastCount == rowCount;
    final recent = _lastAt != null && at.difference(_lastAt!) < _quiet;
    if (same && recent) return;
    if (_lastCount != null && rowCount <= _lastCount! && recent) return;
    _lastCount = rowCount;
    _lastAt = at;
    report(rowCount);
  }

  static void resetForTests() {
    _lastCount = null;
    _lastAt = null;
    report = _post;
  }

  static void _post(int rowCount) {
    if (Platform.environment['FLUTTER_TEST'] == 'true') return;
    final base = Env.apiBaseUrl;
    if (base == null || base.isEmpty) return;
    final root = base.endsWith('/') ? base : '$base/';
    _send(root, rowCount);
  }

  static Future<void> _send(String root, int rowCount) async {
    final result = await executeApi<void>(
      request: ApiRequest(
        url: '${root}v1/telemetry/home-rows',
        method: 'POST',
        body: jsonEncode({'row_count': rowCount}),
      ),
      decode: (_) {},
    );
    switch (result) {
      case ApiSuccess():
      case ApiFailure():
        return;
    }
  }
}
