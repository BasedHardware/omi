import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/env/env.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_secret.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/developer_api_keys_page.dart';
import 'package:omi/pages/settings/developer_mcp_section.dart';
import 'package:omi/pages/settings/widgets/create_mcp_api_key_dialog.dart';
import 'package:omi/pages/settings/widgets/mcp_api_key_created_dialog.dart';
import 'package:omi/pages/settings/widgets/mcp_api_key_list_item.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/mcp_config.dart';

/// Settings > Developer > MCP: keys, the Claude Code config, Claude Desktop and the server/OAuth
/// details, over the shared [McpProvider]. Creation and revocation stay with that provider.
class DeveloperMcpPage extends StatefulWidget {
  const DeveloperMcpPage({super.key});

  @override
  State<DeveloperMcpPage> createState() => _DeveloperMcpPageState();
}

class _DeveloperMcpPageState extends State<DeveloperMcpPage> {
  bool _creating = false;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = context.watch<McpProvider>();
    final classic = Scaffold(
      appBar: AppBar(title: Text(l10n.mcp), leading: const OmiBackButton()),
      body: const SingleChildScrollView(padding: EdgeInsets.all(OmiSpacing.lg), child: DeveloperMcpSection()),
    );
    final keys = provider.keys;
    if (!nativePresentationEnabled ||
        !keys.every((key) => nativeKeyMetadataValid(id: key.id, name: key.name, prefix: key.keyPrefix))) {
      return classic;
    }
    final mcpUrl = hostedMcpUrl(Env.apiBaseUrl ?? '');
    final config = hostedMcpConfigJson(mcpUrl);
    final loading = provider.isLoading && keys.isEmpty;
    final failed = provider.error != null && keys.isEmpty;
    NativeRow copy(String id, String title, String value, {String subtitle = '', String? what}) => NativeRow(id, title,
        subtitle: subtitle, symbol: 'doc.on.doc', action: (_) => OmiClipboard.copy(context, value, what: what));
    return Scaffold(
      body: IosNativeSurface(
        title: l10n.mcp,
        fallback: classic,
        loading: loading,
        failed: failed,
        errorMessage: l10n.couldNotLoadApiKeys,
        empty: l10n.noApiKeysYet,
        onRefresh: (_) => provider.fetchKeys(),
        toolbar: [
          NativeRow('mcp_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
          NativeRow('mcp_docs', l10n.docs,
              symbol: 'arrow.up.right', action: (_) => DeveloperDocsButton.open(developerMcpDocsUrl, 'MCP')),
          NativeRow('mcp_create', l10n.createKey, symbol: 'plus', enabled: !_creating, action: (_) => _create()),
        ],
        sections: [
          NativeSection('mcp_keys', [
            if (keys.isEmpty && !loading && !failed)
              NativeRow('mcp_keys_empty', l10n.noApiKeysYet,
                  kind: 'label', symbol: 'key', subtitle: l10n.createKeyToGetStarted),
            for (final (index, key) in keys.indexed)
              NativeRow('mcp_key:$index', key.name,
                  kind: 'menu',
                  symbol: 'key',
                  subtitle: '${key.keyPrefix}*** · ${OmiDateFormat.of(context).date(key.createdAt)}',
                  options: {'revoke': l10n.revoke}, action: (_) async {
                final confirmed = await confirmMcpApiKeyRevoke(context, provider, key);
                // The owner restores a key it could not revoke; say so instead of letting it reappear.
                if (confirmed &&
                    context.mounted &&
                    provider.keys.any((current) => current.id == key.id) &&
                    provider.error != null) {
                  OmiFeedback.error(context, l10n.failedToRevokeApiKey(provider.error!));
                }
              }),
          ]),
          NativeSection('mcp_claude_code', [
            NativeRow('mcp_claude_code', l10n.claudeCode,
                kind: 'label', symbol: 'terminal', subtitle: l10n.addToClaudeCodeConfig),
            NativeRow('mcp_config_json', l10n.claudeCode, kind: 'rich_text', blocks: [
              {'kind': 'code', 'text': config, 'indent': 0, 'prefix': ''},
            ]),
            copy('mcp_copy_config', l10n.copyConfig, config),
          ]),
          NativeSection('mcp_claude_desktop', [
            NativeRow('mcp_claude_desktop', l10n.claudeDesktop,
                kind: 'label', symbol: 'desktopcomputer', subtitle: l10n.claudeDesktopConnectorSetup),
            copy('mcp_desktop_url', mcpUrl, mcpUrl, subtitle: l10n.serverUrl, what: l10n.serverUrl),
          ]),
          NativeSection('mcp_server', [
            NativeRow('mcp_server', l10n.mcpServer,
                kind: 'label', symbol: 'server.rack', subtitle: l10n.connectAiAssistantsToYourData),
            copy('mcp_server_url', mcpUrl, mcpUrl, subtitle: l10n.serverUrl, what: l10n.serverUrl),
          ]),
          NativeSection('mcp_api_key_auth',
              [NativeRow('mcp_auth_header', l10n.header, kind: 'label', subtitle: mcpAuthHeaderTemplate)],
              title: l10n.apiKeyAuth),
          NativeSection(
              'mcp_oauth',
              [
                NativeRow('mcp_oauth_setup', l10n.mcpOAuthSetup, kind: 'label'),
                copy('mcp_client_id', kMcpOAuthClientId, kMcpOAuthClientId,
                    subtitle: l10n.clientId, what: l10n.clientId),
                NativeRow('mcp_client_secret', l10n.clientSecret, kind: 'label', subtitle: l10n.leaveBlank),
              ],
              title: l10n.oAuth),
        ],
      ),
    );
  }

  /// Asks for a name natively (again, with a hint, while it is blank), creates the key under a
  /// blocking activity and reveals it once. A host without native modals keeps the Flutter dialog.
  Future<void> _create() async {
    if (_creating) return;
    final provider = context.read<McpProvider>();
    final owner = AuthService.instance.captureSessionSnapshot();
    // Held from the first tap, so a second Create never starts another prompt or key.
    setState(() => _creating = true);
    try {
      await _createNamed(provider, owner);
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  Future<void> _createNamed(McpProvider provider, AuthSessionSnapshot? owner) async {
    final l10n = context.l10n;
    var blank = false;
    String name;
    while (true) {
      final result = await showIosNativeModal(context, title: l10n.createNewKey, guardEdits: true, actions: [
        NativeRow('cancel', l10n.cancel, symbol: 'xmark'),
        NativeRow('create', l10n.create, symbol: 'checkmark'),
      ], sections: [
        NativeSection(
            'mcp_new_key',
            [
              NativeRow('mcp_key_name', l10n.keyNameHint, kind: 'text', value: '', maximumLength: 100),
              if (blank)
                NativeRow('mcp_key_name_required', l10n.pleaseEnterAName,
                    kind: 'label', symbol: 'exclamationmark.circle'),
            ],
            title: l10n.name),
      ]);
      if (!mounted) return;
      if (result == null) {
        await showDialog<void>(context: context, builder: (_) => const CreateMcpApiKeyDialog());
        return;
      }
      if (result.action != 'create') return;
      name = (result.values['mcp_key_name'] as String? ?? '').trim();
      if (name.isNotEmpty) break;
      blank = true;
    }
    final activity = await showIosNativeActivity(context, label: l10n.creating);
    McpApiKeyCreated? created;
    try {
      created = await provider.createKey(name);
    } finally {
      // The overlay covers every route; it is gone before anything else is presented.
      await activity?.dismiss();
    }
    if (!mounted || owner == null || !AuthService.instance.isSessionSnapshotCurrent(owner)) return;
    if (created == null) {
      final error = provider.error;
      OmiFeedback.error(
          context, error != null ? l10n.failedToCreateKeyWithError(error) : l10n.failedToCreateKeyTryAgain);
      return;
    }
    final key = created;
    await showIosNativeSecretSheet(
      context,
      title: l10n.keyCreated,
      message: l10n.keyCreatedMessage,
      secretLabel: l10n.keyWord,
      secret: key.key,
      copyLabel: l10n.copy,
      doneLabel: l10n.done,
      onCopy: () => OmiClipboard.copy(context, key.key, what: l10n.keyWord),
      showClassic: () => showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (_) => McpApiKeyCreatedDialog(apiKey: key),
      ),
    );
  }
}
