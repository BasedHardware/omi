import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';

import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/pages/conversations/sync_page.dart';

Widget _buildFaIcon(IconData icon, {double size = 18, Color color = const Color(0xFF8E8E93)}) {
  return Padding(
    padding: const EdgeInsets.only(left: 2, top: 1),
    child: FaIcon(icon, size: size, color: color),
  );
}

class RecordingsListPage extends StatefulWidget {
  final WalStorage? initialFilter;
  const RecordingsListPage({super.key, this.initialFilter});

  @override
  State<RecordingsListPage> createState() => _RecordingsListPageState();
}

class _RecordingsListPageState extends State<RecordingsListPage> {
  @override
  void initState() {
    super.initState();
    if (widget.initialFilter != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        context.read<SyncProvider>().setStorageFilter(widget.initialFilter);
      });
    }
  }

  void _showDeleteProcessedDialog(BuildContext context, SyncProvider provider) async {
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: context.l10n.deleteProcessedFiles,
      message: context.l10n.thisCannotBeUndone,
      confirmLabel: context.l10n.delete,
      confirmColor: Colors.red,
    );
    if (confirmed == true && context.mounted) {
      await provider.deleteAllSyncedWals();
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.processedFilesDeleted), backgroundColor: Colors.green),
        );
      }
    }
  }

  Widget _buildFilterChips(WalStats? stats) {
    return Consumer<SyncProvider>(
      builder: (context, syncProvider, child) {
        final phoneCount = stats?.phoneFiles ?? 0;
        final sdCardRelatedCount = stats?.sdcardRelatedFiles ?? 0;
        final flashPageRelatedCount = stats?.flashPageRelatedFiles ?? 0;
        final totalCount = stats?.totalFiles ?? 0;

        return SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          physics: const BouncingScrollPhysics(),
          child: Row(
            children: [
              _buildChip(context.l10n.all, totalCount, syncProvider.storageFilter == null,
                  () => syncProvider.clearStorageFilter()),
              const SizedBox(width: 8),
              _buildChip(
                  context.l10n.phone,
                  phoneCount,
                  syncProvider.storageFilter == WalStorage.disk || syncProvider.storageFilter == WalStorage.mem,
                  () => syncProvider.setStorageFilter(WalStorage.disk)),
              const SizedBox(width: 8),
              if (sdCardRelatedCount > 0) ...[
                _buildChip(context.l10n.sdCard, sdCardRelatedCount, syncProvider.storageFilter == WalStorage.sdcard,
                    () => syncProvider.setStorageFilter(WalStorage.sdcard)),
                const SizedBox(width: 8),
              ],
              if (flashPageRelatedCount > 0)
                _buildChip(
                    context.l10n.limitless,
                    flashPageRelatedCount,
                    syncProvider.storageFilter == WalStorage.flashPage,
                    () => syncProvider.setStorageFilter(WalStorage.flashPage)),
            ],
          ),
        );
      },
    );
  }

  Widget _buildChip(String label, int count, bool isSelected, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? Colors.white.withOpacity(0.12) : const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(100),
          border: isSelected ? Border.all(color: Colors.white.withOpacity(0.3), width: 1) : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                color: isSelected ? Colors.white : Colors.grey.shade400,
                fontSize: 14,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
            const SizedBox(width: 6),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: isSelected ? Colors.white.withOpacity(0.2) : const Color(0xFF2A2A2E),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                '$count',
                style: TextStyle(
                  color: isSelected ? Colors.white : Colors.grey.shade500,
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyState(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(20),
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: const Color(0xFF2A2A2E),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Center(child: _buildFaIcon(FontAwesomeIcons.microphone, size: 24)),
          ),
          const SizedBox(height: 20),
          Text(context.l10n.noRecordings,
              style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          Text(context.l10n.audioFromOmiWillAppearHere,
              style: TextStyle(color: Colors.grey.shade500, fontSize: 14), textAlign: TextAlign.center),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SyncProvider>(builder: (context, syncProvider, child) {
      return Scaffold(
        backgroundColor: const Color(0xFF0D0D0D),
        appBar: AppBar(
          backgroundColor: const Color(0xFF0D0D0D),
          elevation: 0,
          leading: IconButton(
            icon: const Padding(
              padding: EdgeInsets.only(left: 2, top: 1),
              child: FaIcon(FontAwesomeIcons.chevronLeft, size: 18),
            ),
            onPressed: () => Navigator.of(context).pop(),
          ),
          title: Text(context.l10n.recordings,
              style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600)),
          centerTitle: true,
          actions: [
            PullDownButton(
              itemBuilder: (context) => [
                PullDownMenuItem(
                  title: context.l10n.deleteProcessed,
                  iconWidget: _buildFaIcon(FontAwesomeIcons.trash, size: 16, color: Colors.red),
                  isDestructive: true,
                  onTap: () => _showDeleteProcessedDialog(context, syncProvider),
                ),
              ],
              buttonBuilder: (context, showMenu) => GestureDetector(
                onTap: () {
                  HapticFeedback.mediumImpact();
                  showMenu();
                },
                child: Container(
                  width: 36,
                  height: 36,
                  margin: const EdgeInsets.only(right: 8),
                  decoration: BoxDecoration(
                    color: Colors.grey.withOpacity(0.3),
                    shape: BoxShape.circle,
                  ),
                  child: Center(
                    child: _buildFaIcon(FontAwesomeIcons.ellipsisVertical, size: 16, color: Colors.white),
                  ),
                ),
              ),
            ),
          ],
        ),
        body: FutureBuilder<WalStats>(
          future: syncProvider.getWalStats(),
          builder: (context, statsSnapshot) {
            return CustomScrollView(
              slivers: [
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SizedBox(height: 16),
                        _buildFilterChips(statsSnapshot.data),
                        const SizedBox(height: 16),
                      ],
                    ),
                  ),
                ),
                Consumer<SyncProvider>(
                  builder: (context, syncProvider, child) {
                    if (syncProvider.isLoadingWals && syncProvider.allWals.isEmpty) {
                      return const SliverToBoxAdapter(
                        child: Center(
                            child: Padding(
                                padding: EdgeInsets.all(32), child: CircularProgressIndicator(color: Colors.white))),
                      );
                    }

                    final filteredWals = syncProvider.filteredWals;

                    if (syncProvider.allWals.isEmpty) {
                      return SliverToBoxAdapter(child: _buildEmptyState(context));
                    }

                    if (filteredWals.isEmpty && syncProvider.storageFilter != null) {
                      return SliverToBoxAdapter(
                        child: Container(
                          margin: const EdgeInsets.all(20),
                          padding: const EdgeInsets.all(32),
                          decoration: BoxDecoration(
                            color: const Color(0xFF1C1C1E),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Column(
                            children: [
                              _buildFaIcon(FontAwesomeIcons.filter, size: 24),
                              const SizedBox(height: 16),
                              Text(context.l10n.noRecordings,
                                  style:
                                      const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w500)),
                              const SizedBox(height: 4),
                              Text(context.l10n.tryDifferentFilter,
                                  style: TextStyle(color: Colors.grey.shade500, fontSize: 14)),
                            ],
                          ),
                        ),
                      );
                    }

                    return OptimizedWalsListWidget(wals: filteredWals);
                  },
                ),
                const SliverToBoxAdapter(child: SizedBox(height: 100)),
              ],
            );
          },
        ),
      );
    });
  }
}
