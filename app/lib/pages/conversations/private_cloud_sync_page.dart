import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/providers/user_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/audio_player_utils.dart';
import 'package:omi/utils/other/time_utils.dart';

class PrivateCloudSyncPage extends StatefulWidget {
  const PrivateCloudSyncPage({super.key});

  @override
  State<PrivateCloudSyncPage> createState() => _PrivateCloudSyncPageState();
}

class _PrivateCloudSyncPageState extends State<PrivateCloudSyncPage> {
  bool _isSaving = false;

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

  Future<void> _togglePlay(Wal wal) async {
    await AudioPlayerUtils.instance.togglePlayback(wal);
  }

  Future<void> _shareWal(Wal wal) async {
    final filePath = wal.filePath;
    if (filePath != null && filePath.isNotEmpty) {
      try {
        await Share.shareXFiles(
          [XFile(filePath)],
          subject: 'Audio recording from ${dateTimeFormat('yyyy-MM-dd h:mm a', DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000))}',
        );
      } catch (e) {
        print('Error sharing audio: $e');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Failed to share audio'), backgroundColor: Colors.red),
          );
        }
      }
    }
  }

  Future<void> _deleteAllCloudFiles() async {
    final confirmed = await _showDeleteAllDialog();
    if (confirmed != true) return;

    if (!mounted) return;

    try {
      final syncProvider = context.read<SyncProvider>();
      await syncProvider.deleteAllSyncedWals();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.allFilesDeleted), backgroundColor: Colors.green),
        );
      }
    } catch (e) {
      print('Error deleting all cloud files: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to delete recordings'), backgroundColor: Colors.red),
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
            Expanded(
              child: Text(
                context.l10n.deleteAllFiles,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              context.l10n.deleteAllFilesWarning,
              style: TextStyle(color: Colors.grey.shade400, fontSize: 14, height: 1.5),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.blue.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.blue.withValues(alpha: 0.3)),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.info_outline, color: Colors.blue, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Your audio data may be used to improve AI models. Deleted recordings cannot be recovered and will not be available for AI training.',
                      style: TextStyle(color: Colors.blue.shade200, fontSize: 12, height: 1.4),
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

  Widget _buildWalListItem(Wal wal) {
    final audioUtils = AudioPlayerUtils.instance;
    final isCurrentlyPlaying = audioUtils.currentPlayingId == wal.id;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            // Play/Pause button
            GestureDetector(
              onTap: () => _togglePlay(wal),
              child: Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: Colors.deepPurpleAccent.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  isCurrentlyPlaying ? Icons.pause : Icons.play_arrow,
                  color: Colors.deepPurpleAccent,
                  size: 24,
                ),
              ),
            ),
            const SizedBox(width: 14),
            // Info
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    dateTimeFormat('MMM d, h:mm a', DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000)),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 15,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Icon(Icons.mic, size: 12, color: Colors.grey.shade500),
                      const SizedBox(width: 4),
                      Text(
                        secondsToHumanReadable(wal.seconds, context),
                        style: TextStyle(color: Colors.grey.shade500, fontSize: 12),
                      ),
                      const SizedBox(width: 12),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.green.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.cloud_done, size: 10, color: Colors.green),
                            const SizedBox(width: 3),
                            Text(
                              context.l10n.synced.toUpperCase(),
                              style: const TextStyle(color: Colors.green, fontSize: 10, fontWeight: FontWeight.w500),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            // Share button
            IconButton(
              onPressed: () => _shareWal(wal),
              icon: _buildFaIcon(FontAwesomeIcons.shareNodes, size: 16, color: Colors.grey.shade400),
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<UserProvider, SyncProvider>(
      builder: (context, userProvider, syncProvider, child) {
        final isEnabled = userProvider.privateCloudSyncEnabled;
        final isLoading = userProvider.isLoading;
        final syncedWals = syncProvider.syncedWals;

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
              if (isEnabled && syncedWals.isNotEmpty)
                TextButton(
                  onPressed: _deleteAllCloudFiles,
                  child: Text(
                    context.l10n.deleteAll,
                    style: const TextStyle(color: Colors.red, fontSize: 14, fontWeight: FontWeight.w500),
                  ),
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
                      // Toggle section
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

                      // Cloud audio files section
                      if (isEnabled) ...[
                        const SizedBox(height: 32),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              'Cloud Recordings',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 18,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                              decoration: BoxDecoration(
                                color: Colors.deepPurpleAccent.withValues(alpha: 0.2),
                                borderRadius: BorderRadius.circular(100),
                              ),
                              child: Text(
                                '${syncedWals.length} files',
                                style: const TextStyle(
                                  color: Colors.deepPurpleAccent,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        if (syncedWals.isEmpty)
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(32),
                            decoration: BoxDecoration(
                              color: const Color(0xFF1C1C1E),
                              borderRadius: BorderRadius.circular(16),
                            ),
                            child: Column(
                              children: [
                                Icon(
                                  Icons.cloud_off,
                                  size: 48,
                                  color: Colors.grey.shade600,
                                ),
                                const SizedBox(height: 12),
                                Text(
                                  'No cloud recordings yet',
                                  style: TextStyle(
                                    color: Colors.grey.shade400,
                                    fontSize: 15,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Recordings will appear here once synced',
                                  style: TextStyle(
                                    color: Colors.grey.shade600,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          )
                        else
                          ...syncedWals.map((wal) => _buildWalListItem(wal)),
                      ],
                    ],
                  ),
                ),
        );
      },
    );
  }
}
