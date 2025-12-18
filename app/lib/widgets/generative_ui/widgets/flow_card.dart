import 'package:flutter/material.dart';
import '../models/flow_data.dart';

/// Card showing a flow/use case with numbered steps
class FlowCard extends StatelessWidget {
  final FlowData data;

  const FlowCard({
    super.key,
    required this.data,
  });

  @override
  Widget build(BuildContext context) {
    if (data.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(top: 8, bottom: 8),
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.05),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: Colors.white.withOpacity(0.1),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            // Header
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 14, 14, 12),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(
                      color: const Color(0xFF8B5CF6).withOpacity(0.15),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: const Icon(
                      Icons.account_tree_rounded,
                      color: Color(0xFF8B5CF6),
                      size: 16,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      data.title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  Text(
                    '${data.steps.length} steps',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.4),
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
            // Divider
            Container(
              height: 1,
              color: Colors.white.withOpacity(0.08),
            ),
            // Steps
            Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                children: data.steps.asMap().entries.map((entry) {
                  final index = entry.key;
                  final step = entry.value;
                  final isLast = index == data.steps.length - 1;
                  return _FlowStepItem(
                    key: ValueKey('flow_step_$index'),
                    step: step,
                    index: index,
                    isLast: isLast,
                  );
                }).toList(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FlowStepItem extends StatelessWidget {
  final FlowStepData step;
  final int index;
  final bool isLast;

  const _FlowStepItem({
    super.key,
    required this.step,
    required this.index,
    required this.isLast,
  });

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Step indicator with connecting line
          SizedBox(
            width: 28,
            child: Column(
              children: [
                Container(
                  width: 22,
                  height: 22,
                  decoration: BoxDecoration(
                    color: step.type.backgroundColor,
                    shape: BoxShape.circle,
                  ),
                  child: Center(
                    child: step.type == FlowStepType.main
                        ? Text(
                            '${index + 1}',
                            style: TextStyle(
                              color: step.type.color,
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                            ),
                          )
                        : Icon(
                            step.type.icon,
                            size: 12,
                            color: step.type.color,
                          ),
                  ),
                ),
                if (!isLast)
                  Expanded(
                    child: Container(
                      width: 2,
                      margin: const EdgeInsets.symmetric(vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.12),
                        borderRadius: BorderRadius.circular(1),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          // Step content
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (step.type != FlowStepType.main)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: step.type.backgroundColor,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          step.type.displayName,
                          style: TextStyle(
                            color: step.type.color,
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  Text(
                    step.content,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.85),
                      fontSize: 14,
                      height: 1.4,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
