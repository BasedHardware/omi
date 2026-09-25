import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

/// Settings page: keep a private copy of recordings in the cloud.
class PrivateCloudSyncPage extends StatefulWidget {
  const PrivateCloudSyncPage({super.key});

  @override
  State<PrivateCloudSyncPage> createState() => _PrivateCloudSyncPageState();
}

class _PrivateCloudSyncPageState extends State<PrivateCloudSyncPage> {
  bool _isSaving = false;

  Future<void> _togglePrivateCloudSync(bool value) async {
    final userProvider = context.read<UserProvider>();
    final l10n = context.l10n;
    if (value) {
      final confirmed = await showOmiConfirm(
        context,
        title: l10n.enableCloudStorage,
        message: l10n.cloudStorageDialogMessage,
        confirmLabel: l10n.enable,
      );
      if (!confirmed || !mounted) return;
    }

    setState(() => _isSaving = true);
    try {
      await userProvider.setPrivateCloudSync(value);
      if (!mounted) return;
      setState(() => _isSaving = false);
      OmiFeedback.confirm(context, value ? l10n.cloudStorageEnabled : l10n.cloudStorageDisabled);
    } catch (e) {
      Logger.debug('Error toggling cloud storage: $e');
      if (!mounted) return;
      setState(() => _isSaving = false);
      OmiFeedback.error(context, l10n.failedToUpdateSettings(readableError(e)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Consumer<UserProvider>(
      builder: (context, userProvider, child) {
        return Scaffold(
          appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.storeAudioOnCloud)),
          body: userProvider.isLoading
              ? const OmiLoadingState()
              : ListView(
                  padding: const EdgeInsets.all(OmiSpacing.md),
                  children: [
                    OmiSettingsGroup(
                      footer: l10n.storeAudioCloudDescription,
                      children: [
                        OmiSettingsRow.toggle(
                          leading: const FaIcon(FontAwesomeIcons.cloud),
                          title: l10n.enableCloudStorage,
                          value: userProvider.privateCloudSyncEnabled,
                          onChanged: _isSaving ? null : _togglePrivateCloudSync,
                        ),
                      ],
                    ),
                  ],
                ),
        );
      },
    );
  }
}
