// The Quick Summary stream's events, one per SSE `data:` frame of
// POST /v1/conversations/{id}/interim-summary. A local SSE event schema, not a REST DTO: the route's
// OpenAPI response is the event stream itself. Parsed by backend/http/api/interim_summary.dart.

/// One event of the Quick Summary stream.
sealed class InterimSummaryEvent {
  const InterimSummaryEvent();

  /// Parses one SSE `data:` payload; unknown types are ignored (null).
  static InterimSummaryEvent? fromFrame(Map<String, dynamic> json) => switch (json['type']) {
        'start' => InterimSummaryStart(model: json['model'] as String?),
        'delta' => InterimSummaryDelta(json['text'] as String? ?? ''),
        'done' => InterimSummaryDone(
            ttftSeconds: (json['ttft_s'] as num?)?.toDouble(),
            totalSeconds: (json['total_s'] as num?)?.toDouble(),
            usd: (json['usd'] as num?)?.toDouble(),
          ),
        'error' => InterimSummaryError(json['message'] as String? ?? 'error'),
        _ => null,
      };
}

class InterimSummaryStart extends InterimSummaryEvent {
  const InterimSummaryStart({this.model});
  final String? model;
}

class InterimSummaryDelta extends InterimSummaryEvent {
  const InterimSummaryDelta(this.text);
  final String text;
}

class InterimSummaryDone extends InterimSummaryEvent {
  const InterimSummaryDone({this.ttftSeconds, this.totalSeconds, this.usd});
  final double? ttftSeconds;
  final double? totalSeconds;
  final double? usd;
}

class InterimSummaryError extends InterimSummaryEvent {
  const InterimSummaryError(this.message);
  final String message;
}
