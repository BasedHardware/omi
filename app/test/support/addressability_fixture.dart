import 'package:nested/nested.dart';

/// App UI implements ONLY external plugin/auth/BLE I/O setup here, reusing
/// JourneyHermeticBoot/JourneyFixtureBackend. No substitute pages or providers.
/// Return the real production provider instances needed beyond the common
/// JourneyHermeticBoot scope (auth/capture/device/memories/tasks/onboarding).
/// Only their external I/O dependencies may be replaced.
/// Fixture identities and scenarios are in contracts/addressability/catalog.json.
Future<List<SingleChildWidget>> prepareAddressabilityFixture(String routeId) async =>
    throw UnimplementedError('B1 surface external-I/O fixture setup');

Future<void> disposeAddressabilityFixture() async =>
    throw UnimplementedError('B1 close fixture backend, listeners and platform mocks');
