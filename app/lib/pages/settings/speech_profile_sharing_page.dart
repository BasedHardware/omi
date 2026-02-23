import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/share_speech_profile_dialog.dart';

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

  void _openShareDialog() {
    showShareSpeechProfileDialog(
      context,
      cachedHasProfile: _hasProfile,
      onShared: () {
        setState(() => _loading = true);
        _loadData();
      },
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, bottom: 8),
      child: Text(
        title.toUpperCase(),
        style: TextStyle(
          color: Colors.grey.shade500,
          fontSize: 13,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.5,
        ),
      ),
    );
  }

  Widget _buildEmptyState(String message, IconData icon) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 32, horizontal: 16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          Icon(icon, color: Colors.grey.shade600, size: 32),
          const SizedBox(height: 12),
          Text(
            message,
            style: TextStyle(color: Colors.grey.shade400, fontSize: 15),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildProfileTile(SharedProfileInfo info, {required Widget trailing}) {
    final hasName = info.name.isNotEmpty;
    final truncatedUid =
        info.uid.length > 12 ? '${info.uid.substring(0, 6)}...${info.uid.substring(info.uid.length - 4)}' : info.uid;
    return ListTile(
      title: Text(
        hasName ? info.name : truncatedUid,
        style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500),
      ),
      subtitle: hasName
          ? GestureDetector(
              onTap: () {
                Clipboard.setData(ClipboardData(text: info.uid));
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(context.l10n.userIdCopied)),
                );
              },
              child: Text(truncatedUid, style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
            )
          : null,
      onLongPress: () {
        Clipboard.setData(ClipboardData(text: info.uid));
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.userIdCopied)),
        );
      },
      trailing: trailing,
    );
  }

  Widget _buildActionPill(String label, Color color, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text(
          label,
          style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w500),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D0D0D),
        elevation: 0,
        title: Text(context.l10n.sharedProfiles, style: const TextStyle(color: Colors.white, fontSize: 18)),
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
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildSectionHeader(context.l10n.sharedWithSection),
                  if (_sharedWith.isEmpty)
                    _buildEmptyState(context.l10n.noSharedProfiles, Icons.person_add_alt_1_outlined)
                  else
                    ClipRRect(
                      borderRadius: BorderRadius.circular(12),
                      child: Container(
                        decoration: const BoxDecoration(
                          color: Color(0xFF1C1C1E),
                        ),
                        child: Column(
                          children: [
                            for (int i = 0; i < _sharedWith.length; i++) ...[
                              if (i > 0) Divider(height: 1, color: Colors.grey.shade800, indent: 16),
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
                    ),

                  const SizedBox(height: 24),

                  _buildSectionHeader(context.l10n.sharedWithYouSection),
                  if (_sharedWithMe.isEmpty)
                    _buildEmptyState(context.l10n.noProfilesSharedWithYou, Icons.people_outline)
                  else
                    ClipRRect(
                      borderRadius: BorderRadius.circular(12),
                      child: Container(
                        decoration: const BoxDecoration(
                          color: Color(0xFF1C1C1E),
                        ),
                        child: Column(
                          children: [
                            for (int i = 0; i < _sharedWithMe.length; i++) ...[
                              if (i > 0) Divider(height: 1, color: Colors.grey.shade800, indent: 16),
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
                    ),

                  const SizedBox(height: 32),
                ],
              ),
            ),
    );
  }
}
