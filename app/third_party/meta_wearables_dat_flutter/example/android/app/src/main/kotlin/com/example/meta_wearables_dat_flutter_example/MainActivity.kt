package com.example.meta_wearables_dat_flutter_example

import io.flutter.embedding.android.FlutterFragmentActivity

// `meta_wearables_dat_flutter` requires `FlutterFragmentActivity` (a
// `ComponentActivity`) on Android because the registration deep-link flow
// (slice 5) and `Wearables.RequestPermissionContract` (slice 6) both rely on
// `ActivityResultRegistry`, which `FlutterActivity` does not expose. The
// plugin throws `MISSING_FRAGMENT_ACTIVITY` if the host activity is not a
// `ComponentActivity`.
class MainActivity : FlutterFragmentActivity()

