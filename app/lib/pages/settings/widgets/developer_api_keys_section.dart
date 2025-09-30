import 'package:flutter/material.dart';
import 'package:omi/pages/settings/widgets/create_dev_api_key_dialog.dart';
import 'package:omi/pages/settings/widgets/dev_api_key_list_item.dart';
import 'package:omi/providers/dev_api_key_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

class DeveloperApiKeysSection extends StatelessWidget {
  const DeveloperApiKeysSection({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => DevApiKeyProvider()..fetchKeys(),
      child: Builder(
        builder: (context) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Developer API Keys',
                  style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w500),
                ),
                GestureDetector(
                  onTap: () {
                    launchUrl(Uri.parse('https://docs.omi.me/doc/developer/api'));
                    MixpanelManager().pageOpened('Developer API Docs');
                  },
                  child: const Padding(
                    padding: EdgeInsets.all(8.0),
                    child: Text(
                      'Docs',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        decoration: TextDecoration.underline,
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              'Use these API keys to access your memories, conversations, and action items programmatically through the Developer API.',
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'API Keys',
                  style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
                ),
                TextButton.icon(
                  onPressed: () {
                    final provider = Provider.of<DevApiKeyProvider>(context, listen: false);
                    showDialog(
                      context: context,
                      builder: (dialogContext) => ChangeNotifierProvider.value(
                        value: provider,
                        child: const CreateDevApiKeyDialog(),
                      ),
                    );
                  },
                  icon: const Icon(Icons.add, color: Colors.white, size: 18),
                  label: const Text('Create Key', style: TextStyle(color: Colors.white)),
                  style: TextButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  ),
                )
              ],
            ),
            const SizedBox(height: 10),
            Consumer<DevApiKeyProvider>(
              builder: (context, provider, child) {
                if (provider.isLoading && provider.keys.isEmpty) {
                  return const Center(child: CircularProgressIndicator(strokeWidth: 2));
                }
                if (provider.error != null) {
                  return Center(child: Text('Error: ${provider.error}'));
                }
                if (provider.keys.isEmpty) {
                  return const Center(
                    child: Padding(
                      padding: EdgeInsets.all(16.0),
                      child: Text('No API keys found. Create one to get started.'),
                    ),
                  );
                }
                return Column(
                  children: provider.keys.map((key) => DevApiKeyListItem(apiKey: key)).toList(),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}
