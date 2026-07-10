import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/meta_wearables_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

bool metaGlassesOnboardingComplete(MetaWearablesProvider provider) {
  return provider.isRegistered && provider.hasLinkedDevices;
}

class OnboardingMetaGlassesStep extends StatefulWidget {
  const OnboardingMetaGlassesStep({
    super.key,
    required this.onMetaGlassesSelected,
    required this.onOmiDeviceSelected,
    required this.onContinueWithoutDevice,
    this.onMetaGlassesReady,
  });

  final VoidCallback onMetaGlassesSelected;
  final VoidCallback onOmiDeviceSelected;
  final VoidCallback onContinueWithoutDevice;
  final VoidCallback? onMetaGlassesReady;

  @override
  State<OnboardingMetaGlassesStep> createState() => _OnboardingMetaGlassesStepState();
}

class _OnboardingMetaGlassesStepState extends State<OnboardingMetaGlassesStep> {
  bool _notifiedReady = false;

  @override
  Widget build(BuildContext context) {
    return Consumer<MetaWearablesProvider>(
      builder: (context, provider, child) {
        if (!_notifiedReady && metaGlassesOnboardingComplete(provider)) {
          _notifiedReady = true;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) widget.onMetaGlassesReady?.call();
          });
        }

        return LayoutBuilder(
          builder: (context, constraints) => SingleChildScrollView(
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: constraints.maxHeight),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    context.l10n.connectDevice,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w700, color: Colors.white),
                  ),
                  const SizedBox(height: 24),
                  _OnboardingDeviceOption(
                    key: const Key('onboarding_omi_device_option'),
                    title: context.l10n.getOmiDevice,
                    assetPath: Assets.images.omiGlass.path,
                    onTap: widget.onOmiDeviceSelected,
                  ),
                  const SizedBox(height: 12),
                  _OnboardingDeviceOption(
                    key: const Key('onboarding_meta_glasses_option'),
                    title: context.l10n.metaGlasses,
                    assetPath: Assets.images.omiGlass.path,
                    onTap: widget.onMetaGlassesSelected,
                  ),
                  const SizedBox(height: 16),
                  TextButton(
                    onPressed: widget.onContinueWithoutDevice,
                    child: Text(
                      context.l10n.continueWithoutDevice,
                      style: const TextStyle(color: Colors.white70, fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _OnboardingDeviceOption extends StatelessWidget {
  const _OnboardingDeviceOption({super.key, required this.title, required this.assetPath, required this.onTap});

  final String title;
  final String assetPath;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(24)),
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: Image.asset(
                assetPath,
                width: 56,
                height: 56,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const Icon(Icons.devices_other, size: 36, color: Colors.black),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(color: Colors.black, fontSize: 18, fontWeight: FontWeight.w700),
              ),
            ),
            const Icon(Icons.chevron_right, color: Colors.black54),
          ],
        ),
      ),
    );
  }
}
