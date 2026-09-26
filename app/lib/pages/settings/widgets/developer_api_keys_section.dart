import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/pages/settings/widgets/create_dev_api_key_sheet.dart';
import 'package:omi/pages/settings/widgets/dev_api_key_list_item.dart';
import 'package:omi/providers/dev_api_key_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The "Developer API" section of Developer Settings: docs link, Create Key, and the key list.
class DeveloperApiKeysSection extends StatelessWidget {
  const DeveloperApiKeysSection({super.key});

  static const _docsUrl = 'https://docs.omi.me/doc/developer/api';

  Widget _card(Widget child) {
    return DecoratedBox(
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: child,
    );
  }

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => DevApiKeyProvider()..fetchKeys(),
      child: Builder(
        builder: (context) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            OmiSectionHeader(
              context.l10n.developerApi,
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  OmiButton.secondary(
                    label: context.l10n.docs,
                    size: OmiButtonSize.compact,
                    onPressed: () {
                      launchUrl(Uri.parse(_docsUrl));
                      PlatformManager.instance.analytics.pageOpened('Developer API Docs');
                    },
                  ),
                  const SizedBox(width: OmiSpacing.xs),
                  OmiButton.secondary(
                    label: context.l10n.createKey,
                    leading: const FaIcon(FontAwesomeIcons.plus),
                    size: OmiButtonSize.compact,
                    onPressed: () {
                      final provider = Provider.of<DevApiKeyProvider>(context, listen: false);
                      CreateDevApiKeySheet.show(context, provider);
                    },
                  ),
                ],
              ),
            ),

            // API Keys List
            Consumer<DevApiKeyProvider>(
              builder: (context, provider, child) {
                if (provider.isLoading && provider.keys.isEmpty) {
                  return _card(
                      const Padding(padding: EdgeInsets.all(OmiSpacing.xl), child: Center(child: OmiSpinner())));
                }
                if (provider.error != null) {
                  return _card(
                    OmiErrorState(
                      message: context.l10n.errorWithMessage(provider.error!),
                      onRetry: () => provider.fetchKeys(force: true),
                    ),
                  );
                }
                if (provider.keys.isEmpty) {
                  return _card(
                    OmiEmptyState(
                      glyph: const FaIcon(FontAwesomeIcons.key),
                      title: context.l10n.noApiKeys,
                      message: context.l10n.createAKeyToGetStarted,
                    ),
                  );
                }
                return OmiSettingsGroup(children: [for (final key in provider.keys) DevApiKeyListItem(apiKey: key)]);
              },
            ),
          ],
        ),
      ),
    );
  }
}
