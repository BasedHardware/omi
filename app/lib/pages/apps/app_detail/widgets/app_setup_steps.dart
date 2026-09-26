import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The numbered setup steps of an integration app. Each step opens its setup link; once the app
/// reports setup complete every step shows a check.
class AppSetupSteps extends StatelessWidget {
  const AppSetupSteps({super.key, required this.steps, required this.completed, required this.onStepTap});

  final List<AuthStep> steps;
  final bool completed;
  final Future<void> Function(AuthStep step) onStepTap;

  @override
  Widget build(BuildContext context) {
    final inset = MediaQuery.sizeOf(context).width * 0.05;
    return Column(
      children: [
        for (final (index, step) in steps.indexed)
          Container(
            margin: EdgeInsets.only(left: inset, right: inset, bottom: 6),
            decoration: BoxDecoration(
              color: OmiColors.surface1.withValues(alpha: 0.8),
              borderRadius: OmiRadius.lgAll,
              border: Border.all(
                color: completed ? OmiColors.success.withValues(alpha: 0.3) : Colors.transparent,
                width: 1,
              ),
            ),
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                borderRadius: OmiRadius.lgAll,
                onTap: () => onStepTap(step),
                child: Padding(
                  padding: const EdgeInsets.all(OmiSpacing.md),
                  child: Row(
                    children: [
                      Container(
                        width: 32,
                        height: 32,
                        decoration: BoxDecoration(
                          color: completed ? OmiColors.successSurface : OmiColors.surface2,
                          borderRadius: OmiRadius.smAll,
                        ),
                        child: Center(
                          child: completed
                              ? const FaIcon(FontAwesomeIcons.check, size: 14, color: OmiColors.success)
                              : Text(
                                  '${index + 1}',
                                  style: OmiType.subhead.copyWith(
                                    color: OmiColors.textSecondary,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                        ),
                      ),
                      const SizedBox(width: OmiSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(step.name, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
                            const SizedBox(height: OmiSpacing.xxs),
                            Text(
                              completed ? context.l10n.setupCompleted : context.l10n.tapToComplete,
                              style: OmiType.footnote.copyWith(
                                color: completed ? OmiColors.success : OmiColors.textTertiary,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const ExcludeSemantics(
                        child: FaIcon(
                          FontAwesomeIcons.arrowUpRightFromSquare,
                          size: 16,
                          color: OmiColors.textTertiary,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}
