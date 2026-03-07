// FILE: app/lib/pages/conversations/private_cloud_sync_page.dart
// FULL REPLACEMENT of the existing file

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:just_audio/just_audio.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

class PrivateCloudSyncPage extends StatefulWidget {
  const PrivateCloudSyncPage({super.key});

  @override
  State<PrivateCloudSyncPage> createState() => _PrivateCloudSyncPageState();
}

class _PrivateCloudSyncPageState extends State<PrivateCloudSyncPage> {
  bool _isSaving = false;
  bool _isLoadingAudio = false;
  bool _isDeletingAll = false;
  List<Map<String, dynamic>> _audioConversations = [];
  final AudioPlayer _audioPlayer = AudioPlayer();
  String? _currentlyPlayingId;

  @override
  void initState() {
    super.initState();
    final isEnabled = context.read<UserProvider>().privateCloudSyncEnabled;
    if (isEnabled) {
      _loadAudioFiles();
    }
  }

  @override
  void dispose() {
    _audioPlayer.dispose();
    super.dispose();
  }

  Future<void> _loadAudioFiles() async {
    setState(() => _isLoadingAudio = true);
    try {
      final conversations = await listUserAudioFiles();
      if (mounted) {
        setState(() {
          _audioConversations = conversations;
          _isLoadingAudio = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isLoadingAudio = false);
      }
    }
  }

  Future<void> _togglePrivateCloudSync(bool value) async {
    if (value) {
      final confirmed = await _showEnableDialog();
      if (confirmed != true) return;
    }

    setState(() => _isSaving = true);
    try {
      await context.read<UserProvider>().setPrivateCloudSync(value);
      setState(() => _isSaving = false);
      if (value) {
        _loadAudioFiles();
      } else {
        setState(() => _audioConversations = []);
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              value ? context.l10n.cloudStorageEnabled : context.l10n.cloudStorageDisabled,
            ),
            backgroundColor: Colors.green,
          ),
        );
      }
    } catch (e) {
      setState(() => _isSaving = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(context.l10n.failedToUpdateSettings(e.toString())),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _playAudio(String conversationId, String audioFileId) async {
    final playId = '$conversationId/$audioFileId';

    if (_currentlyPlayingId == playId) {
      await _audioPlayer.stop();
      setState(() => _currentlyPlayingId = null);
      return;
    }

    try {
      // Get signed URLs for the conversation
      final audioInfos = await getConversationAudioSignedUrls(conversationId);
      final targetInfo = audioInfos.firstWhere(
        (info) => info.id == audioFileId,
        orElse: () => audioInfos.first,
      );

      if (targetInfo.isCached && targetInfo.signedUrl != null) {
        await _audioPlayer.setUrl(targetInfo.signedUrl!);
      } else {
        // Fall back to stream URL with auth headers
        final headers = await getAudioHeaders();
        final streamUrl = getAudioStreamUrl(
          conversationId: conversationId,
          audioFileId: audioFileId,
        );
        await _audioPlayer.setUrl(streamUrl, headers: headers);
      }

      setState(() => _currentlyPlayingId = playId);
      _audioPlayer.play();

      _audioPlayer.playerStateStream.listen((state) {
        if (state.processingState == ProcessingState.completed) {
          if (mounted) {
            setState(() => _currentlyPlayingId = null);
          }
        }
      });
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to play audio: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _shareAudio(String conversationId, String audioFileId) async {
    try {
      final audioInfos = await getConversationAudioSignedUrls(conversationId);
      final targetInfo = audioInfos.firstWhere(
        (info) => info.id == audioFileId,
        orElse: () => audioInfos.first,
      );

      if (targetInfo.isCached && targetInfo.signedUrl != null) {
        await Share.share(targetInfo.signedUrl!, subject: 'Omi Audio Recording');
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Audio is still being processed. Please try again later.'),
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to share: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  Future<void> _deleteAllAudio() async {
    final confirmed = await _showDeleteAllDialog();
    if (confirmed != true) return;

    setState(() => _isDeletingAll = true);
    try {
      final success = await deleteAllUserAudio();
      if (success && mounted) {
        setState(() {
          _audioConversations = [];
          _isDeletingAll = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('All audio files deleted successfully.'),
            backgroundColor: Colors.green,
          ),
        );
      } else {
        setState(() => _isDeletingAll = false);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Failed to delete audio files.'),
              backgroundColor: Colors.red,
            ),
          );
        }
      }
    } catch (e) {
      setState(() => _isDeletingAll = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  Future<bool?> _showEnableDialog() {
    return showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1C1C1E),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: Text(context.l10n.enableCloudStorage,
            style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
        content: Text(
          context.l10n.cloudStorageDialogMessage,
          style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(context.l10n.cancel, style: TextStyle(color: Colors.grey.shade500)),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(context.l10n.enable,
                style: const TextStyle(color: Colors.deepPurpleAccent, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }

  Future<bool?> _showDeleteAllDialog() {
    return showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1C1C1E),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('Delete All Audio',
            style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
        content: Text(
          'Deleting all audio will remove your recordings from Private Cloud Sync.\n\n'
          'If you have opted into the Omi Training Program, your audio data will '
          'no longer be available for contribution, which may affect your eligibility '
          'for free unlimited access.',
          style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(context.l10n.cancel, style: TextStyle(color: Colors.grey.shade500)),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete All',
                style: TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }

  String _formatDuration(num seconds) {
    final duration = Duration(seconds: seconds.toInt());
    final mins = duration.inMinutes;
    final secs = duration.inSeconds % 60;
    return '${mins}m ${secs}s';
  }

  Widget _buildFaIcon(IconData icon, {double size = 18, Color color = const Color(0xFF8E8E93)}) {
    return Padding(
      padding: const EdgeInsets.only(left: 2, top: 1),
      child: FaIcon(icon, size: size, color: color),
    );
  }

  Widget _buildAudioList() {
    if (_isLoadingAudio) {
      return const Padding(
        padding: EdgeInsets.all(20),
        child: Center(child: CircularProgressIndicator(color: Colors.deepPurpleAccent)),
      );
    }

    if (_audioConversations.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Center(
          child: Text(
            'No audio recordings yet.',
            style: TextStyle(color: Colors.grey.shade500, fontSize: 14),
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(bottom: 12),
          child: Text(
            'Audio Recordings',
            style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
          ),
        ),
        ..._audioConversations.map((conv) => _buildConversationCard(conv)),
        const SizedBox(height: 16),
        _buildDeleteAllButton(),
      ],
    );
  }

  Widget _buildConversationCard(Map<String, dynamic> conv) {
    final title = conv['title'] ?? 'Untitled';
    final audioFiles = (conv['audio_files'] as List<dynamic>?) ?? [];
    final totalDuration = conv['total_duration'] ?? 0;
    final conversationId = conv['conversation_id'] ?? '';

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Text(
                _formatDuration(totalDuration),
                style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ...audioFiles.map((af) {
            final audioFileId = af['id'] ?? '';
            final duration = af['duration'] ?? 0;
            final playId = '$conversationId/$audioFileId';
            final isPlaying = _currentlyPlayingId == playId;

            return Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Row(
                children: [
                  GestureDetector(
                    onTap: () => _playAudio(conversationId, audioFileId),
                    child: Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: isPlaying ? Colors.deepPurpleAccent : const Color(0xFF2A2A2E),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Icon(
                        isPlaying ? Icons.stop : Icons.play_arrow,
                        color: Colors.white,
                        size: 18,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      _formatDuration(duration),
                      style: TextStyle(color: Colors.grey.shade400, fontSize: 13),
                    ),
                  ),
                  GestureDetector(
                    onTap: () => _shareAudio(conversationId, audioFileId),
                    child: Padding(
                      padding: const EdgeInsets.all(4),
                      child: _buildFaIcon(FontAwesomeIcons.shareFromSquare, size: 14, color: Colors.grey.shade400),
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildDeleteAllButton() {
    if (_audioConversations.isEmpty) return const SizedBox.shrink();

    return SizedBox(
      width: double.infinity,
      child: TextButton(
        onPressed: _isDeletingAll ? null : _deleteAllAudio,
        style: TextButton.styleFrom(
          backgroundColor: Colors.red.withOpacity(0.1),
          padding: const EdgeInsets.symmetric(vertical: 14),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
        child: _isDeletingAll
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(color: Colors.redAccent, strokeWidth: 2),
              )
            : const Text(
                'Delete All Audio',
                style: TextStyle(color: Colors.redAccent, fontSize: 15, fontWeight: FontWeight.w600),
              ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<UserProvider>(
      builder: (context, userProvider, child) {
        final isEnabled = userProvider.privateCloudSyncEnabled;
        final isLoading = userProvider.isLoading;

        return Scaffold(
          backgroundColor: const Color(0xFF0D0D0D),
          appBar: AppBar(
            backgroundColor: const Color(0xFF0D0D0D),
            elevation: 0,
            leading: IconButton(
              icon: _buildFaIcon(FontAwesomeIcons.chevronLeft, size: 18, color: Colors.white),
              onPressed: () => Navigator.of(context).pop(),
            ),
            title: Text(context.l10n.storeAudioOnCloud,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
            centerTitle: true,
          ),
          body: isLoading
              ? const Center(child: CircularProgressIndicator(color: Colors.white))
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Toggle card (existing)
                      Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1C1C1E),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                _buildFaIcon(FontAwesomeIcons.cloud, size: 20, color: Colors.deepPurpleAccent),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Text(
                                    context.l10n.storeAudioOnCloud,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 18,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                  decoration: BoxDecoration(
                                    color: isEnabled ? Colors.green.withOpacity(0.2) : const Color(0xFF2A2A2E),
                                    borderRadius: BorderRadius.circular(100),
                                  ),
                                  child: Text(
                                    isEnabled ? context.l10n.on : context.l10n.off,
                                    style: TextStyle(
                                      color: isEnabled ? Colors.green : Colors.white,
                                      fontSize: 13,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 20),
                            Text(
                              context.l10n.storeAudioCloudDescription,
                              style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.5),
                            ),
                            const SizedBox(height: 24),
                            const Divider(height: 1, color: Color(0xFF3C3C43)),
                            const SizedBox(height: 20),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text(
                                  context.l10n.enableCloudStorage,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                Transform.scale(
                                  scale: 0.85,
                                  child: CupertinoSwitch(
                                    value: isEnabled,
                                    onChanged: _isSaving ? null : _togglePrivateCloudSync,
                                    activeTrackColor: Colors.deepPurpleAccent,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      // Audio list (new)
                      if (isEnabled) ...[
                        const SizedBox(height: 24),
                        _buildAudioList(),
                      ],
                    ],
                  ),
                ),
        );
      },
    );
  }
}
