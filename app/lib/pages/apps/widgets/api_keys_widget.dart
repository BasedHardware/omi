import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'app_form_fields.dart';

class ApiKeysWidget extends StatefulWidget {
  final String appId;

  const ApiKeysWidget({super.key, required this.appId});

  @override
  State<ApiKeysWidget> createState() => _ApiKeysWidgetState();
}

class _ApiKeysWidgetState extends State<ApiKeysWidget> {
  bool _isLoading = false;
  String? _deletingKeyId;
  AppApiKey? _newKey;

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      _loadApiKeys();
    });
    super.initState();
  }

  Future<void> _loadApiKeys() async {
    setState(() {
      _isLoading = true;
    });

    try {
      await Provider.of<AddAppProvider>(context, listen: false).loadApiKeys(widget.appId);
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _createApiKey() async {
    try {
      final result = await Provider.of<AddAppProvider>(context, listen: false).createApiKey(widget.appId);
      _newKey = result;
      if (mounted) _showNewKeyDialog();
    } catch (e) {
      if (mounted) {
        OmiFeedback.error(context, context.l10n.failedToCreateApiKey(readableError(e)));
      }
    }
  }

  void _showNewKeyDialog() {
    final l10n = context.l10n;
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => OmiAlertDialog(
        title: l10n.createAKey,
        content: _buildNewKeyContent(dialogContext),
        actions: [
          OmiDialogAction(
            label: l10n.done,
            isDefault: true,
            onPressed: () {
              Navigator.of(dialogContext).pop();
              setState(() {
                _newKey = null;
              });
            },
          ),
        ],
      ),
    );
  }

  Future<void> _deleteApiKey(String keyId) async {
    setState(() {
      _deletingKeyId = keyId;
    });

    try {
      await Provider.of<AddAppProvider>(context, listen: false).deleteApiKey(widget.appId, keyId);
      if (mounted) {
        OmiFeedback.confirm(context, context.l10n.apiKeyRevokedSuccessfully);
      }
    } catch (e) {
      if (mounted) {
        OmiFeedback.error(context, context.l10n.failedToRevokeApiKey(readableError(e)));
      }
    } finally {
      if (mounted) {
        setState(() {
          _deletingKeyId = null;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final provider = Provider.of<AddAppProvider>(context);

    return AppFormCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 8.0, bottom: 12.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Text(l10n.apiKeys, style: OmiType.headline),
                    OmiIconButton(
                      icon: const Icon(Icons.info_outline, size: 20),
                      color: OmiColors.textTertiary,
                      label: l10n.aboutOmiApiKeys,
                      onPressed: () {
                        showDialog(
                          context: context,
                          builder: (dialogContext) => OmiAlertDialog(
                            title: l10n.omiApiKeys,
                            message: l10n.apiKeysDescription,
                            actions: [
                              OmiDialogAction(
                                label: l10n.gotIt,
                                isDefault: true,
                                onPressed: () => Navigator.of(dialogContext).pop(),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
                  ],
                ),
                OmiButton.secondary(
                  label: l10n.createKey,
                  icon: Icons.add,
                  size: OmiButtonSize.compact,
                  onPressed: _createApiKey,
                ),
              ],
            ),
          ),
          if (_isLoading)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(OmiSpacing.md),
                child: OmiSpinner(),
              ),
            ),
          if (provider.apiKeys.isEmpty)
            Padding(
              padding: const EdgeInsets.all(OmiSpacing.md),
              child: Center(
                child: Text(
                  l10n.noApiKeysYet,
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                  textAlign: TextAlign.center,
                ),
              ),
            )
          else
            _buildKeysList(provider),
        ],
      ),
    );
  }

  Widget _buildNewKeyContent(BuildContext dialogContext) {
    final l10n = dialogContext.l10n;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Center(child: Text(l10n.yourNewKey, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600))),
        const SizedBox(height: OmiSpacing.md),
        Container(
          padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
          decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
          child: Row(
            children: [
              Expanded(
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm),
                    child: Text(_newKey!.secret!, style: OmiType.subhead.copyWith(fontFamily: 'monospace')),
                  ),
                ),
              ),
              OmiIconButton(
                icon: const Icon(Icons.copy, size: 18),
                label: l10n.copyToClipboard,
                onPressed: () => OmiClipboard.copy(dialogContext, _newKey!.secret!, what: dialogContext.l10n.apiKey),
              ),
            ],
          ),
        ),
        const SizedBox(height: OmiSpacing.md),
        Text.rich(
          TextSpan(
            children: [
              TextSpan(text: l10n.pleaseCopyKeyNow),
              TextSpan(text: l10n.willNotSeeAgain, style: const TextStyle(fontWeight: FontWeight.bold)),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildKeysList(AddAppProvider provider) {
    final l10n = context.l10n;
    return ListView.separated(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: provider.apiKeys.length,
      separatorBuilder: (context, index) => const SizedBox(height: OmiSpacing.sm),
      itemBuilder: (context, index) {
        final key = provider.apiKeys[index];
        return Container(
          decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(key.label, style: OmiType.callout.copyWith(fontWeight: FontWeight.bold)),
                    Text(
                      OmiDateFormat.of(context).dateTime(key.createdAt),
                      style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                    ),
                  ],
                ),
              ),
              SizedBox(
                width: kOmiMinTapTarget,
                height: kOmiMinTapTarget,
                child: _deletingKeyId == key.id
                    ? const Center(child: OmiSpinner(size: OmiSpinnerSize.small, color: OmiColors.danger))
                    : OmiIconButton(
                        icon: const Icon(Icons.delete_outline),
                        label: l10n.revokeKey,
                        isDestructive: true,
                        onPressed: () => _showDeleteConfirmation(key.id),
                      ),
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _showDeleteConfirmation(String keyId) async {
    final l10n = context.l10n;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.revokeApiKeyQuestion,
      message: l10n.revokeApiKeyWarning,
      confirmLabel: l10n.revoke,
      destructive: true,
    );
    if (confirmed) _deleteApiKey(keyId);
  }
}
