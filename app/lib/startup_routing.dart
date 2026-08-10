import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/flavors.dart';

/// The startup boundary used by [main] before any networked service starts.
void validateApplicationStartupRouting({
  Environment? environment,
  String? configuredApiBaseUrl,
}) {
  final configuredProfile = environment == null
      ? Env.profile
      : (environment == Environment.prod ? AppEnvironmentProfile.production : AppEnvironmentProfile.localDev);
  Env.validateStartupRouting(
    productionFamily: (environment ?? F.env) == Environment.prod,
    configuredApiBaseUrl: configuredApiBaseUrl,
    configuredProfile: configuredProfile,
  );
}
