import 'package:flutter/material.dart';

/// Two-line section header used by the redesigned Apps page.
///
/// Pattern from ChatGPT GPT Store / Shopify App Store: title + grey subtitle on
/// the left, optional "View all ›" text-link on the right. Visually distinct
/// from Apple's editorial section header (which uses uppercase eyebrow + large
/// title + screenshot collage).
class SectionHeader extends StatelessWidget {
  final String title;
  final String? subtitle;
  final VoidCallback? onViewAll;

  const SectionHeader({super.key, required this.title, this.subtitle, this.onViewAll});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: Colors.white),
                ),
                if (subtitle != null && subtitle!.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    subtitle!,
                    style: TextStyle(fontSize: 13, color: Colors.grey.shade400, height: 1.3),
                  ),
                ],
              ],
            ),
          ),
          if (onViewAll != null)
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onViewAll,
              child: const Padding(
                padding: EdgeInsets.only(left: 12, top: 2),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'View all',
                      style: TextStyle(
                        fontSize: 13,
                        color: Color(0xFF8B5CF6),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    SizedBox(width: 2),
                    Icon(Icons.chevron_right_rounded, color: Color(0xFF8B5CF6), size: 16),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
