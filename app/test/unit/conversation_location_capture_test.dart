import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:geolocator/geolocator.dart';

import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';

void main() {
  test('uploads a fresh position before recording starts', () async {
    Geolocation? uploaded;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.always,
      getCurrentPosition: () async => _position(latitude: 28.6139, longitude: 77.2090),
      getLastKnownPosition: () async => null,
      upload: (geolocation) async {
        uploaded = geolocation;
        return true;
      },
    );

    expect(await capture.captureAndUpload(), isTrue);
    expect(uploaded?.latitude, 28.6139);
    expect(uploaded?.longitude, 77.2090);
  });

  test('uploads last-known immediately when a fresh fix would be slow', () async {
    var currentCalls = 0;
    Geolocation? uploaded;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      getCurrentPosition: () {
        currentCalls++;
        return Completer<Position>().future;
      },
      getLastKnownPosition: () async => _position(latitude: 51.5072, longitude: -0.1276),
      upload: (geolocation) async {
        uploaded = geolocation;
        return true;
      },
      currentPositionTimeout: const Duration(milliseconds: 1),
    );

    expect(await capture.captureAndUpload(), isTrue);
    expect(uploaded?.latitude, 51.5072);
    expect(uploaded?.longitude, -0.1276);
    expect(currentCalls, 0);
  });

  test('homepage check-only path does not request permission when denied', () async {
    var requests = 0;
    var uploads = 0;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.denied,
      requestPermission: () async {
        requests++;
        return LocationPermission.whileInUse;
      },
      getCurrentPosition: () async => _position(latitude: 1, longitude: 2),
      getLastKnownPosition: () async => null,
      upload: (_) async {
        uploads++;
        return true;
      },
    );

    expect(await capture.captureAndUpload(promptIfDenied: false), isFalse);
    expect(requests, 0);
    expect(uploads, 0);
  });

  test('homepage check-only path still uploads when permission is already granted', () async {
    var requests = 0;
    Geolocation? uploaded;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      requestPermission: () async {
        requests++;
        return LocationPermission.whileInUse;
      },
      getCurrentPosition: () async => _position(latitude: 35.6895, longitude: 139.6917),
      getLastKnownPosition: () async => null,
      upload: (geolocation) async {
        uploaded = geolocation;
        return true;
      },
    );

    expect(await capture.captureAndUpload(promptIfDenied: false), isTrue);
    expect(requests, 0);
    expect(uploaded?.latitude, 35.6895);
    expect(uploaded?.longitude, 139.6917);
  });

  test('does not upload without location permission', () async {
    var uploads = 0;
    var requests = 0;
    var grants = 0;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.deniedForever,
      requestPermission: () async {
        requests++;
        return LocationPermission.deniedForever;
      },
      getCurrentPosition: () async => _position(latitude: 1, longitude: 2),
      getLastKnownPosition: () async => null,
      onNewlyGranted: () async {
        grants++;
      },
      upload: (_) async {
        uploads++;
        return true;
      },
    );

    expect(await capture.captureAndUpload(), isFalse);
    expect(uploads, 0);
    expect(requests, 0);
    expect(grants, 0);
  });

  test('deniedForever never prompts on the homepage check-only path', () async {
    var requests = 0;
    var uploads = 0;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.deniedForever,
      requestPermission: () async {
        requests++;
        return LocationPermission.deniedForever;
      },
      getCurrentPosition: () async => _position(latitude: 1, longitude: 2),
      getLastKnownPosition: () async => null,
      upload: (_) async {
        uploads++;
        return true;
      },
    );

    expect(await capture.captureAndUpload(promptIfDenied: false), isFalse);
    expect(requests, 0);
    expect(uploads, 0);
  });

  test('requests while-in-use at record start when permission is denied', () async {
    var requests = 0;
    var grants = 0;
    Geolocation? uploaded;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.denied,
      requestPermission: () async {
        requests++;
        return LocationPermission.whileInUse;
      },
      getCurrentPosition: () async => _position(latitude: 37.7749, longitude: -122.4194),
      getLastKnownPosition: () async => null,
      onNewlyGranted: () async {
        grants++;
      },
      upload: (geolocation) async {
        uploaded = geolocation;
        return true;
      },
    );

    expect(await capture.captureAndUpload(), isTrue);
    expect(requests, 1);
    expect(grants, 1);
    expect(uploaded?.latitude, 37.7749);
    expect(uploaded?.longitude, -122.4194);
  });

  test('does not start a post-grant hook when permission was already granted', () async {
    var grants = 0;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      requestPermission: () async => LocationPermission.whileInUse,
      getCurrentPosition: () async => _position(latitude: 1, longitude: 2),
      getLastKnownPosition: () async => _position(latitude: 1, longitude: 2),
      onNewlyGranted: () async {
        grants++;
      },
      upload: (_) async => true,
    );

    expect(await capture.captureAndUpload(), isTrue);
    expect(grants, 0);
  });

  test('does not time out while the user answers the location permission prompt', () async {
    var requests = 0;
    Geolocation? uploaded;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.denied,
      requestPermission: () async {
        requests++;
        await Future<void>.delayed(const Duration(milliseconds: 30));
        return LocationPermission.whileInUse;
      },
      getCurrentPosition: () async => _position(latitude: 40.7128, longitude: -74.0060),
      getLastKnownPosition: () async => null,
      upload: (geolocation) async {
        uploaded = geolocation;
        return true;
      },
      totalTimeout: const Duration(milliseconds: 10),
    );

    expect(await capture.captureAndUpload(), isTrue);
    expect(requests, 1);
    expect(uploaded?.latitude, 40.7128);
    expect(uploaded?.longitude, -74.0060);
  });

  test('uses last-known when a fresh fix throws', () async {
    Geolocation? uploaded;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      getCurrentPosition: () async => throw TimeoutException('gps'),
      getLastKnownPosition: () async => _position(latitude: 1.3521, longitude: 103.8198),
      upload: (geolocation) async {
        uploaded = geolocation;
        return true;
      },
    );

    expect(await capture.captureAndUpload(), isTrue);
    expect(uploaded?.latitude, 1.3521);
    expect(uploaded?.longitude, 103.8198);
  });

  test('falls back to last-known after a fresh-fix error when last-known is the only fix', () async {
    // last-known is tried first; if it is null, a failed current fix must not
    // upload. This guards the Android cold-start case.
    var uploads = 0;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      getCurrentPosition: () async => throw TimeoutException('gps'),
      getLastKnownPosition: () async => null,
      upload: (_) async {
        uploads++;
        return true;
      },
    );

    expect(await capture.captureAndUpload(), isFalse);
    expect(uploads, 0);
  });

  test('refreshes a stale last-known position before upload', () async {
    var currentCalls = 0;
    Geolocation? uploaded;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      getCurrentPosition: () async {
        currentCalls++;
        return _position(latitude: 48.8566, longitude: 2.3522);
      },
      getLastKnownPosition: () async => _position(
        latitude: 51.5072,
        longitude: -0.1276,
        timestamp: DateTime.now().toUtc().subtract(const Duration(minutes: 10)),
      ),
      upload: (geolocation) async {
        uploaded = geolocation;
        return true;
      },
      lastKnownMaxAge: const Duration(minutes: 5),
    );

    expect(await capture.captureAndUpload(), isTrue);
    expect(currentCalls, 1);
    expect(uploaded?.latitude, 48.8566);
    expect(uploaded?.longitude, 2.3522);
  });

  test('uses a stale last-known when the current fix fails', () async {
    Geolocation? uploaded;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      getCurrentPosition: () async => throw TimeoutException('gps'),
      getLastKnownPosition: () async => _position(
        latitude: 35.6762,
        longitude: 139.6503,
        timestamp: DateTime.now().toUtc().subtract(const Duration(hours: 2)),
      ),
      upload: (geolocation) async {
        uploaded = geolocation;
        return true;
      },
      lastKnownMaxAge: const Duration(minutes: 5),
    );

    expect(await capture.captureAndUpload(), isTrue);
    expect(uploaded?.latitude, 35.6762);
    expect(uploaded?.longitude, 139.6503);
  });
}

Position _position({
  required double latitude,
  required double longitude,
  DateTime? timestamp,
}) {
  return Position(
    latitude: latitude,
    longitude: longitude,
    timestamp: timestamp ?? DateTime.now().toUtc(),
    accuracy: 8,
    altitude: 220,
    altitudeAccuracy: 2,
    heading: 0,
    headingAccuracy: 0,
    speed: 0,
    speedAccuracy: 0,
  );
}
