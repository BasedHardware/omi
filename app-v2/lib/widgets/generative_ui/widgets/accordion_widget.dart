import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../generative_markdown_widget.dart';
import '../models/accordion_data.dart';

/// Widget for rendering expandable accordion sections from LLM-generated data.
class GenerativeAccordionWidget extends StatefulWidget {
  final AccordionDisplayData data;

  const GenerativeAccordionWidget({super.key, required this.data});

  @override
  State<GenerativeAccordionWidget> createState() => _GenerativeAccordionWidgetState();
}

class _GenerativeAccordionWidgetState extends State<GenerativeAccordionWidget> {
  late Set<int> _expandedIndices;

  @override
  void initState() {
    super.initState();
    _expandedIndices = {};
  }

  void _toggleExpanded(int index) {
    setState(() {
      if (_expandedIndices.contains(index)) {
        _expandedIndices.remove(index);
      } else {
        if (!widget.data.allowMultiple) {
          _expandedIndices.clear();
        }
        _expandedIndices.add(index);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    if (widget.data.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingS),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (widget.data.title != null && widget.data.title!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: AppStyles.spacingS),
              child: Text(
                widget.data.title!,
                style: const TextStyle(color: AppColors.textPrimary, fontSize: 16, fontWeight: FontWeight.w600),
              ),
            ),
          ...widget.data.items.asMap().entries.map((entry) {
            final index = entry.key;
            final item = entry.value;
            final isExpanded = _expandedIndices.contains(index);
            final isLast = index == widget.data.items.length - 1;

            return _AccordionItem(
              item: item,
              isExpanded: isExpanded,
              isLast: isLast,
              onToggle: () => _toggleExpanded(index),
            );
          }),
        ],
      ),
    );
  }
}

class _AccordionItem extends StatelessWidget {
  final AccordionItemData item;
  final bool isExpanded;
  final bool isLast;
  final VoidCallback onToggle;

  const _AccordionItem({required this.item, required this.isExpanded, required this.isLast, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        InkWell(
          onTap: onToggle,
          borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 10),
            child: Row(
              children: [
                AnimatedRotation(
                  turns: isExpanded ? 0.25 : 0,
                  duration: const Duration(milliseconds: 200),
                  child: const Icon(Icons.chevron_right, color: AppColors.textTertiary, size: 18),
                ),
                const SizedBox(width: AppStyles.spacingS),
                Expanded(
                  child: Text(
                    item.title,
                    style: TextStyle(
                      color: isExpanded ? AppColors.textPrimary : AppColors.textSecondary,
                      fontSize: 15,
                      fontWeight: isExpanded ? FontWeight.w600 : FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        AnimatedCrossFade(
          firstChild: const SizedBox(width: double.infinity, height: 0),
          secondChild: Padding(
            padding: const EdgeInsets.fromLTRB(26, 0, 4, 12),
            child: GenerativeMarkdownWidget(content: item.content, selectable: false),
          ),
          crossFadeState: isExpanded ? CrossFadeState.showSecond : CrossFadeState.showFirst,
          duration: const Duration(milliseconds: 200),
        ),
      ],
    );
  }
}
