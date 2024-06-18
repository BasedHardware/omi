enum Flavor {
  prod,
  dev,
}

class F {
  static Flavor? appFlavor;

  static String get name => appFlavor?.name ?? '';

  static String get title {
    switch (appFlavor) {
      case Flavor.prod:
        return 'Friend';
      case Flavor.dev:
        return 'Friend Dev';
      default:
        return 'title';
    }
  }
}
