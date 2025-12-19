import 'dart:convert';

extension StringExtensions on String {
  String get decodeString {
    try {
      return utf8.decode(codeUnits);
    } on Exception catch (_) {
      return this;
    }
  }

  String capitalize() {
    return isNotEmpty ? '${this[0].toUpperCase()}${substring(1)}' : '';
  }

  /// Strips markdown formatting for plain text previews
  /// Removes headers (##), bold (**), bullets (-), emojis in headers, etc.
  String get stripMarkdownForPreview {
    String result = this;
    
    // Remove markdown headers (## Title -> Title)
    result = result.replaceAll(RegExp(r'^#{1,6}\s*', multiLine: true), '');
    
    // Remove bold/italic markers
    result = result.replaceAll(RegExp(r'\*\*([^*]+)\*\*'), r'$1');
    result = result.replaceAll(RegExp(r'\*([^*]+)\*'), r'$1');
    result = result.replaceAll(RegExp(r'__([^_]+)__'), r'$1');
    result = result.replaceAll(RegExp(r'_([^_]+)_'), r'$1');
    
    // Remove bullet point markers
    result = result.replaceAll(RegExp(r'^\s*[-•]\s*', multiLine: true), '');
    
    // Remove emojis that are commonly used in headers (keep content emojis)
    // Just remove common header emojis: 📋 🌤 💬 ✅ 💡 👥
    result = result.replaceAll(RegExp(r'[📋🌤💬✅💡👥]\s*'), '');
    
    // Collapse multiple newlines to single space
    result = result.replaceAll(RegExp(r'\n+'), ' ');
    
    // Collapse multiple spaces to single space
    result = result.replaceAll(RegExp(r'\s+'), ' ');
    
    return result.trim();
  }
}
