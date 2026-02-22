import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/speech_profile/page.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/dialog.dart';

class SpeechProfileSharingPage extends StatefulWidget {
  const SpeechProfileSharingPage({super.key});

  @override
  State<SpeechProfileSharingPage> createState() => _SpeechProfileSharingPageState();
}

class _SpeechProfileSharingPageState extends State<SpeechProfileSharingPage> {
  bool _loading = true;
  bool? _hasProfile;
  List<SharedProfileInfo> _sharedWith = [];
  List<SharedProfileInfo> _sharedWithMe = [];

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    final results = await Future.wait([
      getUsersIHaveSharedWith(),
      getProfilesSharedWithMe(),
      userHasSpeakerProfile(),
    ]);
    if (!mounted) return;
    setState(() {
      _sharedWith = results[0] as List<SharedProfileInfo>;
      _sharedWithMe = results[1] as List<SharedProfileInfo>;
      _hasProfile = results[2] as bool;
      _loading = false;
    });
  }

  Future<void> _revokeShare(SharedProfileInfo info) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (c) => getDialog(
        context,
        () => Navigator.pop(context, false),
        () => Navigator.pop(context, true),
        context.l10n.revoke,
        context.l10n.revokeShareConfirmation,
        okButtonText: context.l10n.confirm,
      ),
    );
    if (confirmed != true) return;
    await revokeSpeechProfile(info.uid);
    if (!mounted) return;
    setState(() => _loading = true);
    await _loadData();
  }

  Future<void> _removeSharedWithMe(SharedProfileInfo info) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (c) => getDialog(
        context,
        () => Navigator.pop(context, false),
        () => Navigator.pop(context, true),
        context.l10n.removeSharedProfile,
        context.l10n.removeSharedProfileConfirmation,
        okButtonText: context.l10n.confirm,
      ),
    );
    if (confirmed != true) return;
    await removeSharedProfile(info.uid);
    if (!mounted) return;
    setState(() => _loading = true);
    await _loadData();
  }

  void _openShareDialog() async {
    final hasProfile = _hasProfile ?? await userHasSpeakerProfile();
    if (!mounted) return;
    if (!hasProfile) {
      final goRecord = await showDialog<bool>(
        context: context,
        builder: (c) => getDialog(
          context,
          () => Navigator.pop(context, false),
          () => Navigator.pop(context, true),
          context.l10n.shareSpeechProfile,
          context.l10n.noSpeechProfileRecorded,
          okButtonText: context.l10n.recordNow,
        ),
      );
      if (goRecord == true && mounted) {
        routeToPage(context, const SpeechProfilePage());
      }
      return;
    }

    final controller = TextEditingController();
    if (!mounted) return;
    showDialog(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1C1C1E),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Text(context.l10n.shareSpeechProfile, style: const TextStyle(color: Colors.white)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(context.l10n.enterUserIdToShare, style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 14)),
              const SizedBox(height: 12),
              TextField(
                controller: controller,
                style: const TextStyle(color: Colors.white),
                decoration: InputDecoration(
                  hintText: context.l10n.userId,
                  hintStyle: const TextStyle(color: Color(0xFF636366)),
                  enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: Color(0xFF3C3C43))),
                  focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: Colors.white)),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: Text(context.l10n.cancel, style: const TextStyle(color: Colors.white)),
            ),
            TextButton(
              onPressed: () async {
                final targetUid = controller.text.trim();
                if (targetUid.isEmpty) return;
                if (targetUid == SharedPreferencesUtil().uid) {
                  Navigator.pop(ctx);
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text(context.l10n.cannotShareWithSelf)),
                  );
                  return;
                }
                final result = await shareSpeechProfile(targetUid);
                if (!context.mounted) return;
                Navigator.pop(ctx);
                if (result['status'] == 'ok') {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text(context.l10n.profileSharedSuccess)),
                  );
                  setState(() => _loading = true);
                  _loadData();
                } else {
                  final error = result['error'] ?? '';
                  String message;
                  if (error.contains('not found')) {
                    message = context.l10n.userNotFound;
                  } else if (error.contains('yourself')) {
                    message = context.l10n.cannotShareWithSelf;
                  } else if (error.contains('No speech profile')) {
                    message = context.l10n.noSpeechProfileRecorded;
                  } else {
                    message = context.l10n.profileSharedFail;
                  }
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
                }
              },
              child: Text(context.l10n.share, style: const TextStyle(color: Colors.white)),
            ),
          ],
        );
      },
    );
  }

  Widget _buildSectionHeader(String title, IconData icon) {
    return Padding(
      padding: const EdgeInsets.only(left: 16, bottom: 8),
      child: Row(
        children: [
          Icon(icon, color: const Color(0xFF8E8E93), size: 16),
          const SizedBox(width: 6),
          Text(
            title.toUpperCase(),
            style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState(String message) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 32, horizontal: 16),
        child: Text(
          message,
          style: const TextStyle(color: Color(0xFF636366), fontSize: 15),
          textAlign: TextAlign.center,
        ),
      ),
    );
  }

  Widget _buildProfileTile(SharedProfileInfo info, {required Widget trailing}) {
    final truncatedUid = info.uid.length > 10
        ? '${info.uid.substring(0, 5)}...${info.uid.substring(info.uid.length - 5)}'
        : info.uid;
    return ListTile(
      title: Text(
        info.displayName,
        style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
      ),
      subtitle: info.name.isNotEmpty
          ? GestureDetector(
              onTap: () {
                Clipboard.setData(ClipboardData(text: info.uid));
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(context.l10n.userIdCopied)),
                );
              },
              child: Text(truncatedUid, style: const TextStyle(color: Color(0xFF636366), fontSize: 13)),
            )
          : null,
      trailing: trailing,
    );
  }

  Widget _buildActionPill(String label, Color color, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: color.withOpacity(0.15),
          borderRadius: BorderRadius.circular(100),
        ),
        child: Text(
          label,
          style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.w500),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: Text(context.l10n.sharedProfiles),
        backgroundColor: Theme.of(context).colorScheme.primary,
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            onPressed: _openShareDialog,
          ),
        ],
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(
                valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
              ),
            )
          : SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Shared With section
                  _buildSectionHeader(context.l10n.sharedWithSection, Icons.arrow_upward),
                  if (_sharedWith.isEmpty)
                    _buildEmptyState('${context.l10n.noSharedProfiles} :/')
                  else
                    Container(
                      decoration: BoxDecoration(
                        color: const Color(0xFF1C1C1E),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Column(
                        children: [
                          for (int i = 0; i < _sharedWith.length; i++) ...[
                            if (i > 0) const Divider(height: 1, color: Color(0xFF3C3C43), indent: 16),
                            _buildProfileTile(
                              _sharedWith[i],
                              trailing: _buildActionPill(
                                context.l10n.revoke,
                                const Color(0xFFEF4444),
                                () => _revokeShare(_sharedWith[i]),
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),

                  const SizedBox(height: 32),

                  // Shared With You section
                  _buildSectionHeader(context.l10n.sharedWithYouSection, Icons.arrow_downward),
                  if (_sharedWithMe.isEmpty)
                    _buildEmptyState('${context.l10n.noProfilesSharedWithYou} :/')
                  else
                    Container(
                      decoration: BoxDecoration(
                        color: const Color(0xFF1C1C1E),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Column(
                        children: [
                          for (int i = 0; i < _sharedWithMe.length; i++) ...[
                            if (i > 0) const Divider(height: 1, color: Color(0xFF3C3C43), indent: 16),
                            _buildProfileTile(
                              _sharedWithMe[i],
                              trailing: _buildActionPill(
                                context.l10n.removeSharedProfile,
                                const Color(0xFFEF4444),
                                () => _removeSharedWithMe(_sharedWithMe[i]),
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                ],
              ),
            ),
    );
  }
}
