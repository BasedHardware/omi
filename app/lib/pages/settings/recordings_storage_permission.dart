import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/services/translation_service.dart';

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
        title:  Text(TranslationService.translate( 'Authorize Saving Recordings')),
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
                      _hasPermission! ? TranslationService.translate( "Thanks for authorizing!") :TranslationService.translate(  "We need your permission"),
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      _hasPermission!
                          ? TranslationService.translate( "You've already given us permission to save your recordings. Here's a reminder of why we need it:")
                          : TranslationService.translate( "We'd like your permission to save your voice recordings. Here's why:"),
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 32),
                    _buildReasonTile(
                      icon: Icons.person,
                      title: TranslationService.translate( "Improve Your Speech Profile"),
                      description: TranslationService.translate( "We use recordings to further train and enhance your personal speech profile."),
                    ),
                    SizedBox(height: 16),
                    _buildReasonTile(
                      icon: Icons.group,
                      title: TranslationService.translate( "Train Profiles for Friends and Family"),
                      description: TranslationService.translate( "Your recordings help us recognize and create profiles for your friends and family."),
                    ),
                    SizedBox(height: 16),
                    _buildReasonTile(
                      icon: Icons.trending_up,
                      title: TranslationService.translate( "Enhance Transcript Accuracy"),
                      description:
                      TranslationService.translate( "As our model improves, we can provide better transcription results for your recordings."),
                    ),
                    const SizedBox(height: 16),
                    Container(
                      padding: const EdgeInsets.all(12),
                      child: Text(
                        TranslationService.translate( "Legal Notice: The legality of recording and storing voice data may vary depending on your location and how you use this feature. It's your responsibility to ensure compliance with local laws and regulations."),
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
                          _hasPermission! ? TranslationService.translate( "Already Authorized") : TranslationService.translate( "Authorize"),
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
                          child:  Text(
                            TranslationService.translate( "Revoke Authorization"),
                            style: TextStyle(color: Colors.white),
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
      ScaffoldMessenger.of(context).showSnackBar( SnackBar(content: Text(TranslationService.translate( "Authorization successful!"))));
    } else {
      ScaffoldMessenger.of(context)
          .showSnackBar( SnackBar(content: Text(TranslationService.translate( "Failed to authorize. Please try again."))));
    }
  }

  Future<void> _revokeAuthorization() async {
    changeLoadingState();
    final success = await setRecordingPermission(false);
    changeLoadingState();
    if (success) {
      ScaffoldMessenger.of(context).showSnackBar( SnackBar(content: Text(TranslationService.translate( "Authorization revoked."))));
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
            ScaffoldMessenger.of(context).showSnackBar( SnackBar(content: Text(TranslationService.translate( "Recordings deleted."))));
            Navigator.pop(context);
          },
        TranslationService.translate( 'Permission Revoked'),
        TranslationService.translate( 'Do you want us to remove all your existing recordings too?'),
          okButtonText: TranslationService.translate( 'Yes'),
        ),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(TranslationService.translate( "Failed to revoke authorization. Please try again."))),
      );
    }
  }
}
