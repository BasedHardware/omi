import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';

import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/capture/conversation_location_capture.dart';

void main() {
  test('capture without upload defers the compatibility write', () async {
    var uploads = 0;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.always,
      getCurrentPosition: () async => _position(latitude: 9, longitude: 8),
      getLastKnownPosition: () async => null,
      upload: (_) async {
        uploads++;
        return true;
      },
    );

    final result = await capture.capture();
    expect(result?.latitude, 9);
    expect(uploads, 0);

    await capture.uploadCompatibilitySnapshot(result!);
    expect(uploads, 1);
  });

  test('uploads a fresh position and returns the recording-owned snapshot', () async {
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

    final result = await capture.captureAndUpload();
    expect(result?.latitude, 28.6139);
    expect(uploaded?.longitude, 77.2090);
    expect(result?.captureSource, 'current_position');
  });

  test('uses a fresh last-known position without waiting for GPS', () async {
    var currentCalls = 0;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      getCurrentPosition: () {
        currentCalls++;
        return Completer<Position>().future;
      },
      getLastKnownPosition: () async => _position(latitude: 51.5072, longitude: -0.1276),
      upload: (_) async => true,
      now: () => DateTime.utc(2026, 7, 21, 0, 4),
    );

    final result = await capture.captureAndUpload();
    expect(result?.captureSource, 'last_known_position');
    expect(currentCalls, 0);
  });

  test('homepage check-only path does not request permission when denied', () async {
    var requests = 0;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.denied,
      requestPermission: () async {
        requests++;
        return LocationPermission.whileInUse;
      },
      getCurrentPosition: () async => _position(latitude: 1, longitude: 2),
      getLastKnownPosition: () async => null,
      upload: (_) async => true,
    );

    expect(await capture.captureAndUpload(promptIfDenied: false), isNull);
    expect(requests, 0);
  });

  test('record start requests permission and runs the post-grant hook', () async {
    var requests = 0;
    var grants = 0;
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
      upload: (_) async => true,
    );

    expect(await capture.captureAndUpload(), isNotNull);
    expect(requests, 1);
    expect(grants, 1);
  });

  test('permission prompt is outside the location deadline', () async {
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.denied,
      requestPermission: () async {
        await Future<void>.delayed(const Duration(milliseconds: 30));
        return LocationPermission.whileInUse;
      },
      getCurrentPosition: () async => _position(latitude: 40.7128, longitude: -74.0060),
      getLastKnownPosition: () async => null,
      upload: (_) async => true,
      totalTimeout: const Duration(milliseconds: 10),
    );

    expect((await capture.captureAndUpload())?.latitude, 40.7128);
  });

  test('rejects stale and future-dated last-known positions when GPS does not resolve', () async {
    for (final timestamp in [DateTime.utc(2026, 7, 20, 23), DateTime.utc(2026, 7, 21, 0, 20)]) {
      final capture = ConversationLocationCapture(
        isLocationServiceEnabled: () async => true,
        checkPermission: () async => LocationPermission.whileInUse,
        getCurrentPosition: () => Completer<Position>().future,
        getLastKnownPosition: () async => _position(latitude: 1, longitude: 2, timestamp: timestamp),
        upload: (_) async => true,
        currentPositionTimeout: const Duration(milliseconds: 1),
        totalTimeout: const Duration(milliseconds: 10),
        now: () => DateTime.utc(2026, 7, 21, 0, 10),
      );
      expect(await capture.captureAndUpload(), isNull);
    }
  });

  test('preserves the snapshot when the compatibility upload fails', () async {
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.always,
      getCurrentPosition: () async => _position(latitude: 1, longitude: 2),
      getLastKnownPosition: () async => null,
      upload: (_) async => false,
    );

    expect((await capture.captureAndUpload())?.latitude, 1);
  });

  test('shares one deadline between capture and compatibility upload', () async {
    final uploadStarted = Completer<void>();
    var uploadCompleted = false;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.always,
      getCurrentPosition: () async {
        await Future<void>.delayed(const Duration(milliseconds: 10));
        return _position(latitude: 1, longitude: 2);
      },
      getLastKnownPosition: () async => null,
      upload: (_) async {
        uploadStarted.complete();
        await Future<void>.delayed(const Duration(milliseconds: 60));
        uploadCompleted = true;
        return true;
      },
      totalTimeout: const Duration(milliseconds: 40),
    );

    final result = await capture.captureAndUpload();
    expect(result?.latitude, 1);
    expect(uploadStarted.isCompleted, isTrue);
    expect(uploadCompleted, isFalse);
  });

  test('serializes compatibility uploads after an earlier timed-out upload', () async {
    final firstUploadStarted = Completer<void>();
    final releaseFirstUpload = Completer<void>();
    final uploadedLatitudes = <double?>[];
    var positionIndex = 0;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.always,
      getCurrentPosition: () async => _position(latitude: (++positionIndex).toDouble(), longitude: 2),
      getLastKnownPosition: () async => null,
      upload: (geolocation) async {
        uploadedLatitudes.add(geolocation.latitude);
        if (uploadedLatitudes.length == 1) {
          firstUploadStarted.complete();
          await releaseFirstUpload.future;
        }
        return true;
      },
      totalTimeout: const Duration(milliseconds: 10),
    );

    final first = capture.captureAndUpload();
    await firstUploadStarted.future;
    expect((await first)?.latitude, 1);
    final second = capture.captureAndUpload();
    expect((await second)?.latitude, 2);
    expect(uploadedLatitudes, [1]);
    releaseFirstUpload.complete();
    await Future<void>.delayed(Duration.zero);
    expect(uploadedLatitudes, [1, 2]);
  });
}

Position _position({required double latitude, required double longitude, DateTime? timestamp}) {
  return Position(
    latitude: latitude,
    longitude: longitude,
    timestamp: timestamp ?? DateTime.utc(2026, 7, 21),
    accuracy: 8,
    altitude: 220,
    altitudeAccuracy: 2,
    heading: 0,
    headingAccuracy: 0,
    speed: 0,
    speedAccuracy: 0,
  );
}
