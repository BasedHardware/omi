class CloudflareTranscriptApiException implements Exception {
  const CloudflareTranscriptApiException(this.message);
  const CloudflareTranscriptApiException.malformedTranscriptChunk()
      : message = 'Worker response contains a malformed transcript chunk.';
  const CloudflareTranscriptApiException.transportFailure() : message = 'Worker request failed.';

  final String message;

  @override
  String toString() => message;
}
