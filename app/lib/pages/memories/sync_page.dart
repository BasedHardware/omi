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

class SyncPage extends StatefulWidget {
  const SyncPage({super.key});

  @override
  State<SyncPage> createState() => _SyncPageState();
}

class _SyncPageState extends State<SyncPage> {
  bool _isAnimating = false;

  IWalService get _wal => ServiceManager.instance().wal;

  void _toggleAnimation() {
    setState(() {
      _isAnimating = !_isAnimating;
    });
  }

  @override
  Widget build(BuildContext context) {
    // TODO: FIXME
    List<Widget> _buildWals(List<Wal> wals) {
      var views = <Widget>[];

      for (var i = 0; i < wals.length; i++) {
        var wal = wals[i];
        views.add(Container(
            child: Row(
          children: [
            Text("${wal.id} - ${wal.seconds}"),
            TextButton(
              onPressed: () {
                _wal.getSyncs().deleteWal(wal);
              },
              child: Text(
                "Delete",
                style: TextStyle(
                  color: Colors.white,
                ),
              ),
            ),
          ],
        )));
      }

      return views;
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
            return SingleChildScrollView(
              child: Center(
                child: Column(
                  children: [
                    const SizedBox(height: 80),
                    child!,
                    const SizedBox(height: 80),
                    memoryProvider.isSyncing || memoryProvider.syncCompleted
                        ? const SizedBox()
                        : Container(
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
                    const SizedBox(
                      height: 20,
                    ),
                    Column(
                      children: _buildWals(memoryProvider.missingWals),
                    ),
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
