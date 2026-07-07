class HardSecretDetection {
  final String category;
  final int start;
  final int end;

  const HardSecretDetection({required this.category, required this.start, required this.end});
}

class HardSecretDetector {
  static final List<({String category, RegExp pattern})> _patterns = [
    (
      category: 'private_key',
      pattern: RegExp(r'-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+|DSA\s+)?PRIVATE\s+KEY-----', caseSensitive: false),
    ),
    (
      category: 'database_url',
      pattern: RegExp(
        r"""\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis)://[^\s<>"']{12,}""",
        caseSensitive: false,
      ),
    ),
    (
      category: 'api_key',
      pattern: RegExp(r'\b(?:sk[-_][A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})\b', caseSensitive: true),
    ),
    (
      category: 'token',
      pattern: RegExp(
        r"""\b(?:(?:access[_-]?|auth[_-]?|refresh[_-]?)?token\b\s*[:=]\s*["']?|authorization\b\s*:\s*bearer\s+|bearer\b\s+)[A-Za-z0-9._~+/=-]{16,}""",
        caseSensitive: false,
      ),
    ),
    (
      category: 'password',
      pattern: RegExp(r"""\b(?:password|passwd|pwd)\b\s*[:=]\s*["']?[^"'\s]{8,}""", caseSensitive: false),
    ),
    (
      category: 'cookie',
      pattern: RegExp(
        r"""\b(?:cookie|session(?:id)?|sid)\b\s*[:=]\s*["']?[A-Za-z0-9._~+/=-]{16,}""",
        caseSensitive: false,
      ),
    ),
  ];

  static List<HardSecretDetection> detections(String text) {
    final hits = <HardSecretDetection>[];
    for (final candidate in _patterns) {
      for (final match in candidate.pattern.allMatches(text)) {
        hits.add(HardSecretDetection(category: candidate.category, start: match.start, end: match.end));
      }
    }
    hits.sort((a, b) {
      final byStart = a.start.compareTo(b.start);
      if (byStart != 0) return byStart;
      return a.category.compareTo(b.category);
    });
    return hits;
  }

  static bool contains(String text) => detections(text).isNotEmpty;

  static List<String> categories(String text) {
    final values = detections(text).map((detection) => detection.category).toSet().toList();
    values.sort();
    return values;
  }
}
