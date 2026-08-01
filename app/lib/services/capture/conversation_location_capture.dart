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

  /// Returns the start-time snapshot even when the compatibility upload fails,
  /// so the caller can persist it with the recording/WAL.
  Future<Geolocation?> captureAndUpload() async {
    Geolocation? geolocation;
    try {
      geolocation = await _capture().timeout(totalTimeout);
    } on TimeoutException {
      Logger.log('Conversation location capture timed out; recording will continue');
      return null;
    } catch (e) {
      Logger.error('Error capturing conversation location: $e');
      return null;
    }
    if (geolocation == null) return null;
    try {
      await _upload(geolocation).timeout(totalTimeout);
    } catch (e) {
      Logger.log('Conversation location compatibility upload failed; preserving recording snapshot');
    }
    return geolocation;
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
    if (captureSource == 'last_known_position' &&
        _now().toUtc().difference(position.timestamp.toUtc()) > maxLastKnownAge) {
      Logger.log('Last known location is stale, skipping conversation location');
      return null;
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
