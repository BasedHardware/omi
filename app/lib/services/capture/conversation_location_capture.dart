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

/// Captures the location that belongs to a recording before the backend can
/// finalize its conversation.
class ConversationLocationCapture {
  ConversationLocationCapture({
    LocationServiceEnabled? isLocationServiceEnabled,
    LocationPermissionReader? checkPermission,
    CurrentPositionReader? getCurrentPosition,
    LastPositionReader? getLastKnownPosition,
    GeolocationUploader? upload,
    this.currentPositionTimeout = const Duration(seconds: 1),
    this.totalTimeout = const Duration(seconds: 3),
  }) : _isLocationServiceEnabled = isLocationServiceEnabled ?? Geolocator.isLocationServiceEnabled,
       _checkPermission = checkPermission ?? Geolocator.checkPermission,
       _getCurrentPosition = getCurrentPosition ?? Geolocator.getCurrentPosition,
       _getLastKnownPosition = getLastKnownPosition ?? Geolocator.getLastKnownPosition,
       _upload = upload ?? ((geolocation) => updateUserGeolocation(geolocation: geolocation));

  final LocationServiceEnabled _isLocationServiceEnabled;
  final LocationPermissionReader _checkPermission;
  final CurrentPositionReader _getCurrentPosition;
  final LastPositionReader _getLastKnownPosition;
  final GeolocationUploader _upload;
  final Duration currentPositionTimeout;
  final Duration totalTimeout;

  Future<bool> captureAndUpload() async {
    try {
      return await _captureAndUpload().timeout(totalTimeout);
    } on TimeoutException {
      Logger.log('Conversation location capture timed out; recording will continue');
      return false;
    } catch (e) {
      Logger.error('Error capturing conversation location: $e');
      return false;
    }
  }

  Future<bool> _captureAndUpload() async {
    if (!await _isLocationServiceEnabled()) {
      Logger.log('Location service is not enabled, skipping conversation location');
      return false;
    }

    final permission = await _checkPermission();
    if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
      Logger.log('Location permission not granted, skipping conversation location');
      return false;
    }

    Position? position;
    try {
      position = await _getCurrentPosition().timeout(currentPositionTimeout);
    } on TimeoutException {
      // A recent OS fix is preferable to losing the conversation location when
      // a fresh GPS fix is slow indoors.
      position = await _getLastKnownPosition();
    }
    if (position == null) return false;

    return _upload(
      Geolocation(
        latitude: position.latitude,
        longitude: position.longitude,
        altitude: position.altitude,
        accuracy: position.accuracy,
        time: position.timestamp.toUtc(),
      ),
    );
  }
}
