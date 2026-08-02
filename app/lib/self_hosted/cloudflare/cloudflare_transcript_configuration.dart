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

  bool get isConfigured {
    final uri = Uri.tryParse(workerUrl.trim());
    return token.trim().isNotEmpty && uri != null && isValidWorkerUri(uri);
  }

  Uri get baseUri {
    final uri = Uri.tryParse(workerUrl.trim());
    if (uri == null || !isValidWorkerUri(uri)) {
      throw const CloudflareTranscriptConfigurationException(
          'Worker URL must be HTTPS or loopback HTTP without credentials, query, or fragment.');
    }
    return uri.replace(path: uri.path.replaceFirst(RegExp(r'/+$'), ''));
  }

  static bool isValidWorkerUri(Uri uri) {
    return isAllowedScheme(uri) &&
        uri.hasAuthority &&
        uri.host.isNotEmpty &&
        uri.userInfo.isEmpty &&
        uri.query.isEmpty &&
        uri.fragment.isEmpty;
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
