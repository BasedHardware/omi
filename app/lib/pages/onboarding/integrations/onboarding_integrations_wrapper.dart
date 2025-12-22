import 'package:flutter/material.dart';
import 'package:omi/pages/settings/integrations_page.dart';

class OnboardingIntegrationsWrapper extends StatelessWidget {
  final VoidCallback goNext;
  final VoidCallback onSkip;
  final VoidCallback goBack;

  const OnboardingIntegrationsWrapper({
    super.key,
    required this.goNext,
    required this.onSkip,
    required this.goBack,
  });

  @override
  Widget build(BuildContext context) {
    return IntegrationsPage(
      hideAppBar: false,
      onBackPressed: goBack,
      bottomWidget: Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Row(
          children: [
            Expanded(
              child: TextButton(
                onPressed: onSkip,
                style: TextButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: Text(
                  'Skip',
                  style: TextStyle(
                    color: Colors.grey.shade400,
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              flex: 2,
              child: ElevatedButton(
                onPressed: goNext,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: Colors.black,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: const Text(
                  'Continue',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

