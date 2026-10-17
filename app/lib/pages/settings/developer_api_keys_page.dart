import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/widgets/create_dev_api_key_sheet.dart';
import 'package:omi/pages/settings/widgets/dev_api_key_list_item.dart';
import 'package:omi/pages/settings/widgets/developer_api_keys_section.dart';
import 'package:omi/providers/dev_api_key_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A key identity, name and prefix the native list can show. Rows use index ids and carry only this
/// metadata; a key outside these bounds keeps the complete Flutter page.
bool nativeKeyMetadataValid({required String id, required String name, required String prefix}) =>
    id.isNotEmpty &&
    id.length <= 256 &&
    name.length <= 1000 &&
    prefix.length <= 64 &&
    prefix.codeUnits.every((unit) => unit >= 0x21 && unit <= 0x7E);

/// Settings > Developer > Developer API: the docs link, Create Key and the key list, over the same
/// [DevApiKeyProvider] the Flutter section uses.
class DeveloperApiKeysPage extends StatefulWidget {
  const DeveloperApiKeysPage({super.key, @visibleForTesting this.provider});

  /// Replaces the page's own key owner in tests; the page still fetches through it and disposes it.
  final DevApiKeyProvider? provider;

  @override
  State<DeveloperApiKeysPage> createState() => _DeveloperApiKeysPageState();
}

class _DeveloperApiKeysPageState extends State<DeveloperApiKeysPage> {
  /// A create sheet is opening or open; a second tap opens nothing.
  bool _creating = false;

  Future<void> _create(DevApiKeyProvider provider) async {
    if (_creating) return;
    setState(() => _creating = true);
    try {
      await CreateDevApiKeySheet.show(context, provider);
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => (widget.provider ?? DevApiKeyProvider())..fetchKeys(),
      child: Consumer<DevApiKeyProvider>(builder: (context, provider, _) => _page(context, provider)),
    );
  }

  Widget _page(BuildContext context, DevApiKeyProvider provider) {
    final l10n = context.l10n;
    final classic = Scaffold(
      appBar: AppBar(title: Text(l10n.developerApi), leading: const OmiBackButton()),
      body: const SingleChildScrollView(padding: EdgeInsets.all(OmiSpacing.lg), child: DeveloperApiKeysContent()),
    );
    final keys = provider.keys;
    if (!nativePresentationEnabled ||
        !keys.every((key) => nativeKeyMetadataValid(id: key.id, name: key.name, prefix: key.keyPrefix))) {
      return classic;
    }
    final loading = provider.isLoading && keys.isEmpty;
    final failed = provider.error != null && keys.isEmpty;
    return Scaffold(
      body: IosNativeSurface(
        title: l10n.developerApi,
        fallback: classic,
        loading: loading,
        failed: failed,
        errorMessage: l10n.couldNotLoadApiKeys,
        empty: l10n.noApiKeys,
        onRefresh: (_) => provider.fetchKeys(force: true),
        toolbar: [
          NativeRow('dev_keys_back', l10n.back,
              symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
          NativeRow('dev_keys_create', l10n.createKey,
              symbol: 'plus', enabled: !_creating, action: (_) => _create(provider)),
        ],
        sections: [
          NativeSection('dev_keys_links', [
            NativeRow('dev_keys_docs', l10n.docs,
                symbol: 'arrow.up.right', action: (_) => DeveloperApiKeysSection.openDocs()),
          ]),
          NativeSection('dev_keys', [
            if (keys.isEmpty && !loading && !failed)
              NativeRow('dev_keys_empty', l10n.noApiKeys,
                  kind: 'label', symbol: 'key', subtitle: l10n.createAKeyToGetStarted),
            for (final (index, key) in keys.indexed)
              NativeRow('dev_key:$index', key.name,
                  kind: 'menu',
                  symbol: 'key',
                  subtitle: [
                    '${key.keyPrefix}***',
                    OmiDateFormat.of(context).date(key.createdAt),
                    devKeyScopeSummary(l10n, key.scopes).join(', '),
                  ].where((part) => part.isNotEmpty).join(' · '),
                  options: {'revoke': l10n.revoke}, action: (_) async {
                final confirmed = await confirmDevApiKeyRevoke(context, provider, key);
                // The owner restores a key it could not revoke; say so instead of letting it reappear.
                if (confirmed &&
                    context.mounted &&
                    provider.keys.any((current) => current.id == key.id) &&
                    provider.error != null) {
                  OmiFeedback.error(context, l10n.failedToRevokeApiKey(provider.error!));
                }
              }),
          ]),
        ],
      ),
    );
  }
}
