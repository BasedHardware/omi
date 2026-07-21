import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

class DataPrivacyPage extends StatefulWidget {
  const DataPrivacyPage({super.key});

  @override
  State<DataPrivacyPage> createState() => _DataPrivacyPageState();
}

class _DataPrivacyPageState extends State<DataPrivacyPage> {
  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.dataPrivacyPageOpened();
  }

  Widget _buildEncryptionBanner(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1A),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF35343B), width: 1),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: Colors.deepPurple.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(Icons.lock_outline, color: Colors.deepPurple.shade200, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: RichText(
              text: TextSpan(
                style: TextStyle(fontSize: 14, color: Colors.grey.shade300, height: 1.5),
                children: [
                  TextSpan(text: '${context.l10n.dataEncryptedBanner} '),
                  TextSpan(
                    text: context.l10n.learnMore,
                    style: TextStyle(
                      color: Colors.deepPurple.shade200,
                      decoration: TextDecoration.underline,
                      decorationColor: Colors.deepPurple.shade200,
                    ),
                    recognizer: TapGestureRecognizer()
                      ..onTap = () async {
                        final url = Uri.parse('https://www.omi.me/pages/privacy');
                        if (await canLaunchUrl(url)) {
                          await launchUrl(url, mode: LaunchMode.externalApplication);
                        }
                      },
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _getAccessDescription(BuildContext context, App app) {
    List<String> accessTypes = [];
    if (app.hasConversationsAccess()) {
      accessTypes.add(context.l10n.conversations);
    }
    if (app.hasMemoriesAccess()) {
      accessTypes.add(context.l10n.memories);
    }

    String accessDescription = '';
    if (accessTypes.isNotEmpty) {
      accessDescription = context.l10n.accessesDataTypes(accessTypes.join(' & '));
    }

    final trigger = app.externalIntegration?.getTriggerOnString();
    String triggerDescription = '';
    if (trigger != null && trigger != 'Unknown') {
      triggerDescription = context.l10n.triggeredByType(trigger.toLowerCase());
    }

    if (accessDescription.isNotEmpty && triggerDescription.isNotEmpty) {
      return context.l10n.accessesAndTriggeredBy(accessDescription, triggerDescription);
    }
    if (accessDescription.isNotEmpty) {
      return '$accessDescription.';
    }
    if (triggerDescription.isNotEmpty) {
      return context.l10n.isTriggeredBy(triggerDescription);
    }

    return context.l10n.noSpecificDataAccessConfigured;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<UserProvider>(
      builder: (context, provider, child) {
        final isLoading = provider.isLoading;
        final isMigrating = provider.isMigrating;

        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            backgroundColor: Theme.of(context).colorScheme.primary,
            automaticallyImplyLeading: true,
            title: Text(context.l10n.dataPrivacy, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w600)),
            centerTitle: true,
            leading: IconButton(icon: const Icon(Icons.arrow_back_ios_new), onPressed: () => Navigator.pop(context)),
            elevation: 0,
          ),
          body: Stack(
            children: [
              ListView(
                padding: const EdgeInsets.all(16.0),
                children: [
                  _buildEncryptionBanner(context),
                  const SizedBox(height: 32),
                  Consumer<AppProvider>(
                    builder: (context, appProvider, child) {
                      final appsWithDataAccess =
                          appProvider.apps.where((app) => app.enabled && app.worksExternally()).toList();

                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            context.l10n.appAccess,
                            style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                          ),
                          const SizedBox(height: 8),
                          Text(context.l10n.appAccessDesc, style: TextStyle(color: Colors.grey.shade400, fontSize: 14)),
                          const SizedBox(height: 16),
                          if (appsWithDataAccess.isEmpty)
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.symmetric(vertical: 32.0, horizontal: 16.0),
                              decoration: BoxDecoration(
                                color: const Color(0xFF1A1A1A),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Center(
                                child: Column(
                                  children: [
                                    Icon(Icons.apps_outlined, color: Colors.grey.shade600, size: 32),
                                    const SizedBox(height: 16),
                                    Text(
                                      context.l10n.noAppsExternalAccess,
                                      textAlign: TextAlign.center,
                                      style: TextStyle(color: Colors.grey.shade400),
                                    ),
                                  ],
                                ),
                              ),
                            )
                          else
                            Column(
                              children: appsWithDataAccess.map((app) {
                                return Card(
                                  color: const Color(0xFF1A1A1A),
                                  margin: const EdgeInsets.only(bottom: 10),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(12),
                                    side: BorderSide(color: Color(0xFF35343B), width: 1),
                                  ),
                                  elevation: 0,
                                  clipBehavior: Clip.antiAlias,
                                  child: ListTile(
                                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                                    leading: CircleAvatar(backgroundImage: NetworkImage(app.getImageUrl())),
                                    title: Text(app.getName()),
                                    subtitle: Text(
                                      _getAccessDescription(context, app),
                                      style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
                                    ),
                                    trailing: const Icon(Icons.arrow_forward_ios, size: 16),
                                    onTap: () {
                                      routeToPage(context, AppDetailPage(app: app, preventAutoOpenHomePage: true));
                                    },
                                  ),
                                );
                              }).toList(),
                            ),
                        ],
                      );
                    },
                  ),
                  const SizedBox(height: 32),
                ],
              ),
              if (isLoading && !isMigrating)
                Container(
                  color: Colors.black.withValues(alpha: 0.5),
                  child: const Center(child: CircularProgressIndicator()),
                ),
            ],
          ),
        );
      },
    );
  }
}
