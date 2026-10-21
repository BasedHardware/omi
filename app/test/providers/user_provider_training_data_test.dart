import 'package:flutter_test/flutter_test.dart';

import 'package:omi/providers/user_provider.dart';

void main() {
  group('UserProvider training data opt-in loading', () {
    test('applies the fetched record on success', () async {
      final provider = UserProvider(
        trainingDataFetcher: () async => {'opted_in': true, 'status': 'approved'},
      );
      addTearDown(provider.dispose);

      await provider.loadTrainingDataOptIn();

      expect(provider.trainingDataOptedIn, isTrue);
      expect(provider.trainingDataStatus, 'approved');
    });

    test('keeps the opted-in state when a fetch fails (returns null)', () async {
      Map<String, dynamic>? result = {'opted_in': true, 'status': 'approved'};
      final provider = UserProvider(trainingDataFetcher: () async => result);
      addTearDown(provider.dispose);

      await provider.loadTrainingDataOptIn();
      expect(provider.trainingDataOptedIn, isTrue);

      result = null;
      await provider.loadTrainingDataOptIn();

      expect(provider.trainingDataOptedIn, isTrue);
      expect(provider.trainingDataStatus, 'approved');
    });

    test('keeps the opted-in state when the fetch throws', () async {
      var shouldThrow = false;
      final provider = UserProvider(
        trainingDataFetcher: () async {
          if (shouldThrow) throw Exception('network down');
          return {'opted_in': true, 'status': 'approved'};
        },
      );
      addTearDown(provider.dispose);

      await provider.loadTrainingDataOptIn();
      expect(provider.trainingDataOptedIn, isTrue);

      shouldThrow = true;
      await provider.loadTrainingDataOptIn();

      expect(provider.trainingDataOptedIn, isTrue);
    });
  });
}
