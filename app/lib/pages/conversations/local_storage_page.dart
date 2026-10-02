import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Settings page: keep recordings on this phone without a size limit.
class LocalStoragePage extends StatefulWidget {
  const LocalStoragePage({super.key});

  @override
  State<LocalStoragePage> createState() => _LocalStoragePageState();
}

class _LocalStoragePageState extends State<LocalStoragePage> {
  bool _isSaving = false;

  Future<void> _toggleLocalStorage(bool value) async {
    final l10n = context.l10n;
    if (value) {
      final confirmed = await showOmiConfirm(
        context,
        title: l10n.privacyNotice,
        message: l10n.recordingsMayCaptureOthers,
        confirmLabel: l10n.enable,
      );
      if (!confirmed || !mounted) return;
    }

    setState(() => _isSaving = true);
    try {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = value;
      if (mounted) context.read<SyncProvider>().refreshWals();
      if (!mounted) return;
      setState(() => _isSaving = false);
      OmiFeedback.confirm(context, value ? l10n.localStorageEnabled : l10n.localStorageDisabled);
    } catch (e) {
      if (!mounted) return;
      setState(() => _isSaving = false);
      OmiFeedback.error(context, l10n.failedToUpdateSettings(readableError(e)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final isEnabled = SharedPreferencesUtil().unlimitedLocalStorageEnabled;

    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.storeAudioOnPhone)),
      body: ListView(
        padding: const EdgeInsets.all(OmiSpacing.md),
        children: [
          OmiSettingsGroup(
            footer: l10n.storeAudioDescription,
            children: [
              OmiSettingsRow.toggle(
                leading: const FaIcon(FontAwesomeIcons.mobile),
                title: l10n.enableLocalStorage,
                value: isEnabled,
                onChanged: _isSaving ? null : _toggleLocalStorage,
              ),
            ],
          ),
        ],
      ),
    );
  }
}
