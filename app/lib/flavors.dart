import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/env/env.dart';

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
        return Env.appName;
      case Environment.dev:
        return '${Env.appName} Dev';
      default:
        return '${Env.appName} Dev';
    }
  }
}
