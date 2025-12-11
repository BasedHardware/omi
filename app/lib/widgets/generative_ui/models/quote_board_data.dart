import 'package:flutter/material.dart';

/// Record status for quotes
enum QuoteRecordStatus {
  onTheRecord,
  background,
  offTheRecord,
  unclear;

  static QuoteRecordStatus fromString(String? status) {
    if (status == null) return QuoteRecordStatus.unclear;
    final normalized = status.toLowerCase().replaceAll(' ', '').replaceAll('_', '');
    switch (normalized) {
      case 'ontherecord':
        return QuoteRecordStatus.onTheRecord;
      case 'background':
        return QuoteRecordStatus.background;
      case 'offtherecord':
        return QuoteRecordStatus.offTheRecord;
      default:
        return QuoteRecordStatus.unclear;
    }
  }

  String get displayName {
    switch (this) {
      case QuoteRecordStatus.onTheRecord:
        return 'On the record';
      case QuoteRecordStatus.background:
        return 'Background';
      case QuoteRecordStatus.offTheRecord:
        return 'Off the record';
      case QuoteRecordStatus.unclear:
        return 'Unclear';
    }
  }

  Color get color {
    switch (this) {
      case QuoteRecordStatus.onTheRecord:
        return const Color(0xFF22C55E); // Green
      case QuoteRecordStatus.background:
        return const Color(0xFFF59E0B); // Amber/Yellow
      case QuoteRecordStatus.offTheRecord:
        return const Color(0xFFEF4444); // Red
      case QuoteRecordStatus.unclear:
        return const Color(0xFF6B7280); // Gray
    }
  }

  Color get backgroundColor {
    switch (this) {
      case QuoteRecordStatus.onTheRecord:
        return const Color(0xFF22C55E).withOpacity(0.15);
      case QuoteRecordStatus.background:
        return const Color(0xFFF59E0B).withOpacity(0.15);
      case QuoteRecordStatus.offTheRecord:
        return const Color(0xFFEF4444).withOpacity(0.15);
      case QuoteRecordStatus.unclear:
        return const Color(0xFF6B7280).withOpacity(0.15);
    }
  }
}

/// Data model for a single quote
class QuoteData {
  final String speaker;
  final String time;
  final QuoteRecordStatus recordStatus;
  final String quote;

  const QuoteData({
    required this.speaker,
    required this.time,
    required this.recordStatus,
    required this.quote,
  });

  factory QuoteData.fromParsed({
    required Map<String, String> attributes,
    required String innerContent,
  }) {
    return QuoteData(
      speaker: attributes['speaker'] ?? 'Unknown',
      time: attributes['time'] ?? '',
      recordStatus: QuoteRecordStatus.fromString(attributes['record']),
      quote: innerContent.trim(),
    );
  }
}

/// Data model for the entire quote board component
class QuoteBoardDisplayData {
  final List<QuoteData> quotes;

  const QuoteBoardDisplayData({
    required this.quotes,
  });

  bool get isEmpty => quotes.isEmpty;
}
