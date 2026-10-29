import 'dart:math';

import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';

const chunkSizeInSeconds = 60;
const flushIntervalInSeconds = 90;

const sdcardChunkSizeSecs = 60;
const newFrameSyncDelaySeconds = 15;
const framesPerFlashPage = 8;
const secondsPerFlashPage = 1.4;

/// Sync lifecycle of a recording.
///
/// - [inProgress] — still being written (audio is live).
/// - [miss]       — finalized locally, not yet uploaded (or reverted to retry).
/// - [uploaded]   — audio safely received by the server (HTTP 202); the server
///                  job is processing. NOT yet confirmed and NOT deletable —
///                  the local file is retained until [synced]. A reconciler
///                  resolves the job_id to [synced] / [miss] / [corrupted].
/// - [synced]     — server job confirmed success; conversation created. Safe to clean up.
/// - [corrupted]  — the underlying local file is missing/unreadable.
/// - [outsideRecoveryWindow] — the server permanently refused this recording
///                  because it is older than the automatic-recovery window
///                  (HTTP 422 `backfill_lookback_exceeded`). The local file is
///                  intact, but re-uploading it can never succeed, so it is
///                  terminal for sync rather than pending work.
/// - [unsupportedAudio] — the server accepted the bytes and its job then failed
///                  on the audio itself (`sync_invalid_audio` / `stt_invalid_input`).
///                  The same bytes produce the same verdict every time, so like
///                  [outsideRecoveryWindow] this is terminal rather than pending.
///                  The local file is kept; only deletion is offered.
/// - [uploadRejected] — an upload request was refused (HTTP 400/413, or a
///                  historical 403). Retained without user attention; automatic
///                  uploads retry daily for seven days, then count as reported.
enum WalStatus {
  inProgress,
  miss,
  uploaded,
  synced,
  corrupted,
  outsideRecoveryWindow,
  unsupportedAudio,
  uploadRejected,
}

enum WalStorage { mem, disk, sdcard, flashPage }

enum SyncMethod { ble }

/// Bounded reasons an upload was refused, persisted so the row can say which
/// refusal it was instead of a bare "Failed". Tokens, never server prose.
class WalUploadRejection {
  static const invalidCaptureTime = 'invalid_capture_time';
  static const tooLarge = 'too_large';
  static const serverRefused = 'server_refused';
  static const invalidFile = 'invalid_file';
  static const emptyClip = 'empty_clip';
  static const malformedMultipart = 'malformed_multipart';
  static const tooManyParts = 'too_many_parts';

  static String bounded(String? code) => const {
        emptyClip,
        invalidCaptureTime,
        tooLarge,
        serverRefused,
        invalidFile,
        malformedMultipart,
        tooManyParts,
      }.contains(code)
          ? code!
          : serverRefused;
}

/// User-facing sync state for a single recording, derived from [Wal.status],
/// [Wal.isSyncing] and [Wal.retryCount]. This is what the sync UI renders so a
/// recording is never shown as an indistinct row — every state is explicit.
///
/// - [syncing]    — actively uploading right now
/// - [uploaded]   — uploaded; processing on Omi's servers (will finish in the background)
/// - [synced]     — safely backed up to the cloud
/// - [waiting]    — recorded, never attempted yet (will sync automatically)
/// - [retrying]   — a sync attempt failed; will be retried automatically
/// - [failed]     — auto-retries exhausted; needs a manual retry
/// - [corrupted]  — the underlying file is missing/unreadable
/// - [outsideRecoveryWindow] — too old for the server to accept; retrying
///                  cannot help, so the row explains that instead of offering
///                  a Retry the user would spend forever
/// - [unsupportedAudio] — the server could not read the audio; re-uploading the
///                  same bytes cannot change that, so the row offers deletion
///                  rather than a Retry that is guaranteed to fail
enum WalSyncDisplayState {
  syncing,
  uploaded,
  synced,
  waiting,
  retrying,
  failed,
  corrupted,
  outsideRecoveryWindow,
  unsupportedAudio,
  uploadRejected,
}

/// Worst user-facing sync outcome across a set of WALs, so an aggregate
/// indicator (the live-capture one) can name the state that matters instead
/// of always claiming a healthy local save. Ordering: a WAL that can no
/// longer upload on its own (failed/corrupted/outside the recovery window)
/// outranks one that is retrying, which outranks one that is uploading;
/// healthy/quiet states lose to everything.
WalSyncDisplayState? worstSessionSyncState(Iterable<Wal> wals) {
  WalSyncDisplayState? worst;
  for (final wal in wals) {
    final state = wal.syncDisplayState;
    if (worst == null || _syncOutcomeRank(state) > _syncOutcomeRank(worst)) {
      worst = state;
    }
  }
  return worst;
}

/// Whether the state is terminal for automatic uploads and a deliberate
/// retry can still help (the sync pages' "Failed — tap Retry" case, which
/// resets the auto-retry budget). Corrupted and out-of-window recordings
/// cannot be retried into success.
bool isRetryableSyncState(WalSyncDisplayState state) => state == WalSyncDisplayState.failed;

/// Whether the state is one the sync pages file under needs attention: the
/// server refused it, retries are exhausted, or audio is unreadable/too old.
/// Terminal for automatic uploads; SyncPendingWork.needsAttention and every
/// row/bulk action read this one set so they cannot drift apart.
bool isAttentionSyncState(WalSyncDisplayState state) =>
    state == WalSyncDisplayState.failed ||
    state == WalSyncDisplayState.corrupted ||
    state == WalSyncDisplayState.outsideRecoveryWindow ||
    state == WalSyncDisplayState.unsupportedAudio;

/// Whether a recording may be deleted where a block action found it: only a
/// member that is idle (not mid-upload) and already in a terminal,
/// needs-attention state. A block can mix a refused member with one still
/// uploading — the refusal label belongs to the former, so the latter's audio
/// is never deleted under it.
bool walDeletionAllowed(Wal wal) =>
    !wal.isSyncing && (isAttentionSyncState(wal.syncDisplayState) || wal.status == WalStatus.uploadRejected);

/// Whether a deliberate retry of this recording can change its outcome. A
/// `too_large` refusal (413) is deterministic — the same bytes are the same
/// size — so its row offers Delete only, never a Retry that is guaranteed to
/// fail. A local-only recording never joins a cloud drain. Every other
/// retryable state keeps its Retry.
bool walRetryCanHelp(Wal wal) =>
    !wal.onDeviceOnly &&
    isRetryableSyncState(wal.syncDisplayState) &&
    wal.uploadRejectionReason != WalUploadRejection.tooLarge;

int _syncOutcomeRank(WalSyncDisplayState state) => switch (state) {
      WalSyncDisplayState.failed => 4,
      WalSyncDisplayState.corrupted => 4,
      WalSyncDisplayState.outsideRecoveryWindow => 4,
      WalSyncDisplayState.unsupportedAudio => 4,
      WalSyncDisplayState.uploadRejected => 1,
      WalSyncDisplayState.retrying => 3,
      WalSyncDisplayState.syncing => 2,
      WalSyncDisplayState.uploaded => 1,
      WalSyncDisplayState.synced => 1,
      WalSyncDisplayState.waiting => 1,
    };

/// Max automatic sync attempts before a recording is considered
/// [WalSyncDisplayState.failed]. This is the budget itself, not a display
/// mirror: `isAutoUploadEligible` in local_wal_sync.dart drops a recording that
/// has spent it from every automatic drain, so the label and the behaviour
/// cannot drift apart. Only the per-recording manual Retry ignores it.
const int walMaxAutoRetries = 3;

/// Refused recordings one automatic drain may re-send. A day-long server bug can refuse
/// thousands; their daily recovery then spreads over later drains instead of firing every
/// single-file upload back to back (400s engage neither the 429 limiter nor the 5xx pause).
const int walMaxRefusalRetriesPerDrain = 25;

/// A recording young enough to still attach to a live conversation (matches
/// the backend's fresh-lane cutoff, `SYNC_FRESH_MAX_AGE_SECONDS`).
const int liveCaptureMaxAgeSeconds = 6 * 60 * 60;

bool isLiveCaptureWal(Wal wal, int nowSeconds) => nowSeconds - wal.timerStart <= liveCaptureMaxAgeSeconds;

class WalStats {
  final int totalFiles;
  final int phoneFiles;
  final int sdcardFiles;
  final int fromSdcardFiles;
  final int limitlessFiles;
  final int fromFlashPageFiles;
  final int phoneSize;
  final int sdcardSize;
  final int syncedFiles;
  final int missedFiles;

  WalStats({
    required this.totalFiles,
    required this.phoneFiles,
    required this.sdcardFiles,
    required this.fromSdcardFiles,
    required this.limitlessFiles,
    required this.fromFlashPageFiles,
    required this.phoneSize,
    required this.sdcardSize,
    required this.syncedFiles,
    required this.missedFiles,
  });

  int get sdcardRelatedFiles => sdcardFiles + fromSdcardFiles;
  int get flashPageRelatedFiles => limitlessFiles + fromFlashPageFiles;

  String get totalSizeFormatted => _formatBytes(phoneSize + sdcardSize);
  String get phoneSizeFormatted => _formatBytes(phoneSize);
  String get sdcardSizeFormatted => _formatBytes(sdcardSize);

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }
}

class Wal {
  /// Runtime ordinal from a validated index load, used to seed the index owner
  /// without sending or serializing the unchanged history back to it.
  int? loadedIndexToken;

  /// The exact file validated by the loader, including backup recovery.
  String? loadedIndexSource;

  // Persisted object fields follow replacement semantics (see persistentFingerprint).
  // Subscribers track identity: device timestamps and paths can change.
  final Set<void Function(Wal)> _changeListeners = {};
  final Set<void Function(Wal)> _viewChangeListeners = {};
  void addViewChangeListener(void Function(Wal) listener) => _viewChangeListeners.add(listener);
  void removeViewChangeListener(void Function(Wal) listener) => _viewChangeListeners.remove(listener);
  void _viewChanged() {
    for (final listener in _viewChangeListeners) {
      listener(this);
    }
  }

  void addChangeListener(void Function(Wal) listener) => _changeListeners.add(listener);
  void removeChangeListener(void Function(Wal) listener) => _changeListeners.remove(listener);
  void _changed() {
    _viewChanged();
    for (final listener in _changeListeners) {
      listener(this);
    }
  }

  int _timerStart;
  int get timerStart => _timerStart;
  set timerStart(int value) {
    if (_timerStart == value) return;
    _timerStart = value;
    _changed();
  }

  BleAudioCodec _codec;
  BleAudioCodec get codec => _codec;
  set codec(BleAudioCodec value) {
    if (_codec == value) return;
    _codec = value;
    _changed();
  }

  int _channel;
  int get channel => _channel;
  set channel(int value) {
    if (_channel == value) return;
    _channel = value;
    _changed();
  }

  int _sampleRate;
  int get sampleRate => _sampleRate;
  set sampleRate(int value) {
    if (_sampleRate == value) return;
    _sampleRate = value;
    _changed();
  }

  int _seconds;
  int get seconds => _seconds;
  set seconds(int value) {
    if (_seconds == value) return;
    _seconds = value;
    _changed();
  }

  String _device;
  String get device => _device;
  set device(String value) {
    if (_device == value) return;
    _device = value;
    _changed();
  }

  String? _deviceModel;
  String? get deviceModel => _deviceModel;
  set deviceModel(String? value) {
    if (_deviceModel == value) return;
    _deviceModel = value;
    _changed();
  }

  WalStatus _status;
  WalStatus get status => _status;
  set status(WalStatus value) {
    if (_status == value) return;
    _status = value;
    _changed();
  }

  WalStorage _storage;
  WalStorage get storage => _storage;
  set storage(WalStorage value) {
    if (_storage == value) return;
    _storage = value;
    _changed();
  }

  /// Explicit phone-only custody. Never admitted to a cloud audio drain.
  bool _onDeviceOnly;
  bool get onDeviceOnly => _onDeviceOnly;
  set onDeviceOnly(bool value) {
    if (_onDeviceOnly == value) return;
    _onDeviceOnly = value;
    _changed();
  }

  /// Explicit Transcribe Later consent: only a manual upload may release this hold.
  bool _holdForUser;
  bool get holdForUser => _holdForUser;
  set holdForUser(bool value) {
    if (_holdForUser == value) return;
    _holdForUser = value;
    _changed();
  }

  DeviceType? _deviceType;
  DeviceType? get deviceType => _deviceType;
  set deviceType(DeviceType? value) {
    if (_deviceType == value) return;
    _deviceType = value;
    _changed();
  }

  Map<String, dynamic>? _onDeviceConversation;
  Map<String, dynamic>? get onDeviceConversation => _onDeviceConversation;
  set onDeviceConversation(Map<String, dynamic>? value) {
    if (_onDeviceConversation == value) return;
    _onDeviceConversation = value;
    _changed();
  }

  /// Immutable continuation input, retained until conversation receipt is durable.
  Map<String, dynamic>? _onDevicePreparedUpload;
  Map<String, dynamic>? get onDevicePreparedUpload => _onDevicePreparedUpload;
  set onDevicePreparedUpload(Map<String, dynamic>? value) {
    if (_onDevicePreparedUpload == value) return;
    _onDevicePreparedUpload = value;
    _changed();
  }

  String? _onDeviceUploadFailure;
  String? get onDeviceUploadFailure => _onDeviceUploadFailure;
  set onDeviceUploadFailure(String? value) {
    if (_onDeviceUploadFailure == value) return;
    _onDeviceUploadFailure = value;
    _changed();
  }

  /// Recording-time custody evidence. Null identifies pre-fix dev records.
  bool? _capturedOnDeviceOnly;
  bool? get capturedOnDeviceOnly => _capturedOnDeviceOnly;
  set capturedOnDeviceOnly(bool? value) {
    if (_capturedOnDeviceOnly == value) return;
    _capturedOnDeviceOnly = value;
    _changed();
  }

  /// Imported device storage was never part of the phone's live STT route.
  /// Repair only the erroneous pre-fix stamp, preserving explicit capture consent.
  void repairLegacyImportedCustody() {
    if (capturedOnDeviceOnly == null &&
        onDeviceConversation == null &&
        (originalStorage == WalStorage.sdcard || originalStorage == WalStorage.flashPage)) {
      onDeviceOnly = false;
    }
  }

  String? _filePath;
  String? get filePath => _filePath;
  set filePath(String? value) {
    if (_filePath == value) return;
    _filePath = value;
    _changed();
  }

  List<List<int>> data;
  int _storageOffset = 0;
  int get storageOffset => _storageOffset;
  set storageOffset(int value) {
    if (_storageOffset == value) return;
    _storageOffset = value;
    _changed();
  }

  int _storageTotalBytes = 0;
  int get storageTotalBytes => _storageTotalBytes;
  set storageTotalBytes(int value) {
    if (_storageTotalBytes == value) return;
    _storageTotalBytes = value;
    _changed();
  }

  int _fileNum = 1;
  int get fileNum => _fileNum;
  set fileNum(int value) {
    if (_fileNum == value) return;
    _fileNum = value;
    _changed();
  }

  bool _isSyncing = false;
  bool get isSyncing => _isSyncing;
  set isSyncing(bool value) {
    if (_isSyncing == value) return;
    _isSyncing = value;
    _viewChanged();
  }

  DateTime? _syncStartedAt;
  DateTime? get syncStartedAt => _syncStartedAt;
  set syncStartedAt(DateTime? value) {
    if (_syncStartedAt == value) return;
    _syncStartedAt = value;
    _viewChanged();
  }

  int? _syncEtaSeconds;
  int? get syncEtaSeconds => _syncEtaSeconds;
  set syncEtaSeconds(int? value) {
    if (_syncEtaSeconds == value) return;
    _syncEtaSeconds = value;
    _viewChanged();
  }

  double? _syncSpeedKBps;
  double? get syncSpeedKBps => _syncSpeedKBps;
  set syncSpeedKBps(double? value) {
    if (_syncSpeedKBps == value) return;
    _syncSpeedKBps = value;
    _viewChanged();
  }

  /// 0..1 fraction of this recording's device transfer. Runtime only.
  /// Null when this recording is not the active device download.
  /// Zero means the transfer has started but no countable bytes have arrived.
  double? _deviceDownloadFraction;
  double? get deviceDownloadFraction => _deviceDownloadFraction;
  set deviceDownloadFraction(double? value) {
    if (_deviceDownloadFraction == value) return;
    _deviceDownloadFraction = value;
    _viewChanged();
  }

  SyncMethod syncMethod = SyncMethod.ble;

  int _frameSize = 160;
  int get frameSize => _frameSize;
  set frameSize(int value) {
    if (_frameSize == value) return;
    _frameSize = value;
    _changed();
  }

  int _totalFrames = 0;
  int get totalFrames => _totalFrames;
  set totalFrames(int value) {
    if (_totalFrames == value) return;
    _totalFrames = value;
    _changed();
  }

  int _syncedFrameOffset = 0;
  int get syncedFrameOffset => _syncedFrameOffset;
  set syncedFrameOffset(int value) {
    if (_syncedFrameOffset == value) return;
    _syncedFrameOffset = value;
    _changed();
  }

  WalStorage? _originalStorage;
  WalStorage? get originalStorage => _originalStorage;
  set originalStorage(WalStorage? value) {
    if (_originalStorage == value) return;
    _originalStorage = value;
    _changed();
  }

  /// The conversation this WAL belongs to. Stamped when ConversationProcessingStartedEvent
  /// arrives so WALs survive app kill and can be recovered on startup.
  String? _conversationId;
  String? get conversationId => _conversationId;
  set conversationId(String? value) {
    if (_conversationId == value) return;
    _conversationId = value;
    _changed();
  }

  /// Client recording id (`activeRecordingId` / `external_data.recording_session_id`).
  /// Stamped when the WAL is created so a safety copy that misses
  /// ConversationProcessingStarted can still bind to the live conversation.
  String? _recordingSessionId;
  String? get recordingSessionId => _recordingSessionId;
  set recordingSessionId(String? value) {
    if (_recordingSessionId == value) return;
    _recordingSessionId = value;
    _changed();
  }

  /// The account that created this recording, stamped from the signed-in uid
  /// at creation (or back-filled at logout). Loaded records owned by another
  /// account are parked durably instead of being loaded, so a session never
  /// renders or uploads another account's recordings after an account switch.
  /// Null on records written before this field existed (pre-upgrade data).
  String? _ownerUid;
  String? get ownerUid => _ownerUid;
  set ownerUid(String? value) {
    if (_ownerUid == value) return;
    _ownerUid = value;
    _changed();
  }

  String? _captureRoot;
  String? get captureRoot => _captureRoot;
  set captureRoot(String? value) {
    if (_captureRoot == value) return;
    _captureRoot = value;
    _changed();
  }

  int? _sourceFrameStart;
  int? get sourceFrameStart => _sourceFrameStart;
  set sourceFrameStart(int? value) {
    if (_sourceFrameStart == value) return;
    _sourceFrameStart = value;
    _changed();
  }

  int? _sourceClockEpoch;
  int? get sourceClockEpoch => _sourceClockEpoch;
  set sourceClockEpoch(int? value) {
    if (_sourceClockEpoch == value) return;
    _sourceClockEpoch = value;
    _changed();
  }

  int? _liveRingId;
  int? get liveRingId => _liveRingId;
  set liveRingId(int? value) {
    if (_liveRingId == value) return;
    _liveRingId = value;
    _changed();
  }

  int? _liveOrdinalStart;
  int? get liveOrdinalStart => _liveOrdinalStart;
  set liveOrdinalStart(int? value) {
    if (_liveOrdinalStart == value) return;
    _liveOrdinalStart = value;
    _changed();
  }

  int? _liveOrdinalEnd;
  int? get liveOrdinalEnd => _liveOrdinalEnd;
  set liveOrdinalEnd(int? value) {
    if (_liveOrdinalEnd == value) return;
    _liveOrdinalEnd = value;
    _changed();
  }

  int? liveConnectionEpoch;

  /// Canonical start-time location snapshot for delayed/offline finalization.
  Geolocation? _geolocation;
  Geolocation? get geolocation => _geolocation;
  set geolocation(Geolocation? value) {
    if (_geolocation == value) return;
    _geolocation = value;
    _changed();
  }

  /// Number of sync retry attempts for this WAL.
  int _retryCount;
  int get retryCount => _retryCount;
  set retryCount(int value) {
    if (_retryCount == value) return;
    _retryCount = value;
    _changed();
  }

  /// Unix timestamp (seconds) of the last sync retry attempt.
  int _lastRetryAt;
  int get lastRetryAt => _lastRetryAt;
  set lastRetryAt(int value) {
    if (_lastRetryAt == value) return;
    _lastRetryAt = value;
    _changed();
  }

  /// Server job id assigned when this recording's audio was uploaded (HTTP 202).
  /// The reconciler polls this to resolve [WalStatus.uploaded] → synced / miss /
  /// corrupted. Null until uploaded. Multiple WALs in one upload batch share it.
  String? _jobId;
  String? get jobId => _jobId;
  set jobId(String? value) {
    if (_jobId == value) return;
    _jobId = value;
    _changed();
  }

  /// Unix timestamp (seconds) when the audio was uploaded (202 received).
  int _uploadedAt;
  int get uploadedAt => _uploadedAt;
  set uploadedAt(int value) {
    if (_uploadedAt == value) return;
    _uploadedAt = value;
    _changed();
  }

  int _jobPendingConfirmedAt;
  int get jobPendingConfirmedAt => _jobPendingConfirmedAt;
  set jobPendingConfirmedAt(int value) {
    if (_jobPendingConfirmedAt == value) return;
    _jobPendingConfirmedAt = value;
    _changed();
  }

  /// Unix timestamp (seconds) when the server confirmed this recording synced
  /// (job resolved to [WalStatus.synced], or the live-stream ack completed it).
  /// 0 = unknown: records synced before this field existed, and WALs whose
  /// status was migrated without a timestamp. The synced-copy auto-remove
  /// policy deliberately skips records with 0 — never delete on unknown age.
  int _syncedAt;
  int get syncedAt => _syncedAt;
  set syncedAt(int value) {
    if (_syncedAt == value) return;
    _syncedAt = value;
    _changed();
  }

  bool _keptForTranscriptRecovery;
  bool get keptForTranscriptRecovery => _keptForTranscriptRecovery;
  set keptForTranscriptRecovery(bool value) {
    if (_keptForTranscriptRecovery == value) return;
    _keptForTranscriptRecovery = value;
    _changed();
  }

  /// Set only when [timerStart] is an app estimate (the device gave no
  /// trustworthy recording time): names the one contiguous device recording
  /// this audio belongs to. The upload filename carries it so the backend
  /// never merges it with audio outside that run by invented adjacency.
  String? _clockRun;
  String? get clockRun => _clockRun;
  set clockRun(String? value) {
    if (_clockRun == value) return;
    _clockRun = value;
    _changed();
  }

  /// Why the server refused the last upload attempt, as a bounded
  /// [WalUploadRejection] token; null when the row was never refused.
  String? _uploadRejectionReason;
  String? get uploadRejectionReason => _uploadRejectionReason;
  set uploadRejectionReason(String? value) {
    if (_uploadRejectionReason == value) return;
    _uploadRejectionReason = value;
    _changed();
  }

  int _uploadRejectionStatusCode;
  int get uploadRejectionStatusCode => _uploadRejectionStatusCode;
  set uploadRejectionStatusCode(int value) {
    if (_uploadRejectionStatusCode == value) return;
    _uploadRejectionStatusCode = value;
    _changed();
  }

  int _uploadRejectedAt;
  int get uploadRejectedAt => _uploadRejectedAt;
  set uploadRejectedAt(int value) {
    if (_uploadRejectedAt == value) return;
    _uploadRejectedAt = value;
    _changed();
  }

  int _uploadRefusalLastAttemptAt;
  int get uploadRefusalLastAttemptAt => _uploadRefusalLastAttemptAt;
  set uploadRefusalLastAttemptAt(int value) {
    if (_uploadRefusalLastAttemptAt == value) return;
    _uploadRefusalLastAttemptAt = value;
    _changed();
  }

  /// Daily recovery is independent of the transient network retry budget.
  /// Old indexes get a new seven-day window on their first recovery pass.
  /// Refusals fixed by the bytes themselves (size, part count) never succeed on a resend.
  bool refusalRetryDue(int nowSeconds) =>
      status == WalStatus.uploadRejected &&
      uploadRejectionReason != WalUploadRejection.tooLarge &&
      uploadRejectionReason != WalUploadRejection.tooManyParts &&
      (uploadRejectedAt == 0 || nowSeconds < uploadRejectedAt + 7 * 86400) &&
      (uploadRefusalLastAttemptAt == 0 || nowSeconds >= uploadRefusalLastAttemptAt + 86400);

  bool refusalReported(int nowSeconds) =>
      status == WalStatus.uploadRejected && uploadRejectedAt > 0 && nowSeconds >= uploadRejectedAt + 7 * 86400;

  String get id => '${device}_$timerStart';

  /// Single source of truth for how this recording's sync state is shown to the
  /// user. The sync page renders an explicit label + icon for every value so a
  /// not-yet-synced recording is never visually identical to a failed one.
  WalSyncDisplayState get syncDisplayState {
    // Corruption and a server lookback rejection are terminal. Neither must be
    // visually downgraded to an active upload if a transient flag was left
    // behind by an interrupted attempt.
    if (status == WalStatus.corrupted) return WalSyncDisplayState.corrupted;
    if (status == WalStatus.outsideRecoveryWindow) return WalSyncDisplayState.outsideRecoveryWindow;
    if (status == WalStatus.unsupportedAudio) return WalSyncDisplayState.unsupportedAudio;
    if (status == WalStatus.uploadRejected) return WalSyncDisplayState.uploadRejected;
    if (isSyncing) return WalSyncDisplayState.syncing;
    switch (status) {
      case WalStatus.uploaded:
        return WalSyncDisplayState.uploaded;
      case WalStatus.synced:
        return WalSyncDisplayState.synced;
      case WalStatus.corrupted:
        return WalSyncDisplayState.corrupted;
      case WalStatus.outsideRecoveryWindow:
        return WalSyncDisplayState.outsideRecoveryWindow;
      case WalStatus.unsupportedAudio:
        return WalSyncDisplayState.unsupportedAudio;
      case WalStatus.uploadRejected:
        return WalSyncDisplayState.uploadRejected;
      case WalStatus.miss:
        if (retryCount >= walMaxAutoRetries) return WalSyncDisplayState.failed;
        if (retryCount > 0) return WalSyncDisplayState.retrying;
        return WalSyncDisplayState.waiting;
      case WalStatus.inProgress:
        return WalSyncDisplayState.waiting;
    }
  }

  /// Marks this recording as terminally unavailable and clears any transient
  /// upload presentation left by an interrupted attempt.
  void markCorrupted() {
    status = WalStatus.corrupted;
    isSyncing = false;
    syncStartedAt = null;
    syncEtaSeconds = null;
    syncSpeedKBps = null;
  }

  /// Marks this recording as permanently refused by the server for being older
  /// than the automatic-recovery window. The local file is deliberately kept —
  /// only the sync attempt is terminal.
  void markOutsideRecoveryWindow() {
    status = WalStatus.outsideRecoveryWindow;
    isSyncing = false;
    syncStartedAt = null;
    syncEtaSeconds = null;
    syncSpeedKBps = null;
  }

  /// Marks this recording as permanently unreadable by the server's transcription
  /// job. Like [markOutsideRecoveryWindow] the local file is kept and only the
  /// sync attempt is terminal; the job id is dropped because it has been resolved.
  void markUnsupportedAudio() {
    status = WalStatus.unsupportedAudio;
    jobId = null;
    isSyncing = false;
    syncStartedAt = null;
    syncEtaSeconds = null;
    syncSpeedKBps = null;
  }

  /// Retains refused bytes and the closed reason with a durable daily retry
  /// clock. Connectivity changes and manual gestures cannot reset this clock.
  void markUploadRejected({String? reasonCode, int statusCode = 400, int? nowSeconds}) {
    status = WalStatus.uploadRejected;
    uploadRejectionReason = WalUploadRejection.bounded(reasonCode);
    uploadRejectionStatusCode = statusCode;
    final now = nowSeconds ?? DateTime.now().millisecondsSinceEpoch ~/ 1000;
    if (uploadRejectedAt == 0) uploadRejectedAt = now;
    uploadRefusalLastAttemptAt = now;
    jobId = null;
    isSyncing = false;
    syncStartedAt = null;
    syncEtaSeconds = null;
    syncSpeedKBps = null;
  }

  /// Fresh budget for transient failures. Refusals use their separate clock.
  void prepareManualRetry() {
    retryCount = 0;
    lastRetryAt = 0;
  }

  Wal({
    required int timerStart,
    required BleAudioCodec codec,
    required int seconds,
    int sampleRate = 16000,
    int channel = 1,
    WalStatus status = WalStatus.inProgress,
    WalStorage storage = WalStorage.mem,
    bool onDeviceOnly = false,
    bool holdForUser = false,
    DeviceType? deviceType,
    Map<String, dynamic>? onDeviceConversation,
    Map<String, dynamic>? onDevicePreparedUpload,
    String? onDeviceUploadFailure,
    bool? capturedOnDeviceOnly,
    String? filePath,
    String device = "phone",
    String? deviceModel,
    int storageOffset = 0,
    int storageTotalBytes = 0,
    int fileNum = 1,
    List<List<int>>? data,
    int totalFrames = 0,
    int syncedFrameOffset = 0,
    WalStorage? originalStorage,
    String? conversationId,
    String? recordingSessionId,
    String? ownerUid,
    String? captureRoot,
    int? sourceFrameStart,
    int? sourceClockEpoch,
    int? liveRingId,
    int? liveOrdinalStart,
    int? liveOrdinalEnd,
    Geolocation? geolocation,
    int retryCount = 0,
    int lastRetryAt = 0,
    String? jobId,
    int uploadedAt = 0,
    int jobPendingConfirmedAt = 0,
    int syncedAt = 0,
    bool keptForTranscriptRecovery = false,
    String? clockRun,
    String? uploadRejectionReason,
    int uploadRejectionStatusCode = 400,
    int uploadRejectedAt = 0,
    int uploadRefusalLastAttemptAt = 0,
  })  : _timerStart = timerStart,
        _codec = codec,
        _seconds = seconds,
        _sampleRate = sampleRate,
        _channel = channel,
        _status = status,
        _storage = storage,
        _onDeviceOnly = onDeviceOnly,
        _holdForUser = holdForUser,
        _deviceType = deviceType,
        _onDeviceConversation = onDeviceConversation,
        _onDevicePreparedUpload = onDevicePreparedUpload,
        _onDeviceUploadFailure = onDeviceUploadFailure,
        _capturedOnDeviceOnly = capturedOnDeviceOnly,
        _filePath = filePath,
        _device = device,
        _deviceModel = deviceModel,
        _storageOffset = storageOffset,
        _storageTotalBytes = storageTotalBytes,
        _fileNum = fileNum,
        _totalFrames = totalFrames,
        _syncedFrameOffset = syncedFrameOffset,
        _originalStorage = originalStorage,
        _conversationId = conversationId,
        _recordingSessionId = recordingSessionId,
        _ownerUid = ownerUid,
        _captureRoot = captureRoot,
        _sourceFrameStart = sourceFrameStart,
        _sourceClockEpoch = sourceClockEpoch,
        _liveRingId = liveRingId,
        _liveOrdinalStart = liveOrdinalStart,
        _liveOrdinalEnd = liveOrdinalEnd,
        _geolocation = geolocation,
        _retryCount = retryCount,
        _lastRetryAt = lastRetryAt,
        _jobId = jobId,
        _uploadedAt = uploadedAt,
        _jobPendingConfirmedAt = jobPendingConfirmedAt,
        _syncedAt = syncedAt,
        _keptForTranscriptRecovery = keptForTranscriptRecovery,
        _clockRun = clockRun,
        _uploadRejectionReason = uploadRejectionReason,
        _uploadRejectionStatusCode = uploadRejectionStatusCode,
        _uploadRejectedAt = uploadRejectedAt,
        _uploadRefusalLastAttemptAt = uploadRefusalLastAttemptAt,
        data = data ?? [] {
    frameSize = codec.getFrameSize();
  }

  factory Wal.fromJson(Map<String, dynamic> json) {
    return Wal(
      timerStart: json['timer_start'],
      codec: mapNameToCodec(json['codec']),
      channel: json['channel'] ?? 1,
      sampleRate: json['sample_rate'] ?? 16000,
      status: WalStatus.values.asNameMap()[json['status']] ?? WalStatus.inProgress,
      storage: WalStorage.values.asNameMap()[json['storage']] ?? WalStorage.mem,
      onDeviceOnly: json['on_device_only'] == true,
      holdForUser: json['hold_for_user'] == true,
      deviceType: DeviceType.values.asNameMap()[json['device_type']],
      onDeviceConversation:
          json['on_device_conversation'] is Map ? Map<String, dynamic>.from(json['on_device_conversation']) : null,
      onDeviceUploadFailure: json['on_device_upload_failure'] as String?,
      onDevicePreparedUpload: json['on_device_prepared_upload'] is Map
          ? Map<String, dynamic>.from(json['on_device_prepared_upload'] as Map)
          : null,
      capturedOnDeviceOnly: json['captured_on_device_only'] as bool?,
      filePath: json['file_path'],
      seconds: json['seconds'] ?? chunkSizeInSeconds,
      device: json['device'] ?? "phone",
      deviceModel: json['device_model'],
      storageOffset: json['storage_offset'] ?? 0,
      storageTotalBytes: json['storage_total_bytes'] ?? 0,
      fileNum: json['file_num'] ?? 1,
      totalFrames: json['total_frames'] ?? 0,
      syncedFrameOffset: json['synced_frame_offset'] ?? 0,
      originalStorage:
          json['original_storage'] != null ? WalStorage.values.asNameMap()[json['original_storage']] : null,
      conversationId: json['conversation_id'],
      recordingSessionId: json['recording_session_id'],
      ownerUid: json['owner_uid'],
      captureRoot: json['capture_root'],
      sourceFrameStart: json['source_frame_start'],
      sourceClockEpoch: json['source_clock_epoch'],
      liveRingId: json['live_ring_id'],
      liveOrdinalStart: json['live_ordinal_start'],
      liveOrdinalEnd: json['live_ordinal_end'],
      geolocation: json['geolocation'] is Map<String, dynamic>
          ? Geolocation.fromJson(json['geolocation'] as Map<String, dynamic>)
          : null,
      retryCount: json['retry_count'] ?? 0,
      lastRetryAt: json['last_retry_at'] ?? 0,
      jobId: json['job_id'],
      uploadedAt: json['uploaded_at'] ?? 0,
      jobPendingConfirmedAt: json['job_pending_confirmed_at'] ?? 0,
      syncedAt: json['synced_at'] ?? 0,
      keptForTranscriptRecovery: json['kept_for_transcript_recovery'] == true,
      clockRun: json['clock_run'] as String?,
      uploadRejectionReason: json['upload_rejection_reason'] == null
          ? null
          : WalUploadRejection.bounded(json['upload_rejection_reason'] as String?),
      uploadRejectionStatusCode: json['upload_rejection_status_code'] ?? 400,
      uploadRejectedAt: json['upload_rejected_at'] ?? 0,
      uploadRefusalLastAttemptAt: json['upload_refusal_last_attempt_at'] ?? 0,
    )
      ..frameSize = json['frame_size'] ?? mapNameToCodec(json['codec']).getFrameSize()
      ..repairLegacyImportedCustody();
  }

  Map<String, dynamic> toJson() {
    return {
      'timer_start': timerStart,
      'codec': codec.toString(),
      'channel': channel,
      'sample_rate': sampleRate,
      'status': status.name,
      'storage': storage.name,
      'on_device_only': onDeviceOnly,
      'hold_for_user': holdForUser,
      if (deviceType != null) 'device_type': deviceType!.name,
      'on_device_conversation': onDeviceConversation,
      if (onDevicePreparedUpload != null) 'on_device_prepared_upload': onDevicePreparedUpload,
      if (onDeviceUploadFailure != null) 'on_device_upload_failure': onDeviceUploadFailure,
      if (capturedOnDeviceOnly != null) 'captured_on_device_only': capturedOnDeviceOnly,
      'file_path': filePath,
      'seconds': seconds,
      'device': device,
      'device_model': deviceModel,
      'storage_offset': storageOffset,
      'storage_total_bytes': storageTotalBytes,
      'file_num': fileNum,
      'total_frames': totalFrames,
      'frame_size': frameSize,
      'synced_frame_offset': syncedFrameOffset,
      'original_storage': originalStorage?.name,
      'conversation_id': conversationId,
      'recording_session_id': recordingSessionId,
      'owner_uid': ownerUid,
      if (captureRoot != null) 'capture_root': captureRoot,
      if (sourceFrameStart != null) 'source_frame_start': sourceFrameStart,
      if (sourceClockEpoch != null) 'source_clock_epoch': sourceClockEpoch,
      if (liveRingId != null) 'live_ring_id': liveRingId,
      if (liveOrdinalStart != null) 'live_ordinal_start': liveOrdinalStart,
      if (liveOrdinalEnd != null) 'live_ordinal_end': liveOrdinalEnd,
      'geolocation': geolocation?.toJson(),
      'retry_count': retryCount,
      'last_retry_at': lastRetryAt,
      'job_id': jobId,
      'uploaded_at': uploadedAt,
      'job_pending_confirmed_at': jobPendingConfirmedAt,
      'synced_at': syncedAt,
      if (keptForTranscriptRecovery) 'kept_for_transcript_recovery': true,
      if (clockRun != null) 'clock_run': clockRun,
      if (uploadRejectionReason != null) 'upload_rejection_reason': uploadRejectionReason,
      'upload_rejection_status_code': uploadRejectionStatusCode,
      'upload_rejected_at': uploadRejectedAt,
      'upload_refusal_last_attempt_at': uploadRefusalLastAttemptAt,
    };
  }

  static List<Wal> fromJsonList(List<dynamic> jsonList) => jsonList.map((e) => Wal.fromJson(e)).toList();

  /// Cheap change signal over exactly the fields [toJson] persists, so a save
  /// whose snapshot did not change can skip re-encoding the whole index. Every
  /// scalar and enum field mixes its value; string fields mix their content
  /// hash; the three replaced-never-mutated object fields
  /// ([onDeviceConversation], [onDevicePreparedUpload], [geolocation]) mix
  /// instance identity. Runtime-only fields (isSyncing, transfer progress) are
  /// deliberately absent, like [toJson] itself. A new persisted field must be
  /// added here together with toJson, or its changes could be skipped.
  int get persistentFingerprint {
    var h = timerStart;
    h = _mixFingerprint(h, codec.index);
    h = _mixFingerprint(h, channel);
    h = _mixFingerprint(h, sampleRate);
    h = _mixFingerprint(h, status.index);
    h = _mixFingerprint(h, storage.index);
    h = _mixFingerprint(h, onDeviceOnly ? 1 : 0);
    h = _mixFingerprint(h, holdForUser ? 1 : 0);
    h = _mixFingerprint(h, deviceType?.index ?? -1);
    h = _mixFingerprint(h, identityHashCode(onDeviceConversation));
    h = _mixFingerprint(h, identityHashCode(onDevicePreparedUpload));
    h = _mixFingerprint(h, onDeviceUploadFailure?.hashCode ?? 0);
    h = _mixFingerprint(h, capturedOnDeviceOnly == null ? -1 : (capturedOnDeviceOnly! ? 1 : 0));
    h = _mixFingerprint(h, filePath?.hashCode ?? 0);
    h = _mixFingerprint(h, seconds);
    h = _mixFingerprint(h, device.hashCode);
    h = _mixFingerprint(h, deviceModel?.hashCode ?? 0);
    h = _mixFingerprint(h, storageOffset);
    h = _mixFingerprint(h, storageTotalBytes);
    h = _mixFingerprint(h, fileNum);
    h = _mixFingerprint(h, totalFrames);
    h = _mixFingerprint(h, frameSize);
    h = _mixFingerprint(h, syncedFrameOffset);
    h = _mixFingerprint(h, originalStorage?.index ?? -1);
    h = _mixFingerprint(h, conversationId?.hashCode ?? 0);
    h = _mixFingerprint(h, recordingSessionId?.hashCode ?? 0);
    h = _mixFingerprint(h, ownerUid?.hashCode ?? 0);
    h = _mixFingerprint(h, captureRoot?.hashCode ?? 0);
    h = _mixFingerprint(h, sourceFrameStart ?? -1);
    h = _mixFingerprint(h, sourceClockEpoch ?? -1);
    h = _mixFingerprint(h, liveRingId ?? -1);
    h = _mixFingerprint(h, liveOrdinalStart ?? -1);
    h = _mixFingerprint(h, liveOrdinalEnd ?? -1);
    h = _mixFingerprint(h, identityHashCode(geolocation));
    h = _mixFingerprint(h, retryCount);
    h = _mixFingerprint(h, lastRetryAt);
    h = _mixFingerprint(h, jobId?.hashCode ?? 0);
    h = _mixFingerprint(h, uploadedAt);
    h = _mixFingerprint(h, jobPendingConfirmedAt);
    h = _mixFingerprint(h, syncedAt);
    h = _mixFingerprint(h, keptForTranscriptRecovery ? 1 : 0);
    h = _mixFingerprint(h, clockRun?.hashCode ?? 0);
    h = _mixFingerprint(h, uploadRejectionReason?.hashCode ?? 0);
    h = _mixFingerprint(h, uploadRejectionStatusCode);
    h = _mixFingerprint(h, uploadRejectedAt);
    h = _mixFingerprint(h, uploadRefusalLastAttemptAt);
    return h;
  }

  /// Order-sensitive fingerprint of a persisted index snapshot, so a caller
  /// that rewrites the index can tell an unchanged snapshot from a changed one
  /// without re-encoding it.
  static int persistedIndexFingerprint(List<Wal> wals) {
    var h = wals.length;
    for (final wal in wals) {
      h = _mixFingerprint(h, wal.persistentFingerprint);
    }
    return h;
  }

  static int _mixFingerprint(int h, int v) => (h * 31 + v) & 0x3FFFFFFF;

  getFileName() {
    return getFileNameByTimeStarts(timerStart, clockRun: clockRun);
  }

  /// `_clke<run>` sits directly before the timestamp: older backends read only
  /// `_fs<n>` and the trailing part, so they ignore it.
  getFileNameByTimeStarts(int timestarts, {String? clockRun}) {
    final clock = clockRun == null ? '' : '_clke$clockRun';
    return "audio_${device.replaceAll(RegExp(r'[^a-zA-Z0-9]'), "").toLowerCase()}_${codec}_${sampleRate}_${channel}_fs$frameSize${clock}_$timestarts.bin";
  }

  /// A fresh run name for audio whose recording time the app had to estimate.
  static String newClockRun() {
    final random = Random.secure();
    return List.generate(12, (_) => '0123456789abcdefghijklmnopqrstuvwxyz'[random.nextInt(36)]).join();
  }

  static Future<String?> getFilePath(String? pathOrName) async {
    if (pathOrName == null || pathOrName.isEmpty) {
      return null;
    }

    final directory = await getApplicationDocumentsDirectory();
    if (pathOrName.contains('/')) {
      final filename = pathOrName.split('/').last;
      return '${directory.path}/$filename';
    }
    return '${directory.path}/$pathOrName';
  }
}

/// Refusals are operator feedback: no per-recording gesture can repair them.
class WalRefusalSummary {
  const WalRefusalSummary({required this.count, required this.seconds, required this.reportedCount});
  final int count;
  final int seconds;
  final int reportedCount;
  bool get userActionCanHelp => false;

  factory WalRefusalSummary.from(Iterable<Wal> wals, {int? nowSeconds}) {
    final now = nowSeconds ?? DateTime.now().millisecondsSinceEpoch ~/ 1000;
    var count = 0, seconds = 0, reported = 0;
    for (final wal in wals) {
      if (wal.status != WalStatus.uploadRejected) continue;
      count++;
      seconds += max(0, wal.seconds);
      if (wal.refusalReported(now)) reported++;
    }
    return WalRefusalSummary(count: count, seconds: seconds, reportedCount: reported);
  }
}
