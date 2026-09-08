/// The supported mobile trust/data planes.
///
/// A profile is intentionally selected at build time. The default for the
/// `dev` flavor is local emulators; access to production Firebase identity and
/// data requires the explicit `mobile_beta` profile.
enum AppEnvironmentProfile {
  localDev(
    name: 'local_dev',
    defaultApiBaseUrl: 'http://127.0.0.1:8000/',
    firebaseProjectId: 'demo-omi-local',
    authCallbackScheme: 'omi-dev',
    usesFirebaseAuthEmulator: true,
    allowsProductionData: false,
  ),
  localProd(
    name: 'local_prod',
    defaultApiBaseUrl: 'http://127.0.0.1:8000/',
    firebaseProjectId: 'based-hardware',
    authCallbackScheme: 'omi',
    usesFirebaseAuthEmulator: false,
    allowsProductionData: true,
  ),
  mobileBeta(
    name: 'mobile_beta',
    defaultApiBaseUrl: 'https://api.omiapi.com/',
    firebaseProjectId: 'based-hardware',
    authCallbackScheme: 'omi-beta',
    usesFirebaseAuthEmulator: false,
    allowsProductionData: true,
  ),
  production(
    name: 'production',
    defaultApiBaseUrl: 'https://api.omi.me/',
    firebaseProjectId: 'based-hardware',
    authCallbackScheme: 'omi',
    usesFirebaseAuthEmulator: false,
    allowsProductionData: true,
  );

  const AppEnvironmentProfile({
    required this.name,
    required this.defaultApiBaseUrl,
    required this.firebaseProjectId,
    required this.authCallbackScheme,
    required this.usesFirebaseAuthEmulator,
    required this.allowsProductionData,
  });

  final String name;
  final String defaultApiBaseUrl;
  final String firebaseProjectId;
  final String authCallbackScheme;
  final bool usesFirebaseAuthEmulator;
  final bool allowsProductionData;

  static AppEnvironmentProfile forFlavor({required bool productionFlavor}) {
    const requested = String.fromEnvironment('OMI_APP_PROFILE');
    if (requested.isEmpty) {
      return productionFlavor ? AppEnvironmentProfile.production : AppEnvironmentProfile.localDev;
    }

    return AppEnvironmentProfile.values.firstWhere(
      (profile) => profile.name == requested,
      orElse: () => throw StateError(
        'Unknown OMI_APP_PROFILE "$requested". '
        'Use local_dev, mobile_beta, or production.',
      ),
    );
  }
}
