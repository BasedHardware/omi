import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';

import 'package:omi/l10n/app_localizations.dart';

String metaWearablesDeviceKindLabel(AppLocalizations l10n, DeviceKind kind) {
  switch (kind) {
    case DeviceKind.rayBanMeta:
      return l10n.metaGlassesTypeRayBanMeta;
    case DeviceKind.rayBanDisplay:
      return l10n.metaGlassesTypeRayBanDisplay;
    case DeviceKind.oakleyMeta:
      return l10n.metaGlassesTypeOakleyMeta;
    case DeviceKind.unknown:
      return l10n.metaGlasses;
  }
}
