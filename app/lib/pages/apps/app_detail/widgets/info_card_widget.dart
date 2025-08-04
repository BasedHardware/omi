import 'package:flutter/material.dart';
import 'package:omi/widgets/extensions/string.dart';

class InfoCardWidget extends StatelessWidget {
  final VoidCallback onTap;
  final String title;
  final String description;
  final bool showChips;
  final List<String>? capabilityChips;
  final List<String>? connectionChips;
  const InfoCardWidget(
      {super.key,
      required this.onTap,
      required this.title,
      required this.description,
      required this.showChips,
      this.capabilityChips,
      this.connectionChips});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(16.0),
        margin: EdgeInsets.only(
          left: MediaQuery.of(context).size.width * 0.05,
          right: MediaQuery.of(context).size.width * 0.05,
          top: 12,
          bottom: 6,
        ),
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(16.0),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(title, style: const TextStyle(color: Colors.white, fontSize: 16)),
                const Spacer(),
                description.decodeString.characters.length > 200
                    ? const Icon(
                        Icons.arrow_forward,
                        size: 20,
                      )
                    : const SizedBox.shrink(),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              description.decodeString.characters.length > 200
                  ? '${description.decodeString.characters.take(200).toString().trim()}...'
                  : description.decodeString,
              style: const TextStyle(color: Colors.grey, fontSize: 15, height: 1.4),
            ),
            if (showChips && capabilityChips != null) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: capabilityChips!
                    .map((chip) => Chip(
                          label: Text(
                            chip,
                            style: const TextStyle(color: Colors.white),
                          ),
                          backgroundColor: Colors.transparent,
                          shape: StadiumBorder(
                            side: BorderSide(
                              color: Color(0xFF35343B),
                            ),
                          ),
                        ))
                    .toList(),
              ),
            ],
            if (showChips && connectionChips != null) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: connectionChips!
                    .map((chip) => Chip(
                          label: Text(
                            chip,
                            style: const TextStyle(color: Colors.white),
                          ),
                          backgroundColor: Colors.transparent,
                          shape: StadiumBorder(
                            side: BorderSide(
                              color: Color(0xFF35343B),
                            ),
                          ),
                        ))
                    .toList(),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
