import 'dart:async';

import 'package:geolocator/geolocator.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/utils/logger.dart';

typedef LocationServiceEnabled = Future<bool> Function();
typedef LocationPermissionReader = Future<LocationPermission> Function();
typedef LocationPermissionRequester = Future<LocationPermission> Function();
typedef CurrentPositionReader = Future<Position> Function();
typedef LastPositionReader = Future<Position?> Function();
typedef GeolocationUploader = Future<bool> Function(Geolocation geolocation);
typedef LocationGrantHandler = Future<void> Function();
typedef LocationClock = DateTime Function();

/// Captures the location that belongs to a recording before the backend can
/// finalize its conversation.
///
/// Foreground recording only needs while-in-use / ACCESS_FINE_LOCATION (or
/// coarse). Android does **not** need ACCESS_BACKGROUND_LOCATION for this
/// path: capture runs on the UI isolate while the activity is visible, and
/// the optional periodic refresh runs inside FOREGROUND_SERVICE_LOCATION.
class ConversationLocationCapture {
  ConversationLocationCapture({
    LocationServiceEnabled? isLocationServiceEnabled,
    LocationPermissionReader? checkPermission,
    LocationPermissionRequester? requestPermission,
    CurrentPositionReader? getCurrentPosition,
    LastPositionReader? getLastKnownPosition,
    GeolocationUploader? upload,
    LocationGrantHandler? onNewlyGranted,
    LocationClock? now,
    this.currentPositionTimeout = const Duration(seconds: 2),
    this.totalTimeout = const Duration(seconds: 3),
    this.lastKnownMaxAge = const Duration(minutes: 5),
  })  : _isLocationServiceEnabled = isLocationServiceEnabled ?? Geolocator.isLocationServiceEnabled,
        _checkPermission = checkPermission ?? Geolocator.checkPermission,
        _requestPermission = requestPermission ?? Geolocator.requestPermission,
        _getCurrentPosition = getCurrentPosition ?? _defaultCurrentPosition,
        _getLastKnownPosition = getLastKnownPosition ?? _defaultLastKnownPosition,
        _upload = upload ?? ((geolocation) => updateUserGeolocation(geolocation: geolocation)),
        _onNewlyGranted = onNewlyGranted,
        _now = now ?? DateTime.now;

  final LocationServiceEnabled _isLocationServiceEnabled;
  final LocationPermissionReader _checkPermission;
  final LocationPermissionRequester _requestPermission;
  final CurrentPositionReader _getCurrentPosition;
  final LastPositionReader _getLastKnownPosition;
  final GeolocationUploader _upload;
  final LocationGrantHandler? _onNewlyGranted;
  final LocationClock _now;
  final Duration currentPositionTimeout;
  final Duration totalTimeout;
  final Duration lastKnownMaxAge;

  // Future.timeout does not cancel the underlying HTTP request. Keep
  // compatibility writes ordered so an older timed-out request cannot finish
  // after a newer session and put the user's cache back in the past.
  Future<void> _uploadTail = Future<void>.value();

  /// Medium accuracy maps to Android PRIORITY_BALANCED_POWER_ACCURACY so a
  /// while-in-use / approximate grant can still return a fix.
  static Future<Position> _defaultCurrentPosition() {
    return Geolocator.getCurrentPosition(locationSettings: const LocationSettings(accuracy: LocationAccuracy.medium));
  }

  static Future<Position?> _defaultLastKnownPosition() async {
    return await Geolocator.getLastKnownPosition() ??
        await Geolocator.getLastKnownPosition(forceAndroidLocationManager: true);
  }

  bool _isFresh(Position position) {
    final age = _now().toUtc().difference(position.timestamp.toUtc());
    return !age.isNegative && age <= lastKnownMaxAge;
  }

  /// Returns the recording-owned snapshot without writing the compatibility
  /// user cache. Permission prompting is outside the capture deadline so a
  /// human response cannot consume the location-fix budget.
  Future<Geolocation?> capture({bool promptIfDenied = true}) async {
    try {
      if (!await _isLocationServiceEnabled()) {
        Logger.log('Location service is not enabled, skipping conversation location');
        return null;
      }

      var permission = await _checkPermission();
      var newlyGranted = false;
      if (permission == LocationPermission.denied) {
        if (!promptIfDenied) {
          Logger.log('Location permission not granted, skipping conversation location');
          return null;
        }
        permission = await _requestPermission();
        newlyGranted = permission == LocationPermission.whileInUse || permission == LocationPermission.always;
      }
      if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
        Logger.log('Location permission not granted, skipping conversation location');
        return null;
      }
      if (newlyGranted) {
        try {
          await _onNewlyGranted?.call();
        } catch (e) {
          Logger.log('Post-grant location hook failed: $e');
        }
      }

      return await _capturePosition().timeout(totalTimeout);
    } on TimeoutException {
      Logger.log('Conversation location capture timed out; recording will continue');
      return null;
    } catch (e) {
      Logger.error('Error capturing conversation location: $e');
      return null;
    }
  }

  /// Best-effort compatibility write for the backend user-location cache.
  Future<void> uploadCompatibilitySnapshot(Geolocation geolocation) async {
    try {
      await _enqueueUpload(geolocation).timeout(totalTimeout);
    } catch (e) {
      Logger.log('Conversation location compatibility upload failed; preserving recording snapshot');
    }
  }

  /// Returns the recording-owned snapshot even when the compatibility write
  /// fails. Capture has its own post-permission deadline; the compatibility
  /// write only uses time left in the overall best-effort call budget.
  Future<Geolocation?> captureAndUpload({bool promptIfDenied = true}) async {
    final stopwatch = Stopwatch()..start();
    final geolocation = await capture(promptIfDenied: promptIfDenied);
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
    _uploadTail = upload.catchError((_) {});
    return upload;
  }

  Future<Geolocation?> _capturePosition() async {
    Position? lastKnown;
    try {
      lastKnown = await _getLastKnownPosition();
    } catch (e) {
      Logger.log('Last-known conversation location failed: $e');
    }

    Position? position;
    var captureSource = 'current_position';
    if (lastKnown != null && _isFresh(lastKnown)) {
      position = lastKnown;
      captureSource = 'last_known_position';
    } else {
      try {
        position = await _getCurrentPosition().timeout(currentPositionTimeout);
      } catch (e) {
        Logger.log('Fresh conversation location fix failed: $e');
      }
    }
    if (position == null) return null;

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
