import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class TaskIntegrationsBanner extends StatelessWidget {
  const TaskIntegrationsBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();

        // Track banner click
        MixpanelManager().exportTasksBannerClicked();

        Navigator.of(context).push(
          MaterialPageRoute(
            builder: (context) => const TaskIntegrationsPage(),
          ),
        );
      },
      child: Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            colors: [
              Colors.deepPurple.withOpacity(0.3),
              Colors.purple.withOpacity(0.3),
            ],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: Colors.deepPurpleAccent.withOpacity(0.2),
            width: 1,
          ),
        ),
        child: Row(
          children: [
            // Overlapping app logos (stacked)
            SizedBox(
              width: 80, // Width for 3 overlapping logos
              height: 28,
              child: Stack(
                children: [
                  // First logo - Todoist
                  Positioned(
                    left: 0,
                    child: Hero(
                      tag: 'task_integration_todoist_icon',
                      child: _buildOverlappingLogo(
                        Assets.integrationAppLogos.todoistLogo.path,
                        28,
                      ),
                    ),
                  ),
                  // Second logo - ClickUp
                  Positioned(
                    left: 22,
                    child: Hero(
                      tag: 'task_integration_clickup_icon',
                      child: _buildOverlappingLogo(
                        Assets.integrationAppLogos.clickupLogo.path,
                        28,
                      ),
                    ),
                  ),
                  // Third logo - Asana
                  Positioned(
                    left: 44,
                    child: Hero(
                      tag: 'task_integration_asana_icon',
                      child: _buildOverlappingLogo(
                        Assets.integrationAppLogos.asanaLogo.path,
                        28,
                      ),
                    ),
                  ),
                ],
              ),
            ),

            // const SizedBox(width: 20),

            // Message
            const Expanded(
              child: Text(
                'Export tasks with one tap!',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),

            // NEW badge (moved to right)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
              decoration: BoxDecoration(
                color: Colors.green.withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Text(
                'NEW',
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

  Widget _buildOverlappingLogo(String path, double size) {
    return Container(
      width: size,
      height: size,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Image.asset(
          path,
          width: size,
          height: size,
          fit: BoxFit.contain,
        ),
      ),
    );
  }
}
