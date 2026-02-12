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
    parts.add(data.priority.displayName);
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
            color: Colors.white.withOpacity(0.08),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              // Title with priority dot
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(top: 8, right: 10),
                    child: Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: data.priority.color,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                  Expanded(
                    child: Text(
                      data.title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w500,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
              // Summary
              if (data.summary != null && data.summary!.isNotEmpty) ...[
                const SizedBox(height: 8),
                Padding(
                  padding: const EdgeInsets.only(left: 18),
                  child: Text(
                    data.summary!,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.5),
                      fontSize: 13,
                      height: 1.4,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
              // Meta info
              if (_meta.isNotEmpty) ...[
                const SizedBox(height: 6),
                Padding(
                  padding: const EdgeInsets.only(left: 18),
                  child: Text(
                    _meta,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.4),
                      fontSize: 12,
                    ),
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
