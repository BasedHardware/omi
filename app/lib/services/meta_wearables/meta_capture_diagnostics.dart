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

  MetaCaptureDiagnostics copyWith({
    DateTime? lastFrameAt,
    DateTime? lastUploadAt,
    String? lastUploadStatus,
    String? streamState,
    String? sessionState,
    int? pendingQueueCount,
    int? uploadedCount,
    int? failedUploadCount,
  }) =>
      MetaCaptureDiagnostics(
        lastFrameAt: lastFrameAt ?? this.lastFrameAt,
        lastUploadAt: lastUploadAt ?? this.lastUploadAt,
        lastUploadStatus: lastUploadStatus ?? this.lastUploadStatus,
        streamState: streamState ?? this.streamState,
        sessionState: sessionState ?? this.sessionState,
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
