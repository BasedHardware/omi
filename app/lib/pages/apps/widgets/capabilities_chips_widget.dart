import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import '../providers/add_app_provider.dart';

class CapabilitiesChipsWidget extends StatelessWidget {
  const CapabilitiesChipsWidget({super.key});

  Widget _buildCapabilityButton(AppCapability capability, bool isSelected, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        height: 44,
        decoration: BoxDecoration(
          color: isSelected ? Colors.white : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected ? Colors.white : Colors.grey.withOpacity(0.3),
            width: 1,
          ),
        ),
        child: Center(
          child: Text(
            capability.title,
            style: TextStyle(
              color: isSelected ? Colors.black : Colors.white,
              fontSize: 14,
              fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      if (provider.capabilities.isEmpty) {
        return const SizedBox.shrink();
      }

      // Build 2x2 grid manually for precise control
      final caps = provider.capabilities;
      final rows = <Widget>[];

      for (int i = 0; i < caps.length; i += 2) {
        rows.add(
          Padding(
            padding: EdgeInsets.only(left: 8.0, bottom: i + 2 < caps.length ? 10 : 0),
            child: Row(
              children: [
                Expanded(
                  child: _buildCapabilityButton(caps[i], provider.isCapabilitySelected(caps[i]), () {
                    provider.addOrRemoveCapability(caps[i]);
                  }),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: i + 1 < caps.length
                      ? _buildCapabilityButton(caps[i + 1], provider.isCapabilitySelected(caps[i + 1]), () {
                          provider.addOrRemoveCapability(caps[i + 1]);
                        })
                      : const SizedBox.shrink(),
                ),
              ],
            ),
          ),
        );
      }

      return Column(children: rows);
    });
  }
}
