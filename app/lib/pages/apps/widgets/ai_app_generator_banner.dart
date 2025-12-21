import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/pages/settings/ai_app_generator_page.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class AiAppGeneratorBanner extends StatelessWidget {
  const AiAppGeneratorBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();

        // Track banner click
        MixpanelManager().track('AI App Generator Banner Clicked');

        Navigator.of(context).push(
          MaterialPageRoute(
            builder: (context) => const AiAppGeneratorPage(),
          ),
        );
      },
      child: Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              const Color(0xFF6366F1).withOpacity(0.3),
              const Color(0xFF8B5CF6).withOpacity(0.3),
            ],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(18.0),
          border: Border.all(
            color: const Color(0xFF8B5CF6).withOpacity(0.3),
            width: 1,
          ),
        ),
        child: Row(
          children: [
            // Magic wand icon
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
                ),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Center(
                child: FaIcon(
                  FontAwesomeIcons.wandMagicSparkles,
                  color: Colors.white,
                  size: 16,
                ),
              ),
            ),

            const SizedBox(width: 12),

            // Message
            const Expanded(
              child: Text(
                'Build apps using AI in 1 click!',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),

            // BETA badge
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFFFF6B35), Color(0xFFFF8C42)],
                ),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Text(
                'BETA',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 9,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.5,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
