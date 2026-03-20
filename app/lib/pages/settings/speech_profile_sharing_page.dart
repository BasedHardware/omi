import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/dialog.dart';

class SpeechProfileSharingPage extends StatefulWidget {
  const SpeechProfileSharingPage({super.key});

  @override
  State<SpeechProfileSharingPage> createState() =>
      _SpeechProfileSharingPageState();
}

class _SpeechProfileSharingPageState extends State<SpeechProfileSharingPage> {
  final _emailController = TextEditingController();
  final _nameController = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  List<SharedProfile> _sharedProfiles = [];
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _fetchShared();
  }

  @override
  void dispose() {
    _emailController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _fetchShared() async {
    setState(() => _loading = true);
    try {
      final profiles = await getSharedProfiles();
      setState(() {
        _sharedProfiles = profiles;
        _error = null;
      });
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _shareProfile() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await shareSpeechProfile(
        recipientEmail: _emailController.text.trim(),
        displayName: _nameController.text.trim(),
      );
      _emailController.clear();
      _nameController.clear();
      await _fetchShared();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.speechProfileShared)),
        );
      }
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _revokeProfile(SharedProfile profile) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(context.l10n.revokeShare),
        content: Text(
            context.l10n.revokeShareConfirmation(profile.displayName)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(context.l10n.cancel),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: Text(context.l10n.revoke),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    setState(() => _loading = true);
    try {
      await revokeSpeechProfile(recipientUserId: profile.sharerUid);
      await _fetchShared();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.shareRevoked)),
        );
      }
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(context.l10n.shareSpeechProfile)),
      body: _loading && _sharedProfiles.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _fetchShared,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  _ShareForm(
                    formKey: _formKey,
                    emailController: _emailController,
                    nameController: _nameController,
                    loading: _loading,
                    onSubmit: _shareProfile,
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: const TextStyle(color: Colors.red)),
                  ],
                  const SizedBox(height: 24),
                  Text(
                    context.l10n.profilesSharedWithYou,
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                  ),
                  const SizedBox(height: 8),
                  if (_sharedProfiles.isEmpty)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      child: Text(
                        context.l10n.noSharedProfiles,
                        style: const TextStyle(color: Colors.grey),
                      ),
                    )
                  else
                    ..._sharedProfiles.map(
                      (p) => _SharedProfileTile(
                        profile: p,
                        onRevoke: () => _revokeProfile(p),
                      ),
                    ),
                ],
              ),
            ),
    );
  }
}

// ── Sub-widgets ───────────────────────────────────────────────────────────

class _ShareForm extends StatelessWidget {
  const _ShareForm({
    required this.formKey,
    required this.emailController,
    required this.nameController,
    required this.loading,
    required this.onSubmit,
  });

  final GlobalKey<FormState> formKey;
  final TextEditingController emailController;
  final TextEditingController nameController;
  final bool loading;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    return Form(
      key: formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            context.l10n.shareYourVoiceProfile,
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
          const SizedBox(height: 8),
          TextFormField(
            controller: emailController,
            decoration: InputDecoration(
              labelText: context.l10n.recipientEmail,
              border: const OutlineInputBorder(),
            ),
            keyboardType: TextInputType.emailAddress,
            validator: (v) =>
                (v == null || !v.contains('@')) ? context.l10n.enterValidEmail : null,
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: nameController,
            decoration: InputDecoration(
              labelText: context.l10n.theirNameForSpeakerLabels,
              border: const OutlineInputBorder(),
            ),
            validator: (v) =>
                (v == null || v.trim().isEmpty) ? context.l10n.enterDisplayName : null,
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: loading ? null : onSubmit,
            child: loading
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Text(context.l10n.shareMyProfile),
          ),
        ],
      ),
    );
  }
}

class _SharedProfileTile extends StatelessWidget {
  const _SharedProfileTile({required this.profile, required this.onRevoke});
  final SharedProfile profile;
  final VoidCallback onRevoke;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: ListTile(
        leading: const CircleAvatar(child: Icon(Icons.mic)),
        title: Text(profile.displayName),
        subtitle: Text(context.l10n.sharedAgo(_relativeDate(profile.createdAt))),
        trailing: IconButton(
          icon: const Icon(Icons.remove_circle_outline, color: Colors.red),
          tooltip: context.l10n.revokeShare,
          onPressed: onRevoke,
        ),
      ),
    );
  }

  String _relativeDate(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inDays > 0) return '${diff.inDays}d';
    if (diff.inHours > 0) return '${diff.inHours}h';
    return context.l10n.justNow;
  }
}
