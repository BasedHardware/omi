import 'package:flutter/material.dart';
import '../models/accordion_data.dart';
import '../generative_markdown_widget.dart';

/// Widget for rendering expandable accordion sections from LLM-generated data
class GenerativeAccordionWidget extends StatefulWidget {
  final AccordionDisplayData data;

  const GenerativeAccordionWidget({
    super.key,
    required this.data,
  });

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
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Title
          if (widget.data.title != null && widget.data.title!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(
                widget.data.title!,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),

          // Accordion items
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

  const _AccordionItem({
    required this.item,
    required this.isExpanded,
    required this.isLast,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Header
        InkWell(
          onTap: onToggle,
          borderRadius: BorderRadius.circular(6),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 10),
            child: Row(
              children: [
                AnimatedRotation(
                  turns: isExpanded ? 0.25 : 0,
                  duration: const Duration(milliseconds: 200),
                  child: Icon(
                    Icons.chevron_right,
                    color: Colors.white.withOpacity(0.5),
                    size: 18,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    item.title,
                    style: TextStyle(
                      color: isExpanded ? Colors.white : Colors.white.withOpacity(0.8),
                      fontSize: 15,
                      fontWeight: isExpanded ? FontWeight.w600 : FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),

        // Content
        AnimatedCrossFade(
          firstChild: const SizedBox(width: double.infinity, height: 0),
          secondChild: Padding(
            padding: const EdgeInsets.fromLTRB(26, 0, 4, 12),
            child: GenerativeMarkdownWidget(
              content: item.content,
              selectable: false,
            ),
          ),
          crossFadeState: isExpanded
              ? CrossFadeState.showSecond
              : CrossFadeState.showFirst,
          duration: const Duration(milliseconds: 200),
        ),
      ],
    );
  }
}
