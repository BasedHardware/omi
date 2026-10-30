import 'dart:async';

/// Recap changes that happen outside the surface showing recaps: a recap deleted from Activity, or a
/// daily-summary notification arriving while the app is in the foreground. Home's recap row listens,
/// so it never shows a ghost card or misses a new recap until the next pull.
final _deleted = StreamController<String>.broadcast();
final _arrived = StreamController<void>.broadcast();

Stream<String> get recapDeletions => _deleted.stream;
Stream<void> get recapArrivals => _arrived.stream;

void announceRecapDeleted(String summaryId) => _deleted.add(summaryId);
void announceRecapArrived() => _arrived.add(null);
