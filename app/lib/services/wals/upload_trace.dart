enum WalJournalRecovery { fresh, recovered, mixed }

typedef UploadTraceSnapshot = ({
  String trace,
  String? holdState,
  int? holdSealedAtMs,
  bool recovered,
  WalJournalRecovery? journalRecovery,
});

/// Measures how long a sealed recording file waits on the phone before the
/// server accepts it, and which upload gate last held it. Measurement only: it
/// never decides whether or when anything uploads, and losing it changes
/// nothing. Held in memory; a restarted app reports `none` for older waits.
///
/// The value travels as one header on the upload,
/// `sealed=<epoch>;first=<epoch>;gate=<label>;attempts=<n>`, for the oldest
/// file in the batch. Labels are a closed set the server also enforces.
class UploadTrace {
  UploadTrace({DateTime Function()? now}) : _now = now ?? DateTime.now;

  static final UploadTrace instance = UploadTrace();

  static const gates = {
    'none',
    'rate_limited',
    'auto_upload_off',
    'background',
    'retries_exhausted',
    'in_flight',
    'offline',
    'server_hold',
    'other',
  };
  static const int _maxTracked = 256;

  final DateTime Function() _now;
  String? _lastGate;
  DateTime? _lastGateAt;
  final Map<String, ({int first, int attempts})> _attempts = {};
  final Map<String, UploadTraceSnapshot> _pending = {};

  /// An upload pass was held back for [gate]. Unknown labels become `other`.
  void noteGate(String gate) {
    _lastGate = gates.contains(gate) ? gate : 'other';
    _lastGateAt = _now();
  }

  /// Builds the header for an upload whose oldest file is [oldestId], sealed
  /// at [sealedAtSeconds], and parks it under [firstFilePath] for the uploader.
  void prepare({
    required String firstFilePath,
    required String oldestId,
    required int sealedAtSeconds,
    String? holdState,
    int? holdSealedAtMs,
    bool recovered = false,
    WalJournalRecovery? journalRecovery,
  }) {
    if (sealedAtSeconds <= 0) return;
    final nowSeconds = _now().millisecondsSinceEpoch ~/ 1000;
    final seen = _attempts[oldestId];
    final entry = (first: seen?.first ?? nowSeconds, attempts: (seen?.attempts ?? 0) + 1);
    if (seen == null && _attempts.length >= _maxTracked) _attempts.remove(_attempts.keys.first);
    _attempts[oldestId] = entry;
    // Only a gate that closed after this file was sealed can have held it.
    final gateAt = _lastGateAt;
    final held = gateAt != null && gateAt.millisecondsSinceEpoch ~/ 1000 >= sealedAtSeconds;
    final gate = held ? (_lastGate ?? 'none') : 'none';
    if (_pending.length >= _maxTracked) _pending.remove(_pending.keys.first);
    _pending[firstFilePath] = (
      trace: 'sealed=$sealedAtSeconds;first=${entry.first};gate=$gate;attempts=${entry.attempts}',
      holdState: holdState,
      holdSealedAtMs: holdSealedAtMs,
      recovered: recovered,
      journalRecovery: journalRecovery,
    );
  }

  /// The header parked for the upload that starts with [firstFilePath], once.
  UploadTraceSnapshot? take(String firstFilePath) => _pending.remove(firstFilePath);

  /// Evaluate at each HTTP send, including a replay after authentication.
  Map<String, String> holdHeadersAtSend(UploadTraceSnapshot? upload, {required bool holdEnabled}) {
    final state = upload?.holdState;
    if (state == null) return const {};
    final sealedAtMs = upload?.holdSealedAtMs;
    final journalRecovery = holdEnabled ? upload?.journalRecovery : null;
    return {
      'X-Omi-Upload-Hold': holdEnabled ? state : 'none',
      if (upload?.recovered == true || journalRecovery != null)
        'X-Omi-Upload-Recovered': upload?.recovered == true ? '1' : '0',
      if (journalRecovery != null) 'X-Omi-Upload-Journal-Recovery': journalRecovery.name,
      if (holdEnabled && state != 'none' && sealedAtMs != null)
        'X-Omi-Upload-Hold-Age-Ms': (_now().millisecondsSinceEpoch - sealedAtMs).clamp(0, 86400000).toString(),
    };
  }

  /// The server accepted the upload whose oldest file is [oldestId].
  void accepted(String oldestId) => _attempts.remove(oldestId);
}
