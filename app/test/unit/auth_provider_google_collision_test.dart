import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/auth/auth_token_result.dart';

void main() {
  test(
    'Google credential collision propagates the pre-switch source proof to migration after destination sign-in',
    () async {
      var destinationEstablished = false;
      final migrations = <(String, String)>[];

      Future<ProviderLinkResult?> googleCollisionHelper() async {
        final result = await resolveProviderCredentialCollision(
          sourceUid: 'anonymous-source',
          sourceIsAnonymous: true,
          captureSourceToken: () async {
            expect(destinationEstablished, isFalse);
            return 'source-id-token';
          },
          establishDestination: () async {
            destinationEstablished = true;
            return 'linked-destination';
          },
        );
        return ProviderLinkResult(
            destinationUid: result.destinationUid,
            destinationSession: const AuthSessionSnapshot(ownerUid: 'linked-destination', generation: 7),
            anonymousSourceMigration: result.anonymousSourceMigration);
      }

      await completeProviderLinkAndMigrate(
        linkProvider: googleCollisionHelper,
        migrate: (sourceUid, sourceToken, destination) async {
          expect(destination.generation, 7);
          expect(destination.ownerUid, 'linked-destination');
          expect(destinationEstablished, isTrue);
          migrations.add((sourceUid, sourceToken));
          return true;
        },
      );

      expect(migrations, [('anonymous-source', 'source-id-token')]);
    },
  );
}
