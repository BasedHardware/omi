class AppleSpeechReadiness {
  final String engine;
  final String status;
  const AppleSpeechReadiness(this.engine, this.status);
  bool get ready => status == 'ready';
  factory AppleSpeechReadiness.fromMap(Map<String, dynamic>? data) =>
      AppleSpeechReadiness(data?['engine'] as String? ?? 'unknown', data?['status'] as String? ?? 'unavailable');
}
