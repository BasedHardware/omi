import 'package:omi/env/env.dart';
import 'package:omi/flavors.dart';

/// The startup boundary used by [main] before any networked service starts.
void validateApplicationStartupRouting({Environment? environment, String? configuredApiBaseUrl}) {
  Env.validateStartupRouting(
    productionFamily: (environment ?? F.env) == Environment.prod,
    configuredApiBaseUrl: configuredApiBaseUrl,
  );
}
