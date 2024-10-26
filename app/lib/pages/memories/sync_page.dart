import 'package:flutter/material.dart';
import 'package:friend_private/pages/memories/widgets/sync_animation.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/services/wals.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

import 'synced_memories_page.dart';

class WalListItem extends StatefulWidget {
  final DateTime date;
  final int walIdx;
  final Wal wal;

  const WalListItem({
    super.key,
    required this.wal,
    required this.date,
    required this.walIdx,
  });

  @override
  State<WalListItem> createState() => _WalListItemState();
}

class _WalListItemState extends State<WalListItem> {
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () async {
        // TODO
      },
      child: Padding(
        padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
        child: Container(
          width: double.maxFinite,
          decoration: BoxDecoration(
            color: Colors.grey.shade900,
            borderRadius: BorderRadius.circular(16.0),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(16.0),
            child: Dismissible(
              key: Key(widget.wal.id),
              direction: widget.wal.isSyncing ? DismissDirection.none : DismissDirection.endToStart,
              background: Container(
                alignment: Alignment.centerRight,
                padding: const EdgeInsets.only(right: 20.0),
                color: Colors.red,
                child: const Icon(Icons.delete, color: Colors.white),
              ),
              onDismissed: (direction) {
                var wal = widget.wal;
                ServiceManager.instance().wal.getSyncs().deleteWal(wal);
              },
              child: Padding(
                padding: const EdgeInsetsDirectional.all(16),
                child: Column(
                  mainAxisSize: MainAxisSize.max,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _getWalHeader(),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  _getWalHeader() {
    final wal = widget.wal;
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(wal.device == "phone" ? "📱" : "💾",
              style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600)),
          const SizedBox(width: 12),
          Container(
            decoration: BoxDecoration(
              color: Colors.grey.shade800,
              borderRadius: BorderRadius.circular(16),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Text(
              "${wal.seconds}s",
              style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
              maxLines: 1,
            ),
          ),
          const SizedBox(
            width: 16,
          ),
          wal.isSyncing
              ? Expanded(
                  child: Align(
                    alignment: Alignment.centerRight,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        (wal.syncEtaSeconds ?? 0) > 0
                            ? Text(
                                "${wal.syncEtaSeconds}s ETA",
                                style: Theme.of(context)
                                    .textTheme
                                    .bodySmall!
                                    .copyWith(color: Colors.white, fontStyle: FontStyle.italic),
                              )
                            : const SizedBox.shrink(),
                        const SizedBox(
                          width: 8,
                        ),
                        const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                        ),
                      ],
                    ),
                  ),
                )
              : Expanded(
                  child: Text(
                    dateTimeFormat('MMM d, h:mm a', DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000)),
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
                    maxLines: 1,
                    textAlign: TextAlign.end,
                  ),
                )
        ],
      ),
    );
  }
}

class DateTimeListItem extends StatelessWidget {
  final bool isFirst;
  final DateTime date;

  const DateTimeListItem({super.key, required this.date, required this.isFirst});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(16, isFirst ? 0 : 20, 16, 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            dateTimeFormat('MMM dd hh:00 a', date),
            style: const TextStyle(color: Colors.white, fontSize: 16),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Container(
              height: 1,
              color: Colors.grey.shade800,
            ),
          )
        ],
      ),
    );
  }
}

class SyncWalGroupWidget extends StatelessWidget {
  final List<Wal> wals;
  final DateTime date;
  final bool isFirst;
  const SyncWalGroupWidget({super.key, required this.wals, required this.date, required this.isFirst});

  @override
  Widget build(BuildContext context) {
    if (wals.isNotEmpty) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          DateTimeListItem(date: date, isFirst: isFirst),
          ...wals.map((wal) {
            return WalListItem(wal: wal, walIdx: wals.indexOf(wal), date: date);
          }),
          const SizedBox(height: 16),
        ],
      );
    } else {
      return const SizedBox.shrink();
    }
  }
}

class SyncPage extends StatefulWidget {
  const SyncPage({super.key});

  @override
  State<SyncPage> createState() => _SyncPageState();
}

class _SyncPageState extends State<SyncPage> {
  bool _isAnimating = false;

  void _toggleAnimation() {
    setState(() {
      _isAnimating = !_isAnimating;
    });
  }

  @override
  Widget build(BuildContext context) {
    Map<DateTime, List<Wal>> _groupWalsByDate(List<Wal> wals) {
      var groupedWals = <DateTime, List<Wal>>{};
      for (var wal in wals) {
        var createdAt = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toLocal();
        var date = DateTime(createdAt.year, createdAt.month, createdAt.day, createdAt.hour);
        if (!groupedWals.containsKey(date)) {
          groupedWals[date] = [];
        }
        groupedWals[date]?.add(wal);
      }
      for (final date in groupedWals.keys) {
        groupedWals[date]?.sort((a, b) => b.timerStart.compareTo(a.timerStart));
      }
      return groupedWals;
    }

    Widget _buildWals(List<Wal> wals) {
      // sdcard
      var sdcardWals = wals.where((w) => w.storage == WalStorage.sdcard).toList();
      var sdcardGroupedWals = _groupWalsByDate(sdcardWals);
      var sdcardKeys = sdcardGroupedWals.keys.toList();
      sdcardKeys.sort((a, b) => b.compareTo(a));

      // phone
      var phoneWals = wals.where((w) => w.storage == WalStorage.disk).toList();
      var phoneGroupedWals = _groupWalsByDate(phoneWals);
      var phoneKeys = phoneGroupedWals.keys.toList();
      phoneKeys.sort((a, b) => b.compareTo(a));

      return SliverList(
        delegate: SliverChildBuilderDelegate(
          childCount: sdcardKeys.length + phoneKeys.length,
          (context, index) {
            var keys = sdcardKeys;
            var groupedWals = sdcardGroupedWals;
            var idx = index;

            // Phone sections
            if (index > sdcardKeys.length - 1) {
              keys = phoneKeys;
              groupedWals = phoneGroupedWals;
              idx -= sdcardKeys.length;
            }

            var date = keys[idx];
            List<Wal> wals = groupedWals[date] ?? [];
            return Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (index == 0) const SizedBox(height: 16),
                SyncWalGroupWidget(
                  isFirst: index == 0,
                  wals: wals,
                  date: date,
                ),
              ],
            );
          },
        ),
      );
    }

    return PopScope(
      canPop: !Provider.of<MemoryProvider>(context, listen: false).isSyncing,
      onPopInvoked: (didPop) {
        var provider = Provider.of<MemoryProvider>(context, listen: false);
        if (provider.isSyncing) {
          showDialog(
              context: context,
              builder: (ctx) {
                return getDialog(
                  context,
                  () {
                    Navigator.pop(context);
                  },
                  () {
                    Navigator.pop(context);
                  },
                  'Sync In-Progress',
                  'Memories are being synced. Please wait until the process is complete',
                  singleButton: true,
                );
              });
        } else {
          provider.clearSyncResult();
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Sync Memories'),
          backgroundColor: Theme.of(context).colorScheme.primary,
        ),
        backgroundColor: Theme.of(context).colorScheme.primary,
        body: Consumer<MemoryProvider>(
          builder: (context, memoryProvider, child) {
            var missingWals = memoryProvider.missingWals;
            var seconds = missingWals.isEmpty ? 0 : missingWals.map((val) => val.seconds).reduce((a, b) => a + b);

            return Stack(
              children: [
                CustomScrollView(
                  slivers: [
                    SliverToBoxAdapter(
                      child: Column(
                        children: [
                          const SizedBox(height: 80),
                          Text(
                            '${seconds}',
                            style: const TextStyle(color: Colors.white, fontSize: 80),
                          ),
                          const SizedBox(height: 16),
                          const Text('Seconds', style: TextStyle(color: Colors.white, fontSize: 18)),
                          const SizedBox(height: 20),
                          memoryProvider.isSyncing
                              ? const Padding(
                                  padding: EdgeInsets.all(8.0),
                                  child: Text(
                                    'Syncing Memories\nPlease don\'t close the app or press the back button',
                                    style: TextStyle(color: Colors.white, fontSize: 16),
                                    textAlign: TextAlign.center,
                                  ),
                                )
                              : memoryProvider.syncCompleted && memoryProvider.syncedMemoriesPointers.isNotEmpty
                                  ? Column(
                                      children: [
                                        const Text(
                                          'Memories Synced Successfully 🎉',
                                          style: TextStyle(color: Colors.white, fontSize: 16),
                                        ),
                                        const SizedBox(
                                          height: 18,
                                        ),
                                        (memoryProvider.syncedMemoriesPointers.isNotEmpty)
                                            ? Container(
                                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                                                decoration: BoxDecoration(
                                                  border: const GradientBoxBorder(
                                                    gradient: LinearGradient(colors: [
                                                      Color.fromARGB(127, 208, 208, 208),
                                                      Color.fromARGB(127, 188, 99, 121),
                                                      Color.fromARGB(127, 86, 101, 182),
                                                      Color.fromARGB(127, 126, 190, 236)
                                                    ]),
                                                    width: 2,
                                                  ),
                                                  borderRadius: BorderRadius.circular(12),
                                                ),
                                                child: TextButton(
                                                  onPressed: () {
                                                    routeToPage(context, const SyncedMemoriesPage());
                                                  },
                                                  child: const Text(
                                                    'View Synced Memories',
                                                    style: TextStyle(color: Colors.white, fontSize: 16),
                                                  ),
                                                ),
                                              )
                                            : const SizedBox.shrink(),
                                      ],
                                    )
                                  : const SizedBox.shrink(),
                        ],
                      ),
                    ),
                    const SliverToBoxAdapter(child: SizedBox(height: 60)),
                    _buildWals(missingWals),
                  ],
                ),
                memoryProvider.isSyncing || memoryProvider.syncCompleted
                    ? const SizedBox()
                    : Align(
                        alignment: Alignment.bottomCenter,
                        child: Container(
                          margin: const EdgeInsets.fromLTRB(32, 16, 32, 40),
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                          decoration: BoxDecoration(
                            border: const GradientBoxBorder(
                              gradient: LinearGradient(colors: [
                                Color.fromARGB(127, 208, 208, 208),
                                Color.fromARGB(127, 188, 99, 121),
                                Color.fromARGB(127, 86, 101, 182),
                                Color.fromARGB(127, 126, 190, 236)
                              ]),
                              width: 2,
                            ),
                            borderRadius: BorderRadius.circular(12),
                            color: Colors.black,
                          ),
                          child: TextButton(
                            onPressed: () async {
                              if (context.read<ConnectivityProvider>().isConnected) {
                                _toggleAnimation();
                                await memoryProvider.syncWals();
                                _toggleAnimation();
                              } else {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('Internet connection is required to sync memories'),
                                    backgroundColor: Colors.red,
                                  ),
                                );
                              }
                            },
                            child: const Text(
                              'Sync Now',
                              style: TextStyle(color: Colors.white, fontSize: 16),
                            ),
                          ),
                        ),
                      ),
              ],
            );
          },
          child: RepaintBoundary(
            child: SyncAnimation(
              isAnimating: _isAnimating,
              onStart: () {},
              onStop: () {},
              dotsPerRing: 12,
            ),
          ),
        ),
      ),
    );
  }
}
