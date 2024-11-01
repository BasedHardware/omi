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
          ChoiceChip(
            label: const Text('Chat'),
            selected: provider.isCapabilitySelected('Chat'),
            backgroundColor: Colors.transparent,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
            showCheckmark: true,
            onSelected: (bool selected) {
              provider.addOrRemoveCapability('Chat');
            },
          ),
          const SizedBox(
            width: 12,
          ),
          ChoiceChip(
            label: const Text('Memories'),
            selected: provider.isCapabilitySelected('Memories'),
            showCheckmark: true,
            backgroundColor: Colors.transparent,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
            onSelected: (bool selected) {
              provider.addOrRemoveCapability('Memories');
            },
          ),
          const SizedBox(
            width: 12,
          ),
          ChoiceChip(
            label: const Text('External Integration'),
            selected: provider.isCapabilitySelected('External Integration'),
            showCheckmark: true,
            backgroundColor: Colors.transparent,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
            onSelected: (bool selected) {
              provider.addOrRemoveCapability('External Integration');
            },
          ),
        ],
      );
    });
  }
}
