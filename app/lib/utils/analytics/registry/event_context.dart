import 'package:uuid/uuid.dart';

/// A random attempt, never derived from an account, device or user content.
final class EventCorrelation {
  const EventCorrelation._(this.value);
  final String value;
  static EventCorrelation mint() => EventCorrelation._(const Uuid().v4());
}

/// An existing opaque record key, for joining an outcome to its owner record.
/// This is not an identity, label, title, transcript, URL or arbitrary payload.
final class RecordReference {
  const RecordReference._(this.value);
  final String value;

  static RecordReference? fromId(String? value) {
    if (value == null || !RegExp(r'^[a-zA-Z0-9_-]{1,128}$').hasMatch(value)) return null;
    return RecordReference._(value);
  }
}
