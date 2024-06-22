enum Environment {
  prod,
  dev,
}

class F {
  static Environment? env;

  static String get title {
    switch (env) {
      case Environment.prod:
        return 'Friend';
      case Environment.dev:
        return 'Friend Dev';
      default:
        return 'Friend Dev';
    }
  }
}
