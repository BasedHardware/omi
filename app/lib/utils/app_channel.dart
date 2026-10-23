import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';

/// Distribution channel the backend sees on every API request (`X-Omi-App-Channel`).
///
/// The same binary is uploaded to TestFlight / Play internal and later promoted to the stores,
/// so the channel is detected at runtime, not baked in at build time:
/// - iOS: a TestFlight install carries a sandbox App Store receipt ([Env.isTestFlight], set at
///   startup from `appStoreReceiptURL.lastPathComponent == "sandboxReceipt"`).
/// - A non-production build profile (`mobile_beta`, `local_dev`, `local_prod`) is never a store install.
/// - Everything else, including every Play install (internal and production tracks look the same
///   on device), is `store`. Unknown fails closed: the server treats `store` as not yet admitted to
///   beta-only features such as episodes.
const String appChannelHeader = 'X-Omi-App-Channel';

enum AppChannel {
  beta('beta'),
  store('store');

  const AppChannel(this.wire);
  final String wire;
}

AppChannel resolveAppChannel({required bool isTestFlight, required AppEnvironmentProfile? profile}) {
  if (isTestFlight) return AppChannel.beta;
  if (profile != null && profile != AppEnvironmentProfile.production) return AppChannel.beta;
  return AppChannel.store;
}

/// The current process's channel. Never throws: a missing profile reads as `store`.
AppChannel currentAppChannel() {
  AppEnvironmentProfile? profile;
  try {
    profile = Env.profile;
  } catch (_) {
    profile = null;
  }
  return resolveAppChannel(isTestFlight: Env.isTestFlight, profile: profile);
}
