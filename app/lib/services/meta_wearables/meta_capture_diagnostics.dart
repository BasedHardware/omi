class MetaCaptureDiagnostics {
  final DateTime? lastFrameAt;
  final DateTime? lastUploadAt;
  final String? lastUploadStatus;
  final String? streamState;
  final String? sessionState;
  final int pendingQueueCount;
  final int uploadedCount;
  final int failedUploadCount;

  const MetaCaptureDiagnostics({
    this.lastFrameAt,
    this.lastUploadAt,
    this.lastUploadStatus,
    this.streamState,
    this.sessionState,
    this.pendingQueueCount = 0,
    this.uploadedCount = 0,
    this.failedUploadCount = 0,
  });

  /// Sentinel distinguishing "not passed" from an explicit null, so callers
  /// can clear nullable fields (`copyWith(lastUploadStatus: null)`).
  static const Object _unset = Object();

  MetaCaptureDiagnostics copyWith({
    Object? lastFrameAt = _unset,
    Object? lastUploadAt = _unset,
    Object? lastUploadStatus = _unset,
    Object? streamState = _unset,
    Object? sessionState = _unset,
    int? pendingQueueCount,
    int? uploadedCount,
    int? failedUploadCount,
  }) =>
      MetaCaptureDiagnostics(
        lastFrameAt: identical(lastFrameAt, _unset) ? this.lastFrameAt : lastFrameAt as DateTime?,
        lastUploadAt: identical(lastUploadAt, _unset) ? this.lastUploadAt : lastUploadAt as DateTime?,
        lastUploadStatus: identical(lastUploadStatus, _unset) ? this.lastUploadStatus : lastUploadStatus as String?,
        streamState: identical(streamState, _unset) ? this.streamState : streamState as String?,
        sessionState: identical(sessionState, _unset) ? this.sessionState : sessionState as String?,
        pendingQueueCount: pendingQueueCount ?? this.pendingQueueCount,
        uploadedCount: uploadedCount ?? this.uploadedCount,
        failedUploadCount: failedUploadCount ?? this.failedUploadCount,
      );

  Map<String, dynamic> toJson() => {
        'lastFrameAt': lastFrameAt?.toIso8601String(),
        'lastUploadAt': lastUploadAt?.toIso8601String(),
        'lastUploadStatus': lastUploadStatus,
        'streamState': streamState,
        'sessionState': sessionState,
        'pendingQueueCount': pendingQueueCount,
        'uploadedCount': uploadedCount,
        'failedUploadCount': failedUploadCount,
      };
}
