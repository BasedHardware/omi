import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:just_audio/just_audio.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/audio_download_service.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

class PrivateCloudSyncPage extends StatefulWidget {
  const PrivateCloudSyncPage({
    super.key,
    this.loadCloudAudioConversations,
    this.deleteAllCloudAudio,
    this.confirmDeleteOverride,
  });

  final Future<List<CloudAudioConversation>> Function()? loadCloudAudioConversations;
  final Future<bool> Function()? deleteAllCloudAudio;
  final Future<bool?> Function(BuildContext context)? confirmDeleteOverride;

  @override
  State<PrivateCloudSyncPage> createState() => _PrivateCloudSyncPageState();
}

class _PrivateCloudSyncPageState extends State<PrivateCloudSyncPage> {
  bool _isSaving = false;
  bool _isLoadingAudio = false;
  bool _isDeleting = false;
  bool _isAudioLoading = false;
  List<CloudAudioConversation> _conversations = [];
  bool? _lastPrivateCloudSyncEnabled;
  int _playbackGeneration = 0;
  int _cloudAudioRequestGeneration = 0;

  final AudioPlayer _audioPlayer = AudioPlayer();
  StreamSubscription<PlayerState>? _playerStateSubscription;
  String? _currentPlayingConversationId;

  @override
  void initState() {
    super.initState();
    _playerStateSubscription = _audioPlayer.playerStateStream.listen((playerState) async {
      if (playerState.processingState == ProcessingState.completed) {
        await _audioPlayer.seek(Duration.zero, index: 0);
        if (!mounted) return;
        setState(() {
          _currentPlayingConversationId = null;
          _isAudioLoading = false;
        });
        return;
      }

      if (mounted) {
        setState(() {});
      }
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();

    final isEnabled = context.watch<UserProvider>().privateCloudSyncEnabled;
    if (_lastPrivateCloudSyncEnabled == isEnabled) return;
    _lastPrivateCloudSyncEnabled = isEnabled;

    if (isEnabled) {
      unawaited(_loadCloudAudioConversations());
      return;
    }

    _cancelPendingPlayback(clearConversations: true);
  }

  void _cancelPendingPlayback({bool clearConversations = false}) {
    _playbackGeneration++;
    unawaited(_audioPlayer.stop());
    _currentPlayingConversationId = null;
    _isAudioLoading = false;
    if (clearConversations) {
      _invalidateCloudAudioRequests(clearLoading: true);
      _conversations = [];
    }
  }

  void _invalidateCloudAudioRequests({bool clearLoading = false}) {
    _cloudAudioRequestGeneration++;
    if (clearLoading) {
      _isLoadingAudio = false;
    }
  }

  bool _shouldAbortPlaybackStart(String conversationId, int playbackGeneration) {
    return !mounted ||
        _isDeleting ||
        !context.read<UserProvider>().privateCloudSyncEnabled ||
        _currentPlayingConversationId != conversationId ||
        _playbackGeneration != playbackGeneration;
  }

  @override
  void dispose() {
    _playerStateSubscription?.cancel();
    _audioPlayer.dispose();
    super.dispose();
  }

  Future<void> _loadCloudAudioConversations() async {
    if (!mounted) return;
    final requestGeneration = ++_cloudAudioRequestGeneration;
    setState(() => _isLoadingAudio = true);
    try {
      final conversations = await (widget.loadCloudAudioConversations ?? getCloudAudioConversations)();
      if (!mounted || requestGeneration != _cloudAudioRequestGeneration) return;
      setState(() {
        _conversations = conversations;
        _isLoadingAudio = false;
      });
    } catch (e) {
      Logger.debug('Error loading cloud audio conversations: $e');
      if (!mounted || requestGeneration != _cloudAudioRequestGeneration) return;
      setState(() => _isLoadingAudio = false);
    }
  }

  Future<void> _togglePrivateCloudSync(bool value) async {
    final userProvider = context.read<UserProvider>();

    if (value) {
      final confirmed = await _showEnableDialog();
      if (confirmed != true) return;
    }

    if (!value) {
      setState(() => _cancelPendingPlayback());
    }

    setState(() => _isSaving = true);
    try {
      await userProvider.setPrivateCloudSync(value);
      if (!mounted) return;
      setState(() => _isSaving = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(value ? context.l10n.cloudStorageEnabled : context.l10n.cloudStorageDisabled),
          backgroundColor: Colors.green,
        ),
      );
    } catch (e) {
      Logger.debug('Error toggling cloud storage: $e');
      if (!mounted) return;
      setState(() => _isSaving = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(context.l10n.failedToUpdateSettings(e.toString())), backgroundColor: Colors.red),
      );
    }
  }

  Future<void> _playConversationAudio(CloudAudioConversation conversation) async {
    if (_isAudioLoading) {
      return;
    }

    if (_currentPlayingConversationId == conversation.id) {
      if (_audioPlayer.playing) {
        await _audioPlayer.pause();
      } else {
        await _audioPlayer.play();
      }
      if (mounted) setState(() {});
      return;
    }

    // Capture the generation token BEFORE the first await so that a
    // concurrent cancel() that increments _playbackGeneration cannot
    // sneak in between the stop() call and the token read.
    final playbackGeneration = ++_playbackGeneration;
    await _audioPlayer.stop();
    if (!mounted) return;
    setState(() {
      _currentPlayingConversationId = conversation.id;
      _isAudioLoading = true;
    });

    try {
      final audioFileInfos = await getConversationAudioSignedUrls(conversation.id);
      if (_shouldAbortPlaybackStart(conversation.id, playbackGeneration)) {
        if (mounted) {
          setState(() {
            _currentPlayingConversationId = null;
            _isAudioLoading = false;
          });
        }
        return;
      }
      if (audioFileInfos.isEmpty) {
        throw Exception('No audio files available to play');
      }

      if (audioFileInfos.any((af) => !af.isCached)) {
        await precacheConversationAudio(conversation.id);
        if (_shouldAbortPlaybackStart(conversation.id, playbackGeneration)) return;
        setState(() {
          _currentPlayingConversationId = null;
          _isAudioLoading = false;
        });
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.preparingCloudAudioTryAgain), backgroundColor: Colors.orange),
        );
        return;
      }

      final headers = await getAudioHeaders();
      final urls = getConversationAudioUrls(
        conversationId: conversation.id,
        audioFileIds: audioFileInfos.map((af) => af.id).toList(),
        format: 'wav',
      );

      final playlist = ConcatenatingAudioSource(
        useLazyPreparation: true,
        children: urls.map((url) => AudioSource.uri(Uri.parse(url), headers: headers)).toList(),
      );

      await _audioPlayer.setAudioSource(playlist, preload: true);
      if (_shouldAbortPlaybackStart(conversation.id, playbackGeneration)) {
        await _audioPlayer.stop();
        if (mounted) {
          setState(() {
            _currentPlayingConversationId = null;
            _isAudioLoading = false;
          });
        }
        return;
      }
      setState(() => _isAudioLoading = false);
      await _audioPlayer.play();
      if (_shouldAbortPlaybackStart(conversation.id, playbackGeneration)) {
        await _audioPlayer.stop();
        if (mounted) {
          setState(() {
            _currentPlayingConversationId = null;
          });
        }
      }
    } catch (e) {
      Logger.debug('Error playing conversation audio: $e');
      if (!mounted) return;
      setState(() {
        _currentPlayingConversationId = null;
        _isAudioLoading = false;
      });
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(context.l10n.failedToPlayCloudAudio), backgroundColor: Colors.red));
    }
  }

  Future<void> _shareConversationAudio(CloudAudioConversation conversation) async {
    AudioDownloadService? service;
    try {
      final audioFileInfos = await getConversationAudioSignedUrls(conversation.id);
      if (audioFileInfos.isEmpty) {
        throw Exception('No audio file available to share');
      }

      if (audioFileInfos.any((af) => !af.isCached || af.signedUrl == null)) {
        await precacheConversationAudio(conversation.id);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.preparingCloudAudioTryAgain), backgroundColor: Colors.orange),
        );
        return;
      }

      service = AudioDownloadService();
      final file = await service.downloadAndCombineCloudAudio(
        conversation.title,
        audioFileInfos.map((audio) => DownloadableCloudAudioFile(url: audio.signedUrl!)).toList(),
      );

      if (file == null) {
        throw Exception('No audio file available to share');
      }

      await SharePlus.instance.share(ShareParams(files: [XFile(file.path, mimeType: 'audio/wav')]));
      await service.cleanup();
    } catch (e) {
      Logger.debug('Error sharing cloud audio: $e');
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(context.l10n.failedToShareCloudAudio), backgroundColor: Colors.red));
    } finally {
      await service?.cleanup();
      service?.dispose();
    }
  }

  Future<void> _deleteAllAudio() async {
    final confirmed = await (widget.confirmDeleteOverride?.call(context) ?? _showDeleteAllDialog());
    if (confirmed != true) return;

    setState(() {
      _isDeleting = true;
      _invalidateCloudAudioRequests(clearLoading: true);
    });
    _cancelPendingPlayback();

    try {
      final success = await (widget.deleteAllCloudAudio ?? deleteAllCloudAudio)();
      if (!mounted) return;
      setState(() => _isDeleting = false);
      if (success) {
        setState(() {
          _conversations = [];
        });
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(context.l10n.audioDeletedSuccessfully), backgroundColor: Colors.green));
      } else {
        // Backend may have partially deleted — reload to reconcile UI with
        // actual server state rather than leaving stale rows.
        unawaited(_loadCloudAudioConversations());
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(context.l10n.failedToDeleteAudio), backgroundColor: Colors.red));
      }
    } catch (e) {
      Logger.debug('Error deleting all audio: $e');
      if (!mounted) return;
      setState(() {
        _isDeleting = false;
      });
      // Backend state is unknown after an exception — reload to reconcile.
      unawaited(_loadCloudAudioConversations());
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(context.l10n.failedToDeleteAudio), backgroundColor: Colors.red));
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
    final duration = Duration(milliseconds: (seconds * 1000).round());
    final hours = duration.inHours;
    final minutes = duration.inMinutes.remainder(60).toString().padLeft(2, '0');
    final secs = duration.inSeconds.remainder(60).toString().padLeft(2, '0');

    if (hours > 0) {
      return '$hours:$minutes:$secs';
    }
    return '$minutes:$secs';
  }

  String _formatDate(DateTime? date) {
    if (date == null) return '';

    final localizations = MaterialLocalizations.of(context);
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final target = DateTime(date.year, date.month, date.day);
    final diff = today.difference(target).inDays;

    if (diff == 0) return context.l10n.today;
    if (diff == 1) return context.l10n.yesterday;
    return localizations.formatMediumDate(date);
  }

  Widget _buildConversationTile(CloudAudioConversation conversation) {
    final isSelected = _currentPlayingConversationId == conversation.id;
    final isPlaying = isSelected && _audioPlayer.playing;
    final isLoading = _isAudioLoading;
    final isSelectedLoading = isSelected && _isAudioLoading;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: isSelected ? const Color(0xFF2A2A2E).withValues(alpha: 0.8) : const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(14),
        border: isSelected ? Border.all(color: Colors.deepPurpleAccent.withValues(alpha: 0.4)) : null,
      ),
      child: Row(
        children: [
          GestureDetector(
            onTap: isLoading ? null : () => _playConversationAudio(conversation),
            child: Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: isSelected ? Colors.deepPurpleAccent : const Color(0xFF2A2A2E),
                shape: BoxShape.circle,
              ),
              child: Center(
                child: isSelectedLoading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                      )
                    : Icon(isPlaying ? Icons.pause : Icons.play_arrow, color: Colors.white, size: 22),
              ),
            ),
          ),
          const SizedBox(width: 12),
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
                Wrap(
                  crossAxisAlignment: WrapCrossAlignment.center,
                  spacing: 8,
                  children: [
                    Text(
                      context.l10n.nAudioFiles(conversation.audioFileCount),
                      style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                    ),
                    Text(
                      _formatDuration(conversation.totalDuration),
                      style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                    ),
                    if (conversation.createdAt != null)
                      Text(
                        _formatDate(conversation.createdAt),
                        style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                      ),
                  ],
                ),
              ],
            ),
          ),
          IconButton(
            onPressed: () => _shareConversationAudio(conversation),
            icon: const Icon(Icons.share_outlined, color: Color(0xFF8E8E93), size: 20),
            splashRadius: 20,
            tooltip: context.l10n.shareAudio,
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
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(color: const Color(0xFF1C1C1E), borderRadius: BorderRadius.circular(20)),
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
                  if (!_isDeleting)
                    TextButton.icon(
                      onPressed: _deleteAllAudio,
                      icon: const Icon(Icons.delete_outline, size: 16, color: Colors.red),
                      label: Text(context.l10n.deleteAllAudio, style: const TextStyle(color: Colors.red, fontSize: 13)),
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
                          Text(context.l10n.deletingAudio, style: TextStyle(color: Colors.grey.shade400, fontSize: 14)),
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
                                    color: isEnabled ? Colors.green.withValues(alpha: 0.2) : const Color(0xFF2A2A2E),
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
                      _buildAudioFilesSection(isEnabled),
                    ],
                  ),
                ),
        );
      },
    );
  }
}
