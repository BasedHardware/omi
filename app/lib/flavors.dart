import 'package:flutter/services.dart';

import 'package:omi/utils/logger.dart';

enum Environment {
  prod,
  dev;

  static Environment? tryFromFlavor(String? flavor) {
    return switch (flavor?.toLowerCase()) {
      'prod' => Environment.prod,
      'dev' || 'raybandat' => Environment.dev,
      _ => null,
    };
  }

  static Environment fromFlavor() {
    final environment = tryFromFlavor(appFlavor);
    if (environment != null) return environment;

    Logger.debug('Warning: Unknown flavor "$appFlavor", defaulting to dev');
    return Environment.dev;
  }
}

class F {
  static Environment env = Environment.fromFlavor();

  static void configureForStartup([String? flavor = appFlavor]) {
    env = Environment.tryFromFlavor(flavor) ??
        (throw StateError('Unsupported build flavor "${flavor ?? '<missing>'}". Use dev, prod, or raybanDat.'));
  }

  static String get title {
    switch (env) {
      case Environment.prod:
        return 'Omi';
      case Environment.dev:
        return 'Omi Dev';
    }
  }
}
