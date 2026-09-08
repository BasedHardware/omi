import 'package:flutter_test/flutter_test.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth_service.dart';

void main() {
  test(
    'Google credential collision propagates the pre-switch source proof to migration after destination sign-in',
    () async {
      var destinationEstablished = false;
      final migrations = <(String, String)>[];

      Future<ProviderLinkResult?> googleCollisionHelper() async {
        return resolveProviderCredentialCollision(
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
      }

      await completeProviderLinkAndMigrate(
        linkProvider: googleCollisionHelper,
        migrate: (sourceUid, sourceToken) async {
          expect(destinationEstablished, isTrue);
          migrations.add((sourceUid, sourceToken));
          return true;
        },
      );

      expect(migrations, [('anonymous-source', 'source-id-token')]);
    },
  );
}
