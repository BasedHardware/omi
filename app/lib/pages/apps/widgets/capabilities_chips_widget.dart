import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/add_app_provider.dart';

class CapabilitiesChipsWidget extends StatelessWidget {
  const CapabilitiesChipsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AddAppProvider>(builder: (context, provider, child) {
      return ListView(
        shrinkWrap: true,
        scrollDirection: Axis.horizontal,
        children: [
          provider.capabilities.isEmpty
              ? const SizedBox.shrink()
              : Wrap(
                  spacing: 12,
                  children: provider.capabilities
                      .map(
                        (capability) => ChoiceChip(
                          label: Text(capability.title),
                          selected: provider.isCapabilitySelected(capability),
                          showCheckmark: true,
                          backgroundColor: Colors.transparent,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                          onSelected: (bool selected) {
                            provider.addOrRemoveCapability(capability);
                          },
                        ),
                      )
                      .toList(),
                ),
        ],
      );
    });
  }
}
