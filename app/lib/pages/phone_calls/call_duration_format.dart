import 'package:omi/ui/format/omi_duration.dart';

/// Elapsed time of a phone call, as a clock position: `0:05`, `3:38`, `1:02:05`.
///
/// Thin adapter over [OmiDuration.offset] so the call page, the home banner and the top bar
/// read the same way as every other time position in the app (docs/ux-contract.md §8).
String formatPhoneCallDuration(Duration d) => OmiDuration.offset(d.inSeconds);
