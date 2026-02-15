import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/settings/widgets/create_dev_api_key_sheet.dart';
import 'package:omi/pages/settings/widgets/dev_api_key_list_item.dart';
import 'package:omi/providers/dev_api_key_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';

class DeveloperApiKeysSection extends StatelessWidget {
  const DeveloperApiKeysSection({super.key});

  Widget _buildDocsButton(BuildContext context, String url, String label) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        onTap: () {
          launchUrl(Uri.parse(url));
          MixpanelManager().pageOpened('$label Docs');
        },
        borderRadius: BorderRadius.circular(20),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Text(
            context.l10n.docs,
            style: const TextStyle(
              color: Colors.black,
              fontWeight: FontWeight.w600,
              fontSize: 12,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCreateKeyButton(BuildContext context) {
    return GestureDetector(
      onTap: () {
        final provider = Provider.of<DevApiKeyProvider>(context, listen: false);
        CreateDevApiKeySheet.show(context, provider);
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.1),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const FaIcon(FontAwesomeIcons.plus, color: Colors.white, size: 10),
            const SizedBox(width: 6),
            Text(
              context.l10n.createKey,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => DevApiKeyProvider()..fetchKeys(),
      child: Builder(
        builder: (context) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Section Header with Docs and Create Key buttons
            Padding(
              padding: const EdgeInsets.only(left: 4, right: 4, bottom: 12),
              child: Row(
                children: [
                  Text(
                    context.l10n.developerApi,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 20,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const Spacer(),
                  _buildDocsButton(context, 'https://docs.omi.me/doc/developer/api', 'Developer API'),
                  const SizedBox(width: 8),
                  _buildCreateKeyButton(context),
                ],
              ),
            ),

            // API Keys List
            Consumer<DevApiKeyProvider>(
              builder: (context, provider, child) {
                if (provider.isLoading && provider.keys.isEmpty) {
                  return Container(
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1C1C1E),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Center(
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    ),
                  );
                }
                if (provider.error != null) {
                  return Container(
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1C1C1E),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Center(
                      child: Text(
                        context.l10n.errorWithMessage(provider.error!),
                        style: TextStyle(color: Colors.red.shade300),
                      ),
                    ),
                  );
                }
                if (provider.keys.isEmpty) {
                  return Container(
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1C1C1E),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      children: [
                        FaIcon(FontAwesomeIcons.key, color: Colors.grey.shade600, size: 28),
                        const SizedBox(height: 12),
                        Text(
                          context.l10n.noApiKeys,
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 15),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          context.l10n.createAKeyToGetStarted,
                          style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                        ),
                      ],
                    ),
                  );
                }
                return Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFF1C1C1E),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Column(
                    children: provider.keys.asMap().entries.map((entry) {
                      final index = entry.key;
                      final key = entry.value;
                      return Column(
                        children: [
                          DevApiKeyListItem(apiKey: key),
                          if (index < provider.keys.length - 1) const Divider(height: 1, color: Color(0xFF3C3C43)),
                        ],
                      );
                    }).toList(),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}
