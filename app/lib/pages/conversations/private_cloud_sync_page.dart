import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:just_audio/just_audio.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

class PrivateCloudSyncPage extends StatefulWidget {
  const PrivateCloudSyncPage({super.key});

  @override
  State<PrivateCloudSyncPage> createState() => _PrivateCloudSyncPageState();
}

class _PrivateCloudSyncPageState extends State<PrivateCloudSyncPage> {
  bool _isSaving = false;
  bool _isLoadingAudio = false;
  bool _isDeleting = false;
  List<CloudAudioConversation> _conversations = [];

  // Audio playback state
  final AudioPlayer _audioPlayer = AudioPlayer();
  String? _currentPlayingConversationId;
  bool _isAudioLoading = false;

  StreamSubscription<PlayerState>? _playerStateSubscription;

  @override
  void initState() {
    super.initState();
    _playerStateSubscription = _audioPlayer.playerStateStream.listen((state) {
      if (mounted) {
        // Clear playing state when playback completes
        if (state.processingState == ProcessingState.completed) {
          setState(() {
            _currentPlayingConversationId = null;
          });
          _audioPlayer.stop();
        } else {
          setState(() {});
        }
      }
    });
    _loadCloudAudioConversations();
  }

  @override
  void dispose() {
    _playerStateSubscription?.cancel();
    _audioPlayer.dispose();
    super.dispose();
  }

  Future<void> _loadCloudAudioConversations() async {
    setState(() => _isLoadingAudio = true);
    try {
      final conversations = await getCloudAudioConversations();
      if (mounted) {
        setState(() {
          _conversations = conversations;
          _isLoadingAudio = false;
        });
      }
    } catch (e) {
      Logger.debug('Error loading cloud audio conversations: $e');
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
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(value ? context.l10n.cloudStorageEnabled : context.l10n.cloudStorageDisabled),
            backgroundColor: Colors.green,
          ),
        );
      }
    } catch (e) {
      Logger.debug('Error toggling cloud storage: $e');
      setState(() => _isSaving = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.failedToUpdateSettings(e.toString())), backgroundColor: Colors.red),
        );
      }
    }
  }

  Future<void> _playConversationAudio(CloudAudioConversation conversation) async {
    // If already playing this conversation, toggle pause/play
    if (_currentPlayingConversationId == conversation.id) {
      if (_audioPlayer.playing) {
        await _audioPlayer.pause();
      } else {
        await _audioPlayer.play();
      }
      return;
    }

    // Stop current playback
    await _audioPlayer.stop();

    setState(() {
      _currentPlayingConversationId = conversation.id;
      _isAudioLoading = true;
    });

    try {
      // Get signed URLs for the conversation's audio files
      final audioFileInfos = await getConversationAudioSignedUrls(conversation.id);
      if (!mounted) return;

      final cachedFiles = audioFileInfos.where((af) => af.isCached).toList();
      if (cachedFiles.isEmpty) {
        // Trigger precache and inform user
        await precacheConversationAudio(conversation.id);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(context.l10n.preparingAudioTryAgain),
              backgroundColor: Colors.orange,
            ),
          );
          setState(() {
            _isAudioLoading = false;
            _currentPlayingConversationId = null;
          });
        }
        return;
      }

      // Build playlist from cached signed URLs
      final headers = await getAudioHeaders();
      final audioFileIds = cachedFiles.map((af) => af.id).toList();
      final urls = getConversationAudioUrls(
        conversationId: conversation.id,
        audioFileIds: audioFileIds,
        format: 'wav',
      );

      final playlist = ConcatenatingAudioSource(
        useLazyPreparation: true,
        children: urls.map((url) => AudioSource.uri(Uri.parse(url), headers: headers)).toList(),
      );

      await _audioPlayer.setAudioSource(playlist, preload: true);

      setState(() => _isAudioLoading = false);

      await _audioPlayer.play();
    } catch (e) {
      Logger.debug('Error playing conversation audio: $e');
      if (mounted) {
        setState(() {
          _isAudioLoading = false;
          _currentPlayingConversationId = null;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(context.l10n.failedToPlayAudio(e.toString())),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _shareConversationAudio(CloudAudioConversation conversation) async {
    try {
      final audioFileInfos = await getConversationAudioSignedUrls(conversation.id);
      final cachedFiles = audioFileInfos.where((af) => af.isCached).toList();

      if (cachedFiles.isEmpty) {
        await precacheConversationAudio(conversation.id);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(context.l10n.preparingAudioTryAgain),
              backgroundColor: Colors.orange,
            ),
          );
        }
        return;
      }

      // Share the signed URL(s) for the audio files
      final urls = cachedFiles.map((af) => af.signedUrl!).toList();
      await Share.share(
        context.l10n.audioShareText(conversation.title, urls.join('\n')),
      );
    } catch (e) {
      Logger.debug('Error sharing audio: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.failedToShareAudio(e.toString())), backgroundColor: Colors.red),
        );
      }
    }
  }

  Future<void> _deleteAllAudio() async {
    final confirmed = await _showDeleteAllDialog();
    if (confirmed != true) return;

    setState(() => _isDeleting = true);

    // Stop any playback
    await _audioPlayer.stop();
    _currentPlayingConversationId = null;

    try {
      final success = await deleteAllCloudAudio();
      if (mounted) {
        setState(() => _isDeleting = false);
        if (success) {
          setState(() => _conversations = []);
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(context.l10n.audioDeletedSuccessfully),
              backgroundColor: Colors.green,
            ),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(context.l10n.failedToDeleteAudio),
              backgroundColor: Colors.red,
            ),
          );
        }
      }
    } catch (e) {
      Logger.debug('Error deleting all audio: $e');
      if (mounted) {
        setState(() => _isDeleting = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(context.l10n.failedToDeleteAudio),
            backgroundColor: Colors.red,
          ),
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
        title: Text(
          context.l10n.enableCloudStorage,
          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
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
            child: Text(
              context.l10n.enable,
              style: const TextStyle(color: Colors.deepPurpleAccent, fontWeight: FontWeight.w600),
            ),
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
        title: Row(
          children: [
            const Icon(Icons.warning_amber_rounded, color: Colors.red, size: 24),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                context.l10n.deleteAllAudioTitle,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
        content: Text(
          context.l10n.deleteAllAudioMessage,
          style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(context.l10n.cancel, style: TextStyle(color: Colors.grey.shade500)),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(
              context.l10n.deleteAll,
              style: const TextStyle(color: Colors.red, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFaIcon(IconData icon, {double size = 18, Color color = const Color(0xFF8E8E93)}) {
    return Padding(
      padding: const EdgeInsets.only(left: 2, top: 1),
      child: FaIcon(icon, size: size, color: color),
    );
  }

  String _formatDuration(double seconds) {
    final duration = Duration(milliseconds: (seconds * 1000).toInt());
    final minutes = duration.inMinutes;
    final secs = duration.inSeconds.remainder(60);
    if (minutes > 0) {
      return '${minutes}m ${secs}s';
    }
    return '${secs}s';
  }

  String _formatDate(BuildContext context, DateTime? date) {
    if (date == null) return '';
    final now = DateTime.now();
    final diff = now.difference(date);
    if (diff.inDays == 0) return context.l10n.today;
    if (diff.inDays == 1) return context.l10n.yesterday;
    if (diff.inDays < 7) return context.l10n.daysAgo(diff.inDays);
    return '${date.month}/${date.day}/${date.year}';
  }

  Widget _buildConversationTile(CloudAudioConversation conversation) {
    final isPlaying = _currentPlayingConversationId == conversation.id;
    final isCurrentlyPlaying = isPlaying && _audioPlayer.playing;
    final isLoading = isPlaying && _isAudioLoading;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: isPlaying ? const Color(0xFF2A2A2E).withOpacity(0.8) : const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(14),
        border: isPlaying ? Border.all(color: Colors.deepPurpleAccent.withOpacity(0.4), width: 1) : null,
      ),
      child: Row(
        children: [
          // Play button
          GestureDetector(
            onTap: isLoading ? null : () => _playConversationAudio(conversation),
            child: Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: isPlaying ? Colors.deepPurpleAccent : const Color(0xFF2A2A2E),
                shape: BoxShape.circle,
              ),
              child: Center(
                child: isLoading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                      )
                    : Icon(
                        isCurrentlyPlaying ? Icons.pause : Icons.play_arrow,
                        color: Colors.white,
                        size: 22,
                      ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          // Conversation info
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  conversation.title,
                  style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w500),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Text(
                      context.l10n.nAudioFiles(conversation.audioFileCount),
                      style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                    ),
                    const SizedBox(width: 8),
                    Text('•', style: TextStyle(color: Colors.grey.shade600, fontSize: 12)),
                    const SizedBox(width: 8),
                    Text(
                      _formatDuration(conversation.totalDuration),
                      style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                    ),
                    if (conversation.createdAt != null) ...[
                      const SizedBox(width: 8),
                      Text('•', style: TextStyle(color: Colors.grey.shade600, fontSize: 12)),
                      const SizedBox(width: 8),
                      Text(
                        _formatDate(context, conversation.createdAt),
                        style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
          // Share button
          IconButton(
            onPressed: () => _shareConversationAudio(conversation),
            icon: const Icon(Icons.share_outlined, color: Color(0xFF8E8E93), size: 20),
            splashRadius: 20,
          ),
        ],
      ),
    );
  }

  Widget _buildAudioFilesSection(bool isEnabled) {
    if (!isEnabled) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 24),
        // Section header with delete all button
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
                  _buildFaIcon(FontAwesomeIcons.fileAudio, size: 18, color: Colors.deepPurpleAccent),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      context.l10n.cloudAudioFiles,
                      style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
                    ),
                  ),
                  if (_conversations.isNotEmpty && !_isDeleting)
                    TextButton.icon(
                      onPressed: _deleteAllAudio,
                      icon: const Icon(Icons.delete_outline, size: 16, color: Colors.red),
                      label: Text(
                        context.l10n.deleteAllAudio,
                        style: const TextStyle(color: Colors.red, fontSize: 13),
                      ),
                      style: TextButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        minimumSize: Size.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 16),
              if (_isLoadingAudio || _isDeleting)
                Center(
                  child: Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      children: [
                        const CircularProgressIndicator(color: Colors.deepPurpleAccent),
                        if (_isDeleting) ...[
                          const SizedBox(height: 12),
                          Text(
                            context.l10n.deletingAudio,
                            style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                          ),
                        ],
                      ],
                    ),
                  ),
                )
              else if (_conversations.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 24),
                  child: Center(
                    child: Column(
                      children: [
                        Icon(Icons.cloud_off_outlined, color: Colors.grey.shade600, size: 40),
                        const SizedBox(height: 12),
                        Text(
                          context.l10n.noCloudAudioFiles,
                          style: TextStyle(color: Colors.grey.shade400, fontSize: 15, fontWeight: FontWeight.w500),
                        ),
                        const SizedBox(height: 6),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 24),
                          child: Text(
                            context.l10n.noCloudAudioDescription,
                            style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      ],
                    ),
                  ),
                )
              else
                // Conversation list
                ListView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: _conversations.length,
                  itemBuilder: (context, index) => _buildConversationTile(_conversations[index]),
                ),
            ],
          ),
        ),
      ],
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
            title: Text(
              context.l10n.storeAudioOnCloud,
              style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
            ),
            centerTitle: true,
          ),
          body: isLoading
              ? const Center(child: CircularProgressIndicator(color: Colors.white))
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
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
                      // Audio files section (only visible when cloud sync is enabled)
                      _buildAudioFilesSection(isEnabled),
                    ],
                  ),
                ),
        );
      },
    );
  }
}
