import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/dialog.dart';

class RecordingsStoragePermission extends StatefulWidget {
  const RecordingsStoragePermission({super.key});

  @override
  State<RecordingsStoragePermission> createState() => _RecordingsStoragePermissionState();
}

class _RecordingsStoragePermissionState extends State<RecordingsStoragePermission> {
  bool? _hasPermission;
  bool loading = false;

  changeLoadingState() => setState(() => loading = !loading);

  @override
  void initState() {
    super.initState();
    _checkPermission();
  }

  Future<void> _checkPermission() async {
    final permission = await getStoreRecordingPermission();
    if (mounted) {
      setState(() {
        _hasPermission = permission;
        if (permission != null) {
          SharedPreferencesUtil().permissionStoreRecordingsEnabled = permission;
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        title: Text(context.l10n.authorizeSavingRecordings),
      ),
      body: loading || _hasPermission == null
          ? const Center(
              child: CircularProgressIndicator(
              color: Colors.white,
            ))
          : SingleChildScrollView(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _hasPermission! ? context.l10n.thanksForAuthorizing : context.l10n.needYourPermission,
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      _hasPermission! ? context.l10n.alreadyGavePermission : context.l10n.wouldLikePermission,
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 32),
                    _buildReasonTile(
                      icon: Icons.person,
                      title: context.l10n.improveSpeechProfile,
                      description: context.l10n.improveSpeechProfileDesc,
                    ),
                    SizedBox(height: 16),
                    _buildReasonTile(
                      icon: Icons.group,
                      title: context.l10n.trainFamilyProfiles,
                      description: context.l10n.trainFamilyProfilesDesc,
                    ),
                    SizedBox(height: 16),
                    _buildReasonTile(
                      icon: Icons.trending_up,
                      title: context.l10n.enhanceTranscriptAccuracy,
                      description: context.l10n.enhanceTranscriptAccuracyDesc,
                    ),
                    const SizedBox(height: 16),
                    Container(
                      padding: const EdgeInsets.all(12),
                      child: Text(
                        context.l10n.legalNotice,
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                              color: Theme.of(context).colorScheme.onSurfaceVariant,
                            ),
                      ),
                    ),
                    const SizedBox(height: 24),
                    Center(
                      child: MaterialButton(
                        onPressed: _hasPermission! ? null : _authorize,
                        child: Text(
                          _hasPermission! ? context.l10n.alreadyAuthorized : context.l10n.authorize,
                          style: const TextStyle(
                            color: Colors.white,
                            decoration: TextDecoration.underline,
                          ),
                        ),
                      ),
                    ),
                    if (_hasPermission!)
                      Center(
                        child: TextButton(
                          onPressed: _revokeAuthorization,
                          child: Text(
                            context.l10n.revokeAuthorization,
                            style: const TextStyle(color: Colors.white),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
    );
  }

  Widget _buildReasonTile({required IconData icon, required String title, required String description}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16.0),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 24),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 4),
                Text(description, style: Theme.of(context).textTheme.bodyMedium),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _authorize() async {
    changeLoadingState();
    final success = await setRecordingPermission(true);
    changeLoadingState();
    if (success) {
      SharedPreferencesUtil().permissionStoreRecordingsEnabled = true;
      setState(() => _hasPermission = true);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.authorizationSuccessful)));
    } else {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.failedToAuthorize)));
    }
  }

  Future<void> _revokeAuthorization() async {
    changeLoadingState();
    final success = await setRecordingPermission(false);
    changeLoadingState();
    if (success) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.authorizationRevoked)));
      setState(() {
        _hasPermission = false;
      });
      SharedPreferencesUtil().permissionStoreRecordingsEnabled = false;
      showDialog(
        context: context,
        builder: (c) => getDialog(
          context,
          () => Navigator.pop(context),
          () {
            deletePermissionAndRecordings();
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.recordingsDeleted)));
            Navigator.pop(context);
          },
          context.l10n.permissionRevokedTitle,
          context.l10n.permissionRevokedMessage,
          okButtonText: context.l10n.yes,
        ),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(context.l10n.failedToRevoke)),
      );
    }
  }
}
