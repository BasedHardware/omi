import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/dialog.dart';

class SpeechProfileSharingPage extends StatefulWidget {
  const SpeechProfileSharingPage({super.key});

  @override
  State<SpeechProfileSharingPage> createState() => _SpeechProfileSharingPageState();
}

class _SpeechProfileSharingPageState extends State<SpeechProfileSharingPage> {
  bool _loading = true;
  List<String> _sharedWith = [];
  List<String> _sharedWithMe = [];

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    final results = await Future.wait([
      getUsersIHaveSharedWith(),
      getProfilesSharedWithMe(),
    ]);
    if (!mounted) return;
    setState(() {
      _sharedWith = results[0];
      _sharedWithMe = results[1];
      _loading = false;
    });
  }

  Future<void> _revokeShare(String uid) async {
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
    await revokeSpeechProfile(uid);
    if (!mounted) return;
    setState(() {
      _loading = true;
    });
    await _loadData();
  }

  void _openShareDialog() {
    final controller = TextEditingController();
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
                final ok = await shareSpeechProfile(targetUid);
                if (!context.mounted) return;
                Navigator.pop(ctx);
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(ok ? context.l10n.profileSharedSuccess : context.l10n.profileSharedFail)),
                );
                if (ok) {
                  setState(() => _loading = true);
                  _loadData();
                }
              },
              child: Text(context.l10n.share, style: const TextStyle(color: Colors.white)),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: Text(context.l10n.speechProfileSharingStatus),
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
                  Padding(
                    padding: const EdgeInsets.only(left: 16, bottom: 8),
                    child: Text(
                      context.l10n.sharedWithSection.toUpperCase(),
                      style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w600),
                    ),
                  ),
                  Container(
                    decoration: BoxDecoration(
                      color: const Color(0xFF1C1C1E),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: _sharedWith.isEmpty
                        ? Padding(
                            padding: const EdgeInsets.all(16),
                            child: Text(
                              context.l10n.noSharedProfiles,
                              style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 15),
                            ),
                          )
                        : Column(
                            children: [
                              for (int i = 0; i < _sharedWith.length; i++) ...[
                                if (i > 0) const Divider(height: 1, color: Color(0xFF3C3C43), indent: 16),
                                ListTile(
                                  title: Text(
                                    _sharedWith[i],
                                    style: const TextStyle(color: Colors.white, fontSize: 15),
                                  ),
                                  trailing: GestureDetector(
                                    onTap: () => _revokeShare(_sharedWith[i]),
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                      decoration: BoxDecoration(
                                        color: const Color(0xFFEF4444).withOpacity(0.15),
                                        borderRadius: BorderRadius.circular(100),
                                      ),
                                      child: Text(
                                        context.l10n.revoke,
                                        style: const TextStyle(
                                          color: Color(0xFFEF4444),
                                          fontSize: 13,
                                          fontWeight: FontWeight.w500,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ],
                          ),
                  ),

                  const SizedBox(height: 32),

                  // Shared With You section
                  Padding(
                    padding: const EdgeInsets.only(left: 16, bottom: 8),
                    child: Text(
                      context.l10n.sharedWithYouSection.toUpperCase(),
                      style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w600),
                    ),
                  ),
                  Container(
                    decoration: BoxDecoration(
                      color: const Color(0xFF1C1C1E),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: _sharedWithMe.isEmpty
                        ? Padding(
                            padding: const EdgeInsets.all(16),
                            child: Text(
                              context.l10n.noProfilesSharedWithYou,
                              style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 15),
                            ),
                          )
                        : Column(
                            children: [
                              for (int i = 0; i < _sharedWithMe.length; i++) ...[
                                if (i > 0) const Divider(height: 1, color: Color(0xFF3C3C43), indent: 16),
                                ListTile(
                                  title: Text(
                                    _sharedWithMe[i],
                                    style: const TextStyle(color: Colors.white, fontSize: 15),
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
