import 'package:flutter/material.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:provider/provider.dart';

class ExternalIntegrationsSection extends StatelessWidget {
  const ExternalIntegrationsSection({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AppProvider>(
      builder: (context, appProvider, child) {
        final enabledExternalApps = appProvider.apps.where((app) => app.enabled && app.worksExternally()).toList();

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'External App Access',
              style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            const Text(
              'The following installed apps have external integrations and can access your data, such as conversations and memories.',
              style: TextStyle(color: Colors.grey, fontSize: 14),
            ),
            const SizedBox(height: 16),
            if (enabledExternalApps.isEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(vertical: 24.0),
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1A1A),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Center(
                  child: Text(
                    'No external apps have access to your data.',
                    style: TextStyle(color: Colors.grey),
                  ),
                ),
              )
            else
              Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1A1A),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: ListView.separated(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: enabledExternalApps.length,
                  itemBuilder: (context, index) {
                    final app = enabledExternalApps[index];
                    return ListTile(
                      leading: CircleAvatar(
                        backgroundImage: NetworkImage(app.getImageUrl()),
                      ),
                      title: Text(app.getName()),
                      trailing: const Icon(Icons.arrow_forward_ios, size: 16),
                      onTap: () {
                        routeToPage(context, AppDetailPage(app: app));
                      },
                    );
                  },
                  separatorBuilder: (context, index) => const Divider(
                    height: 1,
                    color: Colors.grey,
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}
