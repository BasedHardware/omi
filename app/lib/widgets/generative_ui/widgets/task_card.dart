import 'package:flutter/material.dart';
import '../models/task_data.dart';
import 'task_screen.dart';

/// Compact card showing a task preview with summary
/// Tapping navigates to the full-screen TaskScreen
class TaskCard extends StatelessWidget {
  final TaskData data;

  const TaskCard({
    super.key,
    required this.data,
  });

  void _openTaskScreen(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => TaskScreen(data: data),
      ),
    );
  }

  String get _meta {
    final parts = <String>[];
    if (data.hasSteps) {
      parts.add('${data.steps.length} steps');
    }
    if (data.hasTranscriptRefs) {
      parts.add('${data.totalTranscriptRefs} ref');
    }
    return parts.join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    if (data.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(top: 8, bottom: 8),
      child: InkWell(
        onTap: () => _openTaskScreen(context),
        borderRadius: BorderRadius.circular(10),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.05),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: Colors.white.withOpacity(0.1),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              // Header row
              Row(
                children: [
                  Icon(
                    Icons.check_circle_outline_rounded,
                    color: data.priority.color,
                    size: 20,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      data.title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w500,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: data.priority.backgroundColor,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      data.priority.displayName,
                      style: TextStyle(
                        color: data.priority.color,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  const SizedBox(width: 4),
                  Icon(
                    Icons.chevron_right_rounded,
                    color: Colors.white.withOpacity(0.3),
                    size: 20,
                  ),
                ],
              ),
              // Summary
              if (data.summary != null && data.summary!.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  data.summary!,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.6),
                    fontSize: 13,
                    height: 1.4,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
              // Meta info
              if (_meta.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(
                  _meta,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.4),
                    fontSize: 12,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
