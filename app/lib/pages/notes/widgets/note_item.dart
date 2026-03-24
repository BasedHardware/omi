import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/schema/note.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:omi/utils/time/time_utils.dart';

class NoteItem extends StatelessWidget {
  final Note note;
  final VoidCallback onTap;
  final VoidCallback onDelete;

  const NoteItem({
    super.key,
    required this.note,
    required this.onTap,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppStyles.backgroundSecondary,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: Colors.white.withOpacity(0.05),
            width: 1,
          ),
        ),
        child: Row(
          children: [
            // Icon
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: note.type == NoteType.voice
                    ? Colors.deepPurple.withOpacity(0.3)
                    : Colors.deepPurpleAccent.withOpacity(0.3),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Center(
                child: Icon(
                  note.type == NoteType.voice
                      ? FontAwesomeIcons.microphone
                      : FontAwesomeIcons.pen,
                  color: Colors.white70,
                  size: 18,
                ),
              ),
            ),
            const SizedBox(width: 14),
            // Content
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          note.displayTitle,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 15,
                            fontWeight: FontWeight.w500,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      if (note.edited)
                        Padding(
                          padding: const EdgeInsets.only(left: 8),
                          child: Text(
                            '(edited)',
                            style: TextStyle(
                              color: Colors.white.withOpacity(0.4),
                              fontSize: 11,
                              fontStyle: FontStyle.italic,
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    note.type == NoteType.voice
                        ? note.transcription ?? 'Voice note'
                        : note.content,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.6),
                      fontSize: 13,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Icon(
                        FontAwesomeIcons.clock,
                        color: Colors.white.withOpacity(0.3),
                        size: 10,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        TimeUtils.formatRelativeTime(note.createdAt),
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.3),
                          fontSize: 11,
                        ),
                      ),
                      if (note.type == NoteType.voice && note.duration != null) ...[
                        const SizedBox(width: 12),
                        Icon(
                          FontAwesomeIcons.play,
                          color: Colors.white.withOpacity(0.3),
                          size: 10,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          note.formattedDuration,
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.3),
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            // Actions
            Column(
              children: [
                IconButton(
                  icon: Icon(
                    FontAwesomeIcons.penToSquare,
                    color: Colors.white.withOpacity(0.4),
                    size: 16,
                  ),
                  onPressed: onTap,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                  splashRadius: 20,
                ),
                const SizedBox(height: 8),
                IconButton(
                  icon: Icon(
                    FontAwesomeIcons.trash,
                    color: Colors.red.withOpacity(0.5),
                    size: 16,
                  ),
                  onPressed: onDelete,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                  splashRadius: 20,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
