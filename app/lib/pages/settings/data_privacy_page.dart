import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/ui.dart';
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
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.lgAll,
        border: Border.all(color: OmiColors.border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
            child: const Icon(Icons.lock_outline, color: OmiColors.textPrimary, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: RichText(
              text: TextSpan(
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.5),
                children: [
                  TextSpan(text: '${context.l10n.dataEncryptedBanner} '),
                  TextSpan(
                    text: context.l10n.learnMore,
                    style: const TextStyle(
                      color: OmiColors.textPrimary,
                      decoration: TextDecoration.underline,
                      decorationColor: OmiColors.textPrimary,
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
          appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.dataPrivacy)),
          body: Stack(
            children: [
              ListView(
                padding: const EdgeInsets.all(OmiSpacing.md),
                children: [
                  _buildEncryptionBanner(context),
                  const SizedBox(height: OmiSpacing.xxl),
                  Consumer<AppProvider>(
                    builder: (context, appProvider, child) {
                      final appsWithDataAccess =
                          appProvider.apps.where((app) => app.enabled && app.worksExternally()).toList();

                      if (appsWithDataAccess.isEmpty) {
                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            OmiSectionHeader(context.l10n.appAccess, subtitle: context.l10n.appAccessDesc),
                            Container(
                              decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
                              child: OmiEmptyState(icon: Icons.apps_outlined, title: context.l10n.noAppsExternalAccess),
                            ),
                          ],
                        );
                      }
                      return OmiSettingsGroup(
                        header: context.l10n.appAccess,
                        headerSubtitle: context.l10n.appAccessDesc,
                        children: [
                          for (final app in appsWithDataAccess)
                            OmiSettingsRow(
                              leading: CircleAvatar(radius: 16, backgroundImage: NetworkImage(app.getImageUrl())),
                              title: app.getName(),
                              subtitle: _getAccessDescription(context, app),
                              onTap: () {
                                routeToPage(context, AppDetailPage(app: app, preventAutoOpenHomePage: true));
                              },
                            ),
                        ],
                      );
                    },
                  ),
                  const SizedBox(height: OmiSpacing.xxl),
                ],
              ),
              if (isLoading && !isMigrating)
                Container(
                  color: Colors.black.withValues(alpha: 0.5),
                  child: const Center(child: OmiSpinner(size: OmiSpinnerSize.large)),
                ),
            ],
          ),
        );
      },
    );
  }
}
