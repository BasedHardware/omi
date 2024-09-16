import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

enum Environment {
  prod,
  dev;

  static Environment fromFlavor() {
    return Environment.values.firstWhere(
      (e) => e.name == appFlavor?.toLowerCase(),
      orElse: () {
        debugPrint('Warning: Unknown flavor "$appFlavor", defaulting to dev');
        return Environment.dev;
      },
    );
  }
}

class F {
  static Environment env = Environment.fromFlavor();

  static String get title {
    switch (env) {
      case Environment.prod:
        return 'Omi';
      case Environment.dev:
        return 'Omi Dev';
      default:
        return 'Omi Dev';
    }
  }
}
