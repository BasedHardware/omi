import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/extensions/string.dart';

class InfoCardWidget extends StatelessWidget {
  final VoidCallback onTap;
  final String title;
  final String description;
  final bool showChips;
  final List<String>? capabilityChips;
  final List<String>? connectionChips;
  final int? maxLines;
  const InfoCardWidget({
    super.key,
    required this.onTap,
    required this.title,
    required this.description,
    required this.showChips,
    this.capabilityChips,
    this.connectionChips,
    this.maxLines,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(OmiSpacing.md),
        margin: EdgeInsets.only(
          left: MediaQuery.of(context).size.width * 0.05,
          right: MediaQuery.of(context).size.width * 0.05,
          top: 12,
          bottom: 6,
        ),
        decoration: BoxDecoration(
          color: OmiColors.surface1.withValues(alpha: 0.8),
          borderRadius: OmiRadius.lgAll,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w600)),
                const Spacer(),
                (maxLines != null || description.decodeString.characters.length > 200)
                    ? const Icon(Icons.arrow_forward, size: 20)
                    : const SizedBox.shrink(),
              ],
            ),
            const SizedBox(height: OmiSpacing.sm),
            Text(
              maxLines != null
                  ? description.decodeString
                  : (description.decodeString.characters.length > 200
                      ? '${description.decodeString.characters.take(200).toString().trim()}…'
                      : description.decodeString),
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
              maxLines: maxLines,
              overflow: maxLines != null ? TextOverflow.ellipsis : null,
            ),
            if (showChips && capabilityChips != null) ...[
              const SizedBox(height: OmiSpacing.sm),
              Wrap(
                spacing: OmiSpacing.xs,
                runSpacing: OmiSpacing.xs,
                children: capabilityChips!
                    .map(
                      (chip) => Chip(
                        label: Text(chip, style: OmiType.callout),
                        backgroundColor: Colors.transparent,
                        shape: const StadiumBorder(side: BorderSide(color: OmiColors.border)),
                      ),
                    )
                    .toList(),
              ),
            ],
            if (showChips && connectionChips != null) ...[
              const SizedBox(height: OmiSpacing.sm),
              Wrap(
                spacing: OmiSpacing.xs,
                runSpacing: OmiSpacing.xs,
                children: connectionChips!
                    .map(
                      (chip) => Chip(
                        label: Text(chip, style: OmiType.callout),
                        backgroundColor: Colors.transparent,
                        shape: const StadiumBorder(side: BorderSide(color: OmiColors.border)),
                      ),
                    )
                    .toList(),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
