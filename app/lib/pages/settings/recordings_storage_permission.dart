import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
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
        title: const Text('Authorize Saving Recordings'),
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
                      _hasPermission! ? "Thanks for authorizing!" : "We need your permission",
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      _hasPermission!
                          ? "You've already given us permission to save your recordings. Here's a reminder of why we need it:"
                          : "We'd like your permission to save your voice recordings. Here's why:",
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 32),
                    _buildReasonTile(
                      icon: Icons.person,
                      title: "Improve Your Speech Profile",
                      description: "We use recordings to further train and enhance your personal speech profile.",
                    ),
                    SizedBox(height: 16),
                    _buildReasonTile(
                      icon: Icons.group,
                      title: "Train Profiles for Friends and Family",
                      description: "Your recordings help us recognize and create profiles for your friends and family.",
                    ),
                    SizedBox(height: 16),
                    _buildReasonTile(
                      icon: Icons.trending_up,
                      title: "Enhance Transcript Accuracy",
                      description:
                          "As our model improves, we can provide better transcription results for your recordings.",
                    ),
                    const SizedBox(height: 16),
                    Container(
                      padding: const EdgeInsets.all(12),
                      child: Text(
                        "Legal Notice: The legality of recording and storing voice data may vary depending on your location and how you use this feature. It's your responsibility to ensure compliance with local laws and regulations.",
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
                          _hasPermission! ? "Already Authorized" : "Authorize",
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
                          child: const Text(
                            "Revoke Authorization",
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
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Authorization successful!")));
    } else {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text("Failed to authorize. Please try again.")));
    }
  }

  Future<void> _revokeAuthorization() async {
    changeLoadingState();
    final success = await setRecordingPermission(false);
    changeLoadingState();
    if (success) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Authorization revoked.")));
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
            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Recordings deleted.")));
            Navigator.pop(context);
          },
          'Permission Revoked',
          'Do you want us to remove all your existing recordings too?',
          okButtonText: 'Yes',
        ),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Failed to revoke authorization. Please try again.")),
      );
    }
  }
}
