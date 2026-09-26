import 'package:flutter/material.dart';

import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/devices/device_picker.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Onboarding's first question (Rev 3 PickDevice): what the reader will wear. A wearable opens the
/// connect flow, and onboarding moves on once it is paired and tested, or set up later; "Use this
/// iPhone" moves on straight away. Backing out of the connect flow returns here.
class OnboardingPickDeviceStep extends StatelessWidget {
  const OnboardingPickDeviceStep({super.key, required this.goNext});

  final VoidCallback goNext;

  Future<void> _connect(BuildContext context) async {
    OmiHaptics.selection();
    final advance = await Navigator.of(context).push<bool>(
      omiPageRoute(
        builder: (routeContext) => ConnectDevicePage(onDone: () => Navigator.of(routeContext).pop(true)),
      ),
    );
    if (advance == true) goNext();
  }

  void _usePhone() {
    OmiHaptics.selection();
    goNext();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return OnboardingStep(
      card: OnboardingCard(
        content: [
          OnboardingHeader(title: l10n.whatWillYouWear, subtitle: l10n.pickDeviceSubtitle),
          const SizedBox(height: OmiSpacing.lg),
          DevicePickerGroups(onConnect: () => _connect(context), onUsePhone: _usePhone),
          const SizedBox(height: OmiSpacing.lg),
        ],
      ),
    );
  }
}
