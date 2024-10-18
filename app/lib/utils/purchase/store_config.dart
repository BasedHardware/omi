enum StoreT { appleStore, googlePlay }

class StoreConfig {
  factory StoreConfig({required StoreT store, required String apiKey}) {
    _instance ??= StoreConfig._internal(store, apiKey);
    return _instance!;
  }

  StoreConfig._internal(this.store, this.apiKey);

  final StoreT store;
  final String apiKey;
  static StoreConfig? _instance;

  static StoreConfig get instance {
    return _instance!;
  }

  static bool isForAppleStore() => _instance!.store == StoreT.appleStore;

  static bool isForGooglePlay() => _instance!.store == StoreT.googlePlay;
}
