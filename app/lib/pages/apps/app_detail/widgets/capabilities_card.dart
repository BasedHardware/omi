import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/app.dart';

class CapabilitiesCard extends StatelessWidget {
  final List<AppCapability> capabilities;

  const CapabilitiesCard({super.key, required this.capabilities});

  IconData _getCapabilityIcon(String id) {
    switch (id) {
      case 'chat':
        return FontAwesomeIcons.solidComment;
      case 'memories':
        return FontAwesomeIcons.solidLightbulb;
      case 'external_integration':
        return FontAwesomeIcons.puzzlePiece;
      case 'persona':
        return FontAwesomeIcons.userAstronaut;
      case 'proactive_notification':
        return FontAwesomeIcons.solidBell;
      default:
        return FontAwesomeIcons.cubes;
    }
  }

  Color _getCapabilityColor(String id) {
    switch (id) {
      case 'chat':
        return const Color(0xFF00D4FF); // Bright Cyan
      case 'memories':
        return const Color(0xFFFBBF24); // Bright Amber
      case 'external_integration':
        return const Color(0xFF34D399); // Bright Emerald
      case 'persona':
        return const Color(0xFFF472B6); // Bright Pink
      case 'proactive_notification':
        return const Color(0xFFFF6B6B); // Bright Coral
      default:
        return const Color(0xFF9CA3AF); // Light Gray
    }
  }

  @override
  Widget build(BuildContext context) {
    if (capabilities.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
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
          const Text(
            'Capabilities',
            style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: capabilities.map((capability) {
              final color = _getCapabilityColor(capability.id);
              return Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: color.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: color.withOpacity(0.3)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    FaIcon(
                      _getCapabilityIcon(capability.id),
                      size: 14,
                      color: color,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      capability.title,
                      style: TextStyle(
                        color: color,
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}
