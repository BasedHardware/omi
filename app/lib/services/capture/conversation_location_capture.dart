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

/// Captures the location that belongs to a recording before the backend can
/// finalize its conversation.
///
/// Foreground recording only needs while-in-use / ACCESS_FINE_LOCATION (or
/// coarse). Android does **not** need ACCESS_BACKGROUND_LOCATION for this
/// path: capture runs on the UI isolate while the activity is visible, and
/// the optional periodic refresh runs inside FOREGROUND_SERVICE_LOCATION.
/// ACCESS_BACKGROUND_LOCATION is intentionally not requested (Play Store
/// prominent-disclosure). iOS "Always" is requested separately for BGTask
/// windows and is not required for an in-app recorder start.
class ConversationLocationCapture {
  ConversationLocationCapture({
    LocationServiceEnabled? isLocationServiceEnabled,
    LocationPermissionReader? checkPermission,
    LocationPermissionRequester? requestPermission,
    CurrentPositionReader? getCurrentPosition,
    LastPositionReader? getLastKnownPosition,
    GeolocationUploader? upload,
    LocationGrantHandler? onNewlyGranted,
    this.currentPositionTimeout = const Duration(seconds: 2),
    this.totalTimeout = const Duration(seconds: 3),
    this.lastKnownMaxAge = const Duration(minutes: 5),
  })  : _isLocationServiceEnabled = isLocationServiceEnabled ?? Geolocator.isLocationServiceEnabled,
        _checkPermission = checkPermission ?? Geolocator.checkPermission,
        _requestPermission = requestPermission ?? Geolocator.requestPermission,
        _getCurrentPosition = getCurrentPosition ?? _defaultCurrentPosition,
        _getLastKnownPosition = getLastKnownPosition ?? _defaultLastKnownPosition,
        _upload = upload ?? ((geolocation) => updateUserGeolocation(geolocation: geolocation)),
        _onNewlyGranted = onNewlyGranted;

  final LocationServiceEnabled _isLocationServiceEnabled;
  final LocationPermissionReader _checkPermission;
  final LocationPermissionRequester _requestPermission;
  final CurrentPositionReader _getCurrentPosition;
  final LastPositionReader _getLastKnownPosition;
  final GeolocationUploader _upload;
  final LocationGrantHandler? _onNewlyGranted;
  final Duration currentPositionTimeout;
  final Duration totalTimeout;
  final Duration lastKnownMaxAge;

  /// Medium accuracy maps to Android PRIORITY_BALANCED_POWER_ACCURACY so a
  /// while-in-use / approximate grant can still return a fix. Default "best"
  /// is HIGH_ACCURACY GPS and routinely exceeds the recording-start budget
  /// on Android, after which last-known is also often null.
  static Future<Position> _defaultCurrentPosition() {
    return Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(accuracy: LocationAccuracy.medium),
    );
  }

  static Future<Position?> _defaultLastKnownPosition() async {
    return await Geolocator.getLastKnownPosition() ??
        await Geolocator.getLastKnownPosition(forceAndroidLocationManager: true);
  }

  bool _isFresh(Position position) {
    final age = DateTime.now().toUtc().difference(position.timestamp.toUtc());
    return !age.isNegative && age <= lastKnownMaxAge;
  }

  /// [promptIfDenied] is true on record/device start so a skipped onboarding
  /// page still gets a while-in-use prompt. HomePage's no-device check-only
  /// path passes false so plain home-page entry cannot walk the user into
  /// deniedForever. deniedForever is never re-prompted either way.
  Future<bool> captureAndUpload({bool promptIfDenied = true}) async {
    var timedOut = false;
    try {
      if (!await _isLocationServiceEnabled()) {
        Logger.log('Location service is not enabled, skipping conversation location');
        return false;
      }

      var permission = await _checkPermission();
      var newlyGranted = false;
      if (permission == LocationPermission.denied) {
        if (!promptIfDenied) {
          Logger.log('Location permission not granted, skipping conversation location');
          return false;
        }
        // Prompt at record start so a skipped onboarding page still gets a fix
        // when the activity is visible. deniedForever is not re-prompted.
        permission = await _requestPermission();
        newlyGranted = permission == LocationPermission.whileInUse || permission == LocationPermission.always;
      }
      if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
        Logger.log('Location permission not granted, skipping conversation location');
        return false;
      }
      if (newlyGranted) {
        try {
          await _onNewlyGranted?.call();
        } catch (e) {
          Logger.log('Post-grant location hook failed: $e');
        }
      }

      return await _captureAndUpload(isCancelled: () => timedOut).timeout(
        totalTimeout,
        onTimeout: () {
          timedOut = true;
          throw TimeoutException('conversation location');
        },
      );
    } on TimeoutException {
      timedOut = true;
      Logger.log('Conversation location capture timed out; recording will continue');
      return false;
    } catch (e) {
      Logger.error('Error capturing conversation location: $e');
      return false;
    }
  }

  Future<bool> _captureAndUpload({required bool Function() isCancelled}) async {
    Position? lastKnown;
    try {
      lastKnown = await _getLastKnownPosition();
    } catch (e) {
      Logger.log('Last-known conversation location failed: $e');
    }

    late final Position position;
    if (lastKnown != null && _isFresh(lastKnown)) {
      position = lastKnown;
    } else {
      try {
        position = await _getCurrentPosition().timeout(currentPositionTimeout);
      } catch (e) {
        Logger.log('Fresh conversation location fix failed: $e');
        if (lastKnown == null) return false;
        position = lastKnown;
      }
    }

    if (isCancelled()) return false;

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
