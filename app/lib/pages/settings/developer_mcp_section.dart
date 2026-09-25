import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/env/env.dart';
import 'package:omi/pages/settings/widgets/create_mcp_api_key_dialog.dart';
import 'package:omi/pages/settings/widgets/mcp_api_key_list_item.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/mcp_config.dart';
import 'package:omi/utils/platform/platform_manager.dart';

const _mono = 'Ubuntu Mono';

/// A compact "Docs" button that opens [url] (developer section headers).
class DeveloperDocsButton extends StatelessWidget {
  const DeveloperDocsButton({super.key, required this.url, required this.analyticsLabel});

  final String url;
  final String analyticsLabel;

  @override
  Widget build(BuildContext context) {
    return OmiButton.secondary(
      label: context.l10n.docs,
      size: OmiButtonSize.compact,
      onPressed: () {
        launchUrl(Uri.parse(url));
        PlatformManager.instance.analytics.pageOpened('$analyticsLabel Docs');
      },
    );
  }
}

/// Developer Settings → MCP: the keys, the Claude Code hosted-HTTP snippet, the Claude Desktop
/// connector flow and the server URL/auth details.
class DeveloperMcpSection extends StatelessWidget {
  const DeveloperMcpSection({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final mcpUrl = hostedMcpUrl(Env.apiBaseUrl ?? '');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OmiSectionHeader(
          l10n.mcp,
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const DeveloperDocsButton(url: 'https://docs.omi.me/doc/developer/MCP', analyticsLabel: 'MCP'),
              const SizedBox(width: OmiSpacing.xs),
              OmiButton.secondary(
                label: l10n.createKey,
                leading: const FaIcon(FontAwesomeIcons.plus),
                size: OmiButtonSize.compact,
                onPressed: () => showDialog(context: context, builder: (_) => const CreateMcpApiKeyDialog()),
              ),
            ],
          ),
        ),
        const _McpKeysList(),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            OmiSettingsRow(
              leading: const FaIcon(FontAwesomeIcons.terminal),
              title: l10n.claudeCode,
              subtitle: l10n.addToClaudeCodeConfig,
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: OmiSpacing.md),
                  _CodeBlock(child: _claudeCodeConfigSpan(mcpUrl)),
                  const SizedBox(height: OmiSpacing.sm),
                  OmiButton.secondary(
                    label: l10n.copyConfig,
                    leading: const FaIcon(FontAwesomeIcons.copy),
                    expand: true,
                    onPressed: () => OmiClipboard.copy(context, hostedMcpConfigJson(mcpUrl)),
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            OmiSettingsRow(
              leading: const FaIcon(FontAwesomeIcons.desktop),
              title: l10n.claudeDesktop,
              subtitle: l10n.claudeDesktopConnectorSetup,
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.md),
              child: _CopyableValue(value: mcpUrl, what: l10n.serverUrl),
            ),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            OmiSettingsRow(
              leading: const FaIcon(FontAwesomeIcons.server),
              title: l10n.mcpServer,
              subtitle: l10n.connectAiAssistantsToYourData,
            ),
            Padding(
              padding: const EdgeInsets.all(OmiSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _Label(l10n.serverUrl),
                  const SizedBox(height: OmiSpacing.xs),
                  _CopyableValue(value: mcpUrl, what: l10n.serverUrl),
                  const SizedBox(height: OmiSpacing.lg),
                  _Label(l10n.apiKeyAuth),
                  const SizedBox(height: OmiSpacing.xs),
                  _KeyValue(
                    label: l10n.header,
                    value: 'Authorization: Bearer <key>',
                  ),
                  const SizedBox(height: OmiSpacing.lg),
                  _Label(l10n.oAuth),
                  const SizedBox(height: OmiSpacing.xs),
                  Text(
                    l10n.mcpOAuthSetup,
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                  ),
                  const SizedBox(height: OmiSpacing.sm),
                  _KeyValue(label: l10n.clientId, value: kMcpOAuthClientId, copyable: true),
                  const SizedBox(height: OmiSpacing.xs),
                  _KeyValue(label: l10n.clientSecret, value: l10n.leaveBlank, isHint: true),
                ],
              ),
            ),
          ],
        ),
      ],
    );
  }

  static TextSpan _claudeCodeConfigSpan(String mcpUrl) {
    return TextSpan(
      children: [
        for (final (kind, text) in hostedMcpConfigTokens(mcpUrl))
          TextSpan(
            text: text,
            style: switch (kind) {
              McpJsonToken.plain => null,
              McpJsonToken.key => const TextStyle(color: OmiColors.textSecondary),
              McpJsonToken.string => const TextStyle(color: OmiColors.warning),
            },
          ),
      ],
    );
  }
}

class _McpKeysList extends StatelessWidget {
  const _McpKeysList();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<McpProvider>(
      builder: (context, provider, _) {
        if (provider.isLoading && provider.keys.isEmpty) {
          return const Padding(padding: EdgeInsets.all(OmiSpacing.xl), child: OmiSpinner());
        }
        if (provider.error != null) {
          return OmiErrorState(
            message: l10n.errorWithMessage(provider.error!),
            onRetry: () => provider.fetchKeys(),
          );
        }
        if (provider.keys.isEmpty) {
          return OmiEmptyState(
              glyph: const FaIcon(FontAwesomeIcons.key), title: l10n.noApiKeysYet, message: l10n.createKeyToGetStarted);
        }
        return OmiSettingsGroup(children: [for (final key in provider.keys) McpApiKeyListItem(apiKey: key)]);
      },
    );
  }
}

class _Label extends StatelessWidget {
  const _Label(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600));
  }
}

class _CodeBlock extends StatelessWidget {
  const _CodeBlock({required this.child});

  final InlineSpan child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.sm),
      decoration: BoxDecoration(
        color: OmiColors.surface0,
        borderRadius: OmiRadius.mdAll,
        border: Border.all(color: OmiColors.surface2),
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Text.rich(
          TextSpan(style: OmiType.caption.copyWith(fontFamily: _mono, height: 1.6), children: [child]),
        ),
      ),
    );
  }
}

/// A monospace value in a well; tapping copies it.
class _CopyableValue extends StatelessWidget {
  const _CopyableValue({required this.value, required this.what});

  final String value;
  final String what;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: context.l10n.labelCopied(what),
      excludeSemantics: true,
      child: InkWell(
        borderRadius: OmiRadius.mdAll,
        onTap: () => OmiClipboard.copy(context, value, what: what),
        child: Container(
          constraints: const BoxConstraints(minHeight: 44),
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.sm),
          decoration: BoxDecoration(
            color: OmiColors.surface0,
            borderRadius: OmiRadius.mdAll,
            border: Border.all(color: OmiColors.surface2),
          ),
          child: Row(
            children: [
              Expanded(child: Text(value, style: OmiType.footnote.copyWith(fontFamily: _mono))),
              const SizedBox(width: OmiSpacing.xs),
              const FaIcon(FontAwesomeIcons.copy, size: 14, color: OmiColors.textTertiary),
            ],
          ),
        ),
      ),
    );
  }
}

class _KeyValue extends StatelessWidget {
  const _KeyValue({required this.label, required this.value, this.copyable = false, this.isHint = false});

  final String label;
  final String value;
  final bool copyable;
  final bool isHint;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          flex: 2,
          child: Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
        ),
        Expanded(
          flex: 3,
          child: copyable
              ? _CopyableValue(value: value, what: label)
              : Text(
                  value,
                  style: OmiType.footnote.copyWith(
                    color: OmiColors.textSecondary,
                    fontFamily: isHint ? null : _mono,
                    fontStyle: isHint ? FontStyle.italic : null,
                  ),
                ),
        ),
      ],
    );
  }
}
