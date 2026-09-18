import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

class AppDetailSummary extends StatelessWidget {
  final String name;
  final String author;
  final bool official;
  final int ratingCount;
  final String? rating;
  final int installs;
  final VoidCallback? onRatingTap;
  final Widget action;

  const AppDetailSummary({
    super.key,
    required this.name,
    required this.author,
    required this.official,
    required this.ratingCount,
    required this.rating,
    required this.installs,
    required this.action,
    this.onRatingTap,
  });

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 108),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                name,
                style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  Flexible(
                    child: Text(
                      author,
                      style: const TextStyle(color: Colors.grey, fontSize: 16),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (official) ...[
                    const SizedBox(width: 4),
                    const FaIcon(FontAwesomeIcons.solidCircleCheck, size: 14, color: Colors.white),
                  ],
                ],
              ),
              const SizedBox(height: 6),
              GestureDetector(
                onTap: onRatingTap,
                child: Row(
                  children: [
                    if (ratingCount > 0) ...[
                      const FaIcon(FontAwesomeIcons.solidStar, size: 11, color: Colors.white),
                      const SizedBox(width: 4),
                      Text('$rating ($ratingCount)', style: TextStyle(fontSize: 13, color: Colors.grey.shade400)),
                      if (installs > 0) Text('  ·  ', style: TextStyle(fontSize: 13, color: Colors.grey.shade600)),
                    ],
                    if (installs > 0)
                      Text(
                        '${(installs / 10).round() * 10}+ users',
                        style: TextStyle(fontSize: 13, color: Colors.grey.shade500),
                      ),
                  ],
                ),
              ),
            ],
          ),
          action,
        ],
      ),
    );
  }
}
