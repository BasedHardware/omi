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

    final result = await capture.captureAndUpload();
    expect(result, isNotNull);
    expect(uploaded?.latitude, 28.6139);
    expect(uploaded?.longitude, 77.2090);
    expect(result?.captureSource, 'current_position');
  });

  test('uses the last known position when a fresh fix is slow', () async {
    Geolocation? uploaded;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      getCurrentPosition: () => Completer<Position>().future,
      getLastKnownPosition: () async => _position(latitude: 51.5072, longitude: -0.1276),
      upload: (geolocation) async {
        uploaded = geolocation;
        return true;
      },
      currentPositionTimeout: const Duration(milliseconds: 1),
      now: () => DateTime.utc(2026, 7, 21, 0, 10),
    );

    final result = await capture.captureAndUpload();
    expect(result, isNotNull);
    expect(uploaded?.latitude, 51.5072);
    expect(uploaded?.longitude, -0.1276);
    expect(result?.captureSource, 'last_known_position');
  });

  test('does not upload without location permission', () async {
    var uploads = 0;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.denied,
      getCurrentPosition: () async => _position(latitude: 1, longitude: 2),
      getLastKnownPosition: () async => null,
      upload: (_) async {
        uploads++;
        return true;
      },
    );

    expect(await capture.captureAndUpload(), isNull);
    expect(uploads, 0);
  });

  test('rejects a stale last-known position', () async {
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      getCurrentPosition: () => Completer<Position>().future,
      getLastKnownPosition: () async => _position(latitude: 51.5072, longitude: -0.1276),
      upload: (_) async => true,
      currentPositionTimeout: const Duration(milliseconds: 1),
      now: () => DateTime.utc(2026, 7, 21, 0, 16),
    );

    expect(await capture.captureAndUpload(), isNull);
  });

  test('rejects a future-dated last-known position', () async {
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.whileInUse,
      getCurrentPosition: () => Completer<Position>().future,
      getLastKnownPosition: () async => _position(
        latitude: 51.5072,
        longitude: -0.1276,
        timestamp: DateTime.utc(2026, 7, 21, 0, 1),
      ),
      upload: (_) async => true,
      currentPositionTimeout: const Duration(milliseconds: 1),
      now: () => DateTime.utc(2026, 7, 21),
    );

    expect(await capture.captureAndUpload(), isNull);
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

    final stopwatch = Stopwatch()..start();
    final result = await capture.captureAndUpload();

    expect(result?.latitude, 1);
    expect(uploadStarted.isCompleted, isTrue);
    expect(uploadCompleted, isFalse);
    expect(stopwatch.elapsed, lessThan(const Duration(milliseconds: 100)));
  });

  test('serializes compatibility uploads after an earlier timed-out upload', () async {
    final firstUploadStarted = Completer<void>();
    final releaseFirstUpload = Completer<void>();
    final uploadedLatitudes = <double?>[];
    var positionIndex = 0;
    final capture = ConversationLocationCapture(
      isLocationServiceEnabled: () async => true,
      checkPermission: () async => LocationPermission.always,
      getCurrentPosition: () async {
        positionIndex++;
        return _position(latitude: positionIndex.toDouble(), longitude: 2);
      },
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
