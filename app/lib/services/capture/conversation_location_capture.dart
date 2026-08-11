import 'dart:async';

import 'package:geolocator/geolocator.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/utils/logger.dart';

typedef LocationServiceEnabled = Future<bool> Function();
typedef LocationPermissionReader = Future<LocationPermission> Function();
typedef CurrentPositionReader = Future<Position> Function();
typedef LastPositionReader = Future<Position?> Function();
typedef GeolocationUploader = Future<bool> Function(Geolocation geolocation);
typedef LocationClock = DateTime Function();

/// Captures the location that belongs to a recording before the backend can
/// finalize its conversation.
class ConversationLocationCapture {
  ConversationLocationCapture({
    LocationServiceEnabled? isLocationServiceEnabled,
    LocationPermissionReader? checkPermission,
    CurrentPositionReader? getCurrentPosition,
    LastPositionReader? getLastKnownPosition,
    GeolocationUploader? upload,
    LocationClock? now,
    this.currentPositionTimeout = const Duration(seconds: 1),
    this.totalTimeout = const Duration(seconds: 3),
    this.maxLastKnownAge = const Duration(minutes: 15),
  })  : _isLocationServiceEnabled = isLocationServiceEnabled ?? Geolocator.isLocationServiceEnabled,
        _checkPermission = checkPermission ?? Geolocator.checkPermission,
        _getCurrentPosition = getCurrentPosition ?? Geolocator.getCurrentPosition,
        _getLastKnownPosition = getLastKnownPosition ?? Geolocator.getLastKnownPosition,
        _upload = upload ?? ((geolocation) => updateUserGeolocation(geolocation: geolocation)),
        _now = now ?? DateTime.now;

  final LocationServiceEnabled _isLocationServiceEnabled;
  final LocationPermissionReader _checkPermission;
  final CurrentPositionReader _getCurrentPosition;
  final LastPositionReader _getLastKnownPosition;
  final GeolocationUploader _upload;
  final LocationClock _now;
  final Duration currentPositionTimeout;
  final Duration totalTimeout;
  final Duration maxLastKnownAge;

  // Future.timeout does not cancel the underlying HTTP request. Keep
  // compatibility writes ordered so a timed-out older request cannot finish
  // after a newer session's write and put the user's cache back in the past.
  Future<void> _uploadTail = Future<void>.value();

  /// Returns the start-time snapshot without uploading the compatibility write.
  Future<Geolocation?> capture() async {
    try {
      return await _capture().timeout(totalTimeout);
    } on TimeoutException {
      Logger.log('Conversation location capture timed out; recording will continue');
      return null;
    } catch (e) {
      Logger.error('Error capturing conversation location: $e');
      return null;
    }
  }

  /// Best-effort compatibility write for the backend geolocation cache.
  Future<void> uploadCompatibilitySnapshot(Geolocation geolocation) async {
    try {
      await _enqueueUpload(geolocation).timeout(totalTimeout);
    } catch (e) {
      Logger.log('Conversation location compatibility upload failed; preserving recording snapshot');
    }
  }

  /// Returns the start-time snapshot even when the compatibility upload fails,
  /// so the caller can persist it with the recording/WAL.
  Future<Geolocation?> captureAndUpload() async {
    final stopwatch = Stopwatch()..start();
    final geolocation = await capture();
    if (geolocation == null) return null;
    try {
      final remaining = totalTimeout - stopwatch.elapsed;
      if (remaining <= Duration.zero) {
        Logger.log('Conversation location capture deadline elapsed before compatibility upload');
        return geolocation;
      }
      await _enqueueUpload(geolocation).timeout(remaining);
    } catch (e) {
      Logger.log('Conversation location compatibility upload failed; preserving recording snapshot');
    }
    return geolocation;
  }

  Future<void> _enqueueUpload(Geolocation geolocation) {
    final upload = _uploadTail.then<void>((_) async {
      await _upload(geolocation);
    });
    // Keep the queue usable after a failed upload while preserving the error
    // for the caller that is awaiting this particular upload.
    _uploadTail = upload.catchError((_) {});
    return upload;
  }

  Future<Geolocation?> _capture() async {
    if (!await _isLocationServiceEnabled()) {
      Logger.log('Location service is not enabled, skipping conversation location');
      return null;
    }

    final permission = await _checkPermission();
    if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
      Logger.log('Location permission not granted, skipping conversation location');
      return null;
    }

    Position? position;
    var captureSource = 'current_position';
    try {
      position = await _getCurrentPosition().timeout(currentPositionTimeout);
    } on TimeoutException {
      // A recent OS fix is preferable to losing the conversation location when
      // a fresh GPS fix is slow indoors.
      position = await _getLastKnownPosition();
      captureSource = 'last_known_position';
    }
    if (position == null) return null;
    if (captureSource == 'last_known_position') {
      final age = _now().toUtc().difference(position.timestamp.toUtc());
      if (age < Duration.zero || age > maxLastKnownAge) {
        Logger.log('Last known location is stale or future-dated, skipping conversation location');
        return null;
      }
    }

    return Geolocation(
      latitude: position.latitude,
      longitude: position.longitude,
      altitude: position.altitude,
      accuracy: position.accuracy,
      time: position.timestamp.toUtc(),
      captureSource: captureSource,
    );
  }
}
