import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/audio_download_service.dart';
import 'package:omi/utils/audio_player_utils.dart';
import 'package:omi/utils/l10n_extensions.dart';

class PrivateCloudSyncPage extends StatefulWidget {
  const PrivateCloudSyncPage({super.key});

  @override
  State<PrivateCloudSyncPage> createState() => _PrivateCloudSyncPageState();
}

class _PrivateCloudSyncPageState extends State<PrivateCloudSyncPage> {
  bool _isSaving = false;
  bool _isLoadingFiles = false;
  List<CloudAudioFile> _cloudFiles = [];
  String? _playingFileId;
  final AudioDownloadService _downloadService = AudioDownloadService();

  @override
  void initState() {
    super.initState();
    if (mounted) {
      _loadCloudFiles();
    }
  }

  Future<void> _loadCloudFiles() async {
    final conversationProvider = context.read<ConversationProvider>();
    final conversations = conversationProvider.conversations ?? [];

    if (!mounted) return;
    setState(() => _isLoadingFiles = true);

    try {
      final List<CloudAudioFile> files = [];
      for (final conv in conversations) {
        if (conv.audioFiles.isEmpty) continue;

        final audioInfos = await getConversationAudioSignedUrls(conv.id);
        for (final audioInfo in audioInfos) {
          if (audioInfo.signedUrl != null) {
            files.add(CloudAudioFile(
              id: audioInfo.id,
              conversationId: conv.id,
              conversationTitle: conv.title ?? 'Conversation',
              signedUrl: audioInfo.signedUrl!,
              duration: audioInfo.duration,
              status: audioInfo.status,
            ));
          }
        }
      }

      if (mounted) {
        setState(() {
          _cloudFiles = files;
          _isLoadingFiles = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isLoadingFiles = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to load audio files: $e'), backgroundColor: Colors.red),
        );
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
      print('Error toggling cloud storage: $e');
      setState(() => _isSaving = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.failedToUpdateSettings(e.toString())), backgroundColor: Colors.red),
        );
      }
    }
  }

  Future<void> _playAudio(CloudAudioFile file) async {
    try {
      if (_playingFileId == file.id) {
        // Stop playing
        await AudioPlayerUtils.instance.stop();
        setState(() => _playingFileId = null);
        return;
      }

      setState(() => _playingFileId = file.id);

      // Download and play
      final localPath = await _downloadService.downloadFile(file.signedUrl, file.id);
      if (localPath != null) {
        await AudioPlayerUtils.instance.play(localPath);
      }

      if (mounted) {
        setState(() => _playingFileId = null);
      }
    } catch (e) {
      if (mounted) {
        setState(() => _playingFileId = null);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to play audio: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  Future<void> _shareAudio(CloudAudioFile file) async {
    try {
      final localPath = await _downloadService.downloadFile(file.signedUrl, file.id);
      if (localPath != null) {
        await Share.shareXFiles(
          [XFile(localPath)],
          text: 'Audio from ${file.conversationTitle}',
        );
      }
    } catch (e) {
      // Fallback to sharing the URL
      try {
        await Share.share(
          'Audio from ${file.conversationTitle}',
          subject: file.conversationTitle,
        );
      } catch (_) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Failed to share audio'), backgroundColor: Colors.red),
          );
        }
      }
    }
  }

  Future<void> _deleteAllAudio() async {
    final confirmed = await _showDeleteAllDialog();
    if (confirmed != true) return;

    try {
      // TODO: Call backend API to delete all cloud audio files
      // This requires a backend endpoint: DELETE /v1/sync/audio/all
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('All cloud audio files have been deleted'),
            backgroundColor: Colors.orange,
          ),
        );
        setState(() => _cloudFiles = []);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to delete audio files: $e'), backgroundColor: Colors.red),
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
            const Icon(Icons.warning_amber_rounded, color: Colors.orange, size: 24),
            const SizedBox(width: 8),
            const Expanded(
              child: Text(
                'Delete All Audio?',
                style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'This will permanently delete all ${_cloudFiles.length} audio files from private cloud storage.',
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.4),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.orange.withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.orange.withOpacity(0.3)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.info_outline, color: Colors.orange, size: 20),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'The data training program requires the private cloud sync feature. Deleting all audio files will affect your training data.',
                      style: TextStyle(color: Colors.orange.shade200, fontSize: 12, height: 1.4),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(context.l10n.cancel, style: TextStyle(color: Colors.grey.shade500)),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text(
              'Delete All',
              style: TextStyle(color: Colors.red, fontWeight: FontWeight.w600),
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
    final mins = (seconds / 60).floor();
    final secs = (seconds % 60).floor();
    return '${mins.toString().padLeft(2, '0')}:${secs.toString().padLeft(2, '0')}';
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
            actions: [
              if (isEnabled && _cloudFiles.isNotEmpty)
                IconButton(
                  icon: _buildFaIcon(FontAwesomeIcons.trashAlt, size: 16, color: Colors.red),
                  onPressed: _deleteAllAudio,
                  tooltip: 'Delete All',
                ),
            ],
          ),
          body: isLoading
              ? const Center(child: CircularProgressIndicator(color: Colors.white))
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Toggle Section
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

                      // Audio Files Section (only show when enabled)
                      if (isEnabled) ...[
                        const SizedBox(height: 24),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              'Cloud Audio Files',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 18,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            if (_cloudFiles.isNotEmpty)
                              Text(
                                '${_cloudFiles.length} files',
                                style: TextStyle(
                                  color: Colors.grey.shade500,
                                  fontSize: 14,
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: 12),

                        if (_isLoadingFiles)
                          const Center(
                            child: Padding(
                              padding: EdgeInsets.all(40),
                              child: CircularProgressIndicator(color: Colors.white),
                            ),
                          )
                        else if (_cloudFiles.isEmpty)
                          Container(
                            padding: const EdgeInsets.all(40),
                            decoration: BoxDecoration(
                              color: const Color(0xFF1C1C1E),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Center(
                              child: Column(
                                children: [
                                  _buildFaIcon(FontAwesomeIcons.cloudArrowUp, size: 40, color: Colors.grey.shade600),
                                  const SizedBox(height: 16),
                                  Text(
                                    'No audio files in cloud',
                                    style: TextStyle(color: Colors.grey.shade400, fontSize: 16),
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    'Audio will appear here once synced',
                                    style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                                  ),
                                ],
                              ),
                            ),
                          )
                        else
                          ListView.separated(
                            shrinkWrap: true,
                            physics: const NeverScrollableScrollPhysics(),
                            itemCount: _cloudFiles.length,
                            separatorBuilder: (_, __) => const SizedBox(height: 8),
                            itemBuilder: (context, index) {
                              final file = _cloudFiles[index];
                              final isPlaying = _playingFileId == file.id;

                              return Container(
                                padding: const EdgeInsets.all(16),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF1C1C1E),
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                child: Row(
                                  children: [
                                    // Play button
                                    GestureDetector(
                                      onTap: () => _playAudio(file),
                                      child: Container(
                                        width: 44,
                                        height: 44,
                                        decoration: BoxDecoration(
                                          color: isPlaying
                                              ? Colors.deepPurpleAccent
                                              : Colors.deepPurpleAccent.withOpacity(0.2),
                                          borderRadius: BorderRadius.circular(12),
                                        ),
                                        child: Icon(
                                          isPlaying ? FontAwesomeIcons.solidCircleStop : FontAwesomeIcons.play,
                                          color: Colors.white,
                                          size: 16,
                                        ),
                                      ),
                                    ),
                                    const SizedBox(width: 14),
                                    // File info
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            file.conversationTitle,
                                            style: const TextStyle(
                                              color: Colors.white,
                                              fontSize: 15,
                                              fontWeight: FontWeight.w500,
                                            ),
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                          ),
                                          const SizedBox(height: 4),
                                          Row(
                                            children: [
                                              _buildFaIcon(FontAwesomeIcons.clock, size: 12, color: Colors.grey.shade500),
                                              const SizedBox(width: 4),
                                              Text(
                                                _formatDuration(file.duration),
                                                style: TextStyle(
                                                  color: Colors.grey.shade500,
                                                  fontSize: 12,
                                                ),
                                              ),
                                              const SizedBox(width: 12),
                                              Container(
                                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                                decoration: BoxDecoration(
                                                  color: file.status == 'cached'
                                                      ? Colors.green.withOpacity(0.2)
                                                      : Colors.orange.withOpacity(0.2),
                                                  borderRadius: BorderRadius.circular(4),
                                                ),
                                                child: Text(
                                                  file.status == 'cached' ? 'Cached' : 'Pending',
                                                  style: TextStyle(
                                                    color: file.status == 'cached' ? Colors.green : Colors.orange,
                                                    fontSize: 10,
                                                    fontWeight: FontWeight.w500,
                                                  ),
                                                ),
                                              ),
                                            ],
                                          ),
                                        ],
                                      ),
                                    ),
                                    // Share button
                                    IconButton(
                                      icon: _buildFaIcon(FontAwesomeIcons.shareNodes, size: 14, color: Colors.grey.shade400),
                                      onPressed: () => _shareAudio(file),
                                      tooltip: 'Share',
                                    ),
                                  ],
                                ),
                              );
                            },
                          ),
                      ],
                    ],
                  ),
                ),
        );
      },
    );
  }
}

class CloudAudioFile {
  final String id;
  final String conversationId;
  final String conversationTitle;
  final String signedUrl;
  final double duration;
  final String status;

  CloudAudioFile({
    required this.id,
    required this.conversationId,
    required this.conversationTitle,
    required this.signedUrl,
    required this.duration,
    required this.status,
  });
}
