class CloudflareTranscriptConfiguration {
  const CloudflareTranscriptConfiguration({
    required this.workerUrl,
    required this.token,
  });

  factory CloudflareTranscriptConfiguration.fromEnvironment() {
    return const CloudflareTranscriptConfiguration(
      workerUrl: String.fromEnvironment('BRAINBASE_SELF_HOSTED_WORKER_URL'),
      token: String.fromEnvironment('BRAINBASE_SELF_HOSTED_WORKER_TOKEN'),
    );
  }

  final String workerUrl;
  final String token;

  bool get isConfigured => workerUrl.trim().isNotEmpty && token.trim().isNotEmpty;

  Uri get baseUri {
    final uri = Uri.tryParse(workerUrl.trim());
    if (uri == null ||
        !uri.hasAuthority ||
        uri.userInfo.isNotEmpty ||
        uri.query.isNotEmpty ||
        uri.fragment.isNotEmpty ||
        !isAllowedScheme(uri)) {
      throw const CloudflareTranscriptConfigurationException('Worker URL must be HTTPS or loopback HTTP.');
    }
    return uri.replace(path: uri.path.replaceFirst(RegExp(r'/+$'), ''));
  }

  static bool isAllowedScheme(Uri uri) {
    if (uri.scheme == 'https') return true;
    if (uri.scheme != 'http') return false;
    return uri.host == 'localhost' || uri.host == '127.0.0.1' || uri.host == '::1';
  }
}

class CloudflareTranscriptConfigurationException implements Exception {
  const CloudflareTranscriptConfigurationException(this.message);

  final String message;

  @override
  String toString() => message;
}
