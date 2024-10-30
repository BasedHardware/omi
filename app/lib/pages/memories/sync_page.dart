import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:friend_private/pages/settings/widgets/appbar_with_banner.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/services/wals.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/utils/other/time_utils.dart';
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
  double calculateProgress(DateTime? startedAt, int eta) {
    if (startedAt == null) {
      return 0.0;
    }
    if (eta == 0) {
      return 0.01;
    }
    final elapsed = DateTime.now().difference(startedAt).inSeconds;
    final progress = elapsed / eta;
    return progress.clamp(0.0, 1.0);
  }

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
                padding: const EdgeInsetsDirectional.all(0),
                child: Column(
                  mainAxisSize: MainAxisSize.max,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    ListTile(
                      leading: Padding(
                        padding: const EdgeInsets.only(top: 6.0),
                        child: Text(widget.wal.device == "phone" ? "📱" : "💾",
                            style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600)),
                      ),
                      title: Text(
                        secondsToHumanReadable(widget.wal.seconds),
                        style: const TextStyle(color: Colors.white, fontSize: 16),
                      ),
                      subtitle: Text(
                        dateTimeFormat('h:mm a', DateTime.fromMillisecondsSinceEpoch(widget.wal.timerStart * 1000)),
                        style: const TextStyle(color: Colors.grey, fontSize: 14),
                      ),
                      trailing: widget.wal.isSyncing
                          ? Text(
                              "${widget.wal.syncEtaSeconds != null ? "${widget.wal.syncEtaSeconds}s" : "Calculating"} ETA",
                              style: const TextStyle(color: Colors.white, fontSize: 16),
                            )
                          : TextButton(
                              onPressed: () {
                                context.read<MemoryProvider>().setSyncCompleted(false);
                                context.read<MemoryProvider>().syncWal(widget.wal);
                              },
                              child: const Text('Sync', style: TextStyle(color: Colors.white))),
                    ),
                    if (widget.wal.isSyncing)
                      LinearProgressIndicator(
                        value: calculateProgress(
                            widget.wal.syncStartedAt ?? DateTime.now(), widget.wal.syncEtaSeconds ?? 0),
                        backgroundColor: Colors.grey[800],
                        color: Colors.white,
                        minHeight: 4,
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
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

class _SyncPageState extends State<SyncPage> with TickerProviderStateMixin {
  late AnimationController _hideFabAnimation;

  @override
  void initState() {
    _hideFabAnimation = AnimationController(vsync: this, duration: kThemeAnimationDuration, value: 1.0);
    super.initState();
  }

  @override
  void dispose() {
    _hideFabAnimation.dispose();
    super.dispose();
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification.depth == 0) {
      if (notification is UserScrollNotification) {
        final UserScrollNotification userScroll = notification;
        switch (userScroll.direction) {
          case ScrollDirection.forward:
            if (userScroll.metrics.maxScrollExtent != userScroll.metrics.minScrollExtent) {
              _hideFabAnimation.forward();
            }
            break;
          case ScrollDirection.reverse:
            if (userScroll.metrics.maxScrollExtent != userScroll.metrics.minScrollExtent) {
              _hideFabAnimation.reverse();
            }
            break;
          case ScrollDirection.idle:
            break;
        }
      }
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: true,
      onPopInvoked: (didPop) {
        var provider = Provider.of<MemoryProvider>(context, listen: false);
        if (!provider.isSyncing) {
          provider.clearSyncResult();
        }
      },
      child: Consumer<MemoryProvider>(builder: (context, memoryProvider, child) {
        return Scaffold(
          appBar: AppBarWithBanner(
            appBar: AppBar(
              title: const Text('Sync Memories'),
              backgroundColor: Theme.of(context).colorScheme.primary,
            ),
            showAppBar: memoryProvider.isSyncing || memoryProvider.syncCompleted,
            child: Container(
              color: Colors.green,
              child: Center(
                child: Text(
                  memoryProvider.isSyncing
                      ? 'Syncing Memories'
                      : memoryProvider.syncCompleted
                          ? 'Memories Synced Successfully 🎉'
                          : '',
                  style: const TextStyle(color: Colors.white, fontSize: 12),
                ),
              ),
            ),
          ),
          backgroundColor: Theme.of(context).colorScheme.primary,
          floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
          floatingActionButton: memoryProvider.isSyncing || memoryProvider.syncCompleted
              ? const SizedBox()
              : ScaleTransition(
                  scale: _hideFabAnimation,
                  child: Container(
                    margin: const EdgeInsets.fromLTRB(32, 16, 32, 0),
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
                          // _toggleAnimation();
                          await memoryProvider.syncWals();
                          // _toggleAnimation();
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
                        'Sync All',
                        style: TextStyle(color: Colors.white, fontSize: 16),
                      ),
                    ),
                  ),
                ),
          body: NotificationListener(
            onNotification: _handleScrollNotification,
            child: CustomScrollView(
              slivers: [
                SliverToBoxAdapter(
                  child: Column(
                    children: [
                      memoryProvider.isSyncing
                          ? Container(
                              padding: const EdgeInsets.all(12.0),
                              margin: const EdgeInsets.only(left: 16.0, right: 16.0, top: 12),
                              decoration: BoxDecoration(
                                color: Colors.grey.shade900,
                                borderRadius: BorderRadius.circular(16.0),
                              ),
                              child: const ListTile(
                                leading: Icon(
                                  Icons.warning,
                                  color: Colors.yellow,
                                ),
                                title: Text('Please do not close the app while sync is in progress'),
                              ),
                            )
                          : const SizedBox.shrink(),
                      const SizedBox(height: 30),
                      Text(
                        secondsToHumanReadable(memoryProvider.missingWalsInSeconds),
                        style: const TextStyle(color: Colors.white, fontSize: 30),
                      ),
                      const SizedBox(height: 12),
                      const Text('of conversations', style: TextStyle(color: Colors.white, fontSize: 18)),
                      const SizedBox(height: 20),
                      memoryProvider.isSyncing
                          ? memoryProvider.isFetchingMemories
                              ? const Padding(
                                  padding: EdgeInsets.all(8.0),
                                  child: Row(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      SizedBox(
                                        height: 20,
                                        width: 20,
                                        child: CircularProgressIndicator(
                                          color: Colors.white,
                                        ),
                                      ),
                                      SizedBox(width: 12),
                                      Text(
                                        'Finalizing synced memories',
                                        style: TextStyle(color: Colors.white, fontSize: 16),
                                        textAlign: TextAlign.center,
                                      ),
                                    ],
                                  ),
                                )
                              : const Padding(
                                  padding: EdgeInsets.all(8.0),
                                  child: Text(
                                    'Sync in Progress',
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
                const SliverToBoxAdapter(child: SizedBox(height: 50)),
                WalsListWidget(wals: memoryProvider.missingWals),
                const SliverToBoxAdapter(child: SizedBox(height: 50)),
              ],
            ),
          ),
        );
      }),
    );
  }
}

Map<DateTime, List<Wal>> _groupWalsByDate(List<Wal> wals) {
  var groupedWals = <DateTime, List<Wal>>{};
  wals.sort((a, b) => b.timerStart.compareTo(a.timerStart));
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

class WalsListWidget extends StatelessWidget {
  final List<Wal> wals;
  const WalsListWidget({super.key, required this.wals});

  @override
  Widget build(BuildContext context) {
    var groupedWals = _groupWalsByDate(wals);

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        childCount: groupedWals.keys.length,
        (context, index) {
          var date = groupedWals.keys.toList()[index];
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
}
