import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:omi/pages/settings/widgets/appbar_with_banner.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/widgets/downloaded_files_widget.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';

import 'synced_conversations_page.dart';

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
            color: const Color(0xFF1F1F25),
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
                        child: Text(widget.wal.device == "phone" ? "📱" : "💾", style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w500)),
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
                                context.read<ConversationProvider>().setSyncCompleted(false);
                                context.read<ConversationProvider>().syncWal(widget.wal);
                              },
                              child: const Text('Sync', style: TextStyle(color: Colors.white))),
                    ),
                    if (widget.wal.isSyncing)
                      LinearProgressIndicator(
                        value: calculateProgress(widget.wal.syncStartedAt ?? DateTime.now(), widget.wal.syncEtaSeconds ?? 0),
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
              color: Color(0xFF35343B),
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
    
    // Load device storage files when page initializes, but only if device is connected
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final captureProvider = Provider.of<CaptureProvider>(context, listen: false);
      // Only try to update storage list if we have a connected device
      if (captureProvider.havingRecordingDevice) {
        captureProvider.updateStorageList();
      }
    });
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
        var provider = Provider.of<ConversationProvider>(context, listen: false);
        if (!provider.isSyncing) {
          provider.clearSyncResult();
        }
      },
      child: Consumer<ConversationProvider>(builder: (context, conversationProvider, child) {
        return Scaffold(
          appBar: AppBarWithBanner(
            appBar: AppBar(
              title: const Text('Sync Conversations'),
              backgroundColor: Theme.of(context).colorScheme.primary,
            ),
            showAppBar: conversationProvider.isSyncing || conversationProvider.syncCompleted,
            child: Container(
              color: Colors.green,
              child: Center(
                child: Text(
                  conversationProvider.isSyncing
                      ? 'Syncing Conversations'
                      : conversationProvider.syncCompleted
                          ? 'Conversations Synced Successfully 🎉'
                          : '',
                  style: const TextStyle(color: Colors.white, fontSize: 12),
                ),
              ),
            ),
          ),
          backgroundColor: Theme.of(context).colorScheme.primary,
          floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
          floatingActionButton: conversationProvider.isSyncing || conversationProvider.syncCompleted
              ? const SizedBox()
              : ScaleTransition(
                  scale: _hideFabAnimation,
                  child: Container(
                    margin: const EdgeInsets.fromLTRB(32, 16, 32, 0),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                    decoration: BoxDecoration(
                      border: const GradientBoxBorder(
                        gradient: LinearGradient(colors: [Color.fromARGB(127, 208, 208, 208), Color.fromARGB(127, 188, 99, 121), Color.fromARGB(127, 86, 101, 182), Color.fromARGB(127, 126, 190, 236)]),
                        width: 2,
                      ),
                      borderRadius: BorderRadius.circular(12),
                      color: Colors.black,
                    ),
                    child: TextButton(
                      onPressed: () async {
                        if (context.read<ConnectivityProvider>().isConnected) {
                          // _toggleAnimation();
                          await conversationProvider.syncWals();
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
                      conversationProvider.isSyncing
                          ? Container(
                              padding: const EdgeInsets.all(12.0),
                              margin: const EdgeInsets.only(left: 16.0, right: 16.0, top: 12),
                              decoration: BoxDecoration(
                                color: const Color(0xFF1F1F25),
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
                        secondsToHumanReadable(conversationProvider.missingWalsInSeconds),
                        style: const TextStyle(color: Colors.white, fontSize: 30),
                      ),
                      const SizedBox(height: 12),
                      const Text('of conversations', style: TextStyle(color: Colors.white, fontSize: 18)),
                      const SizedBox(height: 20),
                      conversationProvider.isSyncing
                          ? conversationProvider.isFetchingConversations
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
                          : conversationProvider.syncCompleted && conversationProvider.syncedConversationsPointers.isNotEmpty
                              ? Column(
                                  children: [
                                    const Text(
                                      'Conversations Synced Successfully 🎉',
                                      style: TextStyle(color: Colors.white, fontSize: 16),
                                    ),
                                    const SizedBox(
                                      height: 18,
                                    ),
                                    (conversationProvider.syncedConversationsPointers.isNotEmpty)
                                        ? Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                                            decoration: BoxDecoration(
                                              border: const GradientBoxBorder(
                                                gradient: LinearGradient(colors: [Color.fromARGB(127, 208, 208, 208), Color.fromARGB(127, 188, 99, 121), Color.fromARGB(127, 86, 101, 182), Color.fromARGB(127, 126, 190, 236)]),
                                                width: 2,
                                              ),
                                              borderRadius: BorderRadius.circular(12),
                                            ),
                                            child: TextButton(
                                              onPressed: () {
                                                routeToPage(context, const SyncedConversationsPage());
                                              },
                                              child: const Text(
                                                'View Synced Conversations',
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
                const SliverToBoxAdapter(child: SizedBox(height: 30)),
                const SliverToBoxAdapter(child: DeviceAudioFilesWidget()),
                const SliverToBoxAdapter(child: SizedBox(height: 20)),
                const SliverToBoxAdapter(child: DownloadedFilesWidget()),
                const SliverToBoxAdapter(child: SizedBox(height: 20)),
                WalsListWidget(wals: conversationProvider.missingWals),
                const SliverToBoxAdapter(child: SizedBox(height: 50)),
              ],
            ),
          ),
        );
      }),
    );
  }
}

class DeviceAudioFilesWidget extends StatelessWidget {
  const DeviceAudioFilesWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<CaptureProvider>(
      builder: (context, captureProvider, child) {
        final fileNames = captureProvider.currentStorageFileNames;
        final isConnected = captureProvider.havingRecordingDevice;
        
        // Show connection status if not connected
        if (!isConnected) {
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Audio Files on Device',
                  style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFF1F1F25),
                    borderRadius: BorderRadius.circular(16.0),
                  ),
                  child: const ListTile(
                    leading: Icon(Icons.bluetooth_disabled, color: Colors.red),
                    title: Text(
                      'Device not connected',
                      style: TextStyle(color: Colors.white, fontSize: 16),
                    ),
                    subtitle: Text(
                      'Connect your device to view audio files',
                      style: TextStyle(color: Colors.grey, fontSize: 14),
                    ),
                  ),
                ),
                const SizedBox(height: 20),
              ],
            ),
          );
        }
        
        if (fileNames.isEmpty) {
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Audio Files on Device',
                  style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFF1F1F25),
                    borderRadius: BorderRadius.circular(16.0),
                  ),
                  child: ListTile(
                    leading: const Icon(Icons.folder_open, color: Colors.grey),
                    title: const Text(
                      'No audio files found',
                      style: TextStyle(color: Colors.white, fontSize: 16),
                    ),
                    subtitle: const Text(
                      'No chunk files detected on device storage',
                      style: TextStyle(color: Colors.grey, fontSize: 14),
                    ),
                    trailing: IconButton(
                      icon: const Icon(Icons.refresh, color: Colors.white),
                      onPressed: () {
                        captureProvider.updateStorageList();
                      },
                    ),
                  ),
                ),
                const SizedBox(height: 20),
              ],
            ),
          );
        }

        // Check if the list was truncated
        final isTruncated = fileNames.any((name) => name.contains('[TRUNCATED]'));
        final actualFiles = fileNames.where((name) => !name.contains('[TRUNCATED]')).toList();

        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Audio Files on Device',
                style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1F1F25),
                  borderRadius: BorderRadius.circular(16.0),
                ),
                child: Column(
                  children: [
                    ListTile(
                      leading: const Icon(Icons.storage, color: Colors.blue),
                      title: Text(
                        '${actualFiles.length}${isTruncated ? '+' : ''} chunk files found',
                        style: const TextStyle(color: Colors.white, fontSize: 16),
                      ),
                      subtitle: isTruncated ? const Text(
                        '⚠️ List truncated - too many files to display all',
                        style: TextStyle(color: Colors.orange, fontSize: 12),
                      ) : null,
                      trailing: IconButton(
                        icon: const Icon(Icons.refresh, color: Colors.white),
                        onPressed: () {
                          // Only refresh if device is connected
                          if (captureProvider.havingRecordingDevice) {
                            captureProvider.updateStorageList();
                          } else {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('Device must be connected to refresh file list'),
                                backgroundColor: Colors.orange,
                              ),
                            );
                          }
                        },
                      ),
                    ),
                    if (actualFiles.isNotEmpty) ...[
                      const Divider(color: Color(0xFF35343B), height: 1),
                      SizedBox(
                        height: 150,
                        child: ListView.builder(
                          itemCount: actualFiles.length,
                          itemBuilder: (context, index) {
                            final fileName = actualFiles[index];
                            final isChunkFile = fileName.contains('chunk_') && fileName.endsWith('.b');
                            final isInfoFile = fileName.endsWith('.info');
                            
                            return Consumer<CaptureProvider>(
                              builder: (context, captureProvider, child) {
                                final isDownloading = captureProvider.isDownloadingFile(fileName);
                                
                                return ListTile(
                                  leading: Icon(
                                    isChunkFile ? Icons.audio_file : 
                                    isInfoFile ? Icons.info_outline :
                                    Icons.insert_drive_file,
                                    color: isChunkFile ? Colors.orange : 
                                           isInfoFile ? Colors.blue :
                                           Colors.grey,
                                    size: 20
                                  ),
                                  title: Text(
                                    fileName,
                                    style: const TextStyle(color: Colors.white70, fontSize: 14),
                                  ),
                                  subtitle: isDownloading 
                                    ? const LinearProgressIndicator(
                                        valueColor: AlwaysStoppedAnimation<Color>(Colors.orange),
                                        backgroundColor: Colors.grey,
                                      )
                                    : null,
                                  trailing: isChunkFile 
                                    ? isDownloading 
                                      ? SizedBox(
                                          width: 80,
                                          child: Row(
                                            mainAxisSize: MainAxisSize.min,
                                            children: [
                                              Icon(Icons.hourglass_empty, color: Colors.orange, size: 18),
                                              SizedBox(width: 8),
                                              Text(
                                                '${(captureProvider.getDownloadProgress(fileName) * 100).toStringAsFixed(0)}%',
                                                style: const TextStyle(color: Colors.orange, fontSize: 12),
                                              ),
                                            ],
                                          ),
                                        )
                                      : Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            IconButton(
                                              icon: const Icon(Icons.download, color: Colors.blue, size: 18),
                                              onPressed: () {
                                                _showDownloadOptions(context, captureProvider, fileName);
                                              },
                                            ),
                                            IconButton(
                                              icon: const Icon(Icons.delete, color: Colors.red, size: 18),
                                              onPressed: () {
                                                _showDeleteConfirmation(context, captureProvider, fileName);
                                              },
                                            ),
                                          ],
                                        )
                                    : Text(
                                        '#${index + 1}',
                                        style: const TextStyle(color: Colors.grey, fontSize: 12),
                                      ),
                                );
                              },
                            );
                          },
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 20),
            ],
          ),
        );
      },
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

void _showDownloadOptions(BuildContext context, CaptureProvider captureProvider, String fileName) {
  showDialog(
    context: context,
    builder: (BuildContext context) {
      return AlertDialog(
        backgroundColor: const Color(0xFF1F1F25),
        title: const Text(
          'Download Options',
          style: TextStyle(color: Colors.white),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Choose download option for $fileName:',
              style: const TextStyle(color: Colors.white70),
            ),
            const SizedBox(height: 16),
            ListTile(
              leading: const Icon(Icons.download, color: Colors.blue),
              title: const Text(
                'Download Only',
                style: TextStyle(color: Colors.white),
              ),
              subtitle: const Text(
                'Keep file on device after download',
                style: TextStyle(color: Colors.white70, fontSize: 12),
              ),
              onTap: () {
                Navigator.of(context).pop();
                captureProvider.downloadChunkFile(fileName, deleteAfterDownload: false);
              },
            ),
            const Divider(color: Colors.grey),
            ListTile(
              leading: const Icon(Icons.download_done, color: Colors.green),
              title: const Text(
                'Download & Delete',
                style: TextStyle(color: Colors.white),
              ),
              subtitle: const Text(
                'Remove file from device after download',
                style: TextStyle(color: Colors.white70, fontSize: 12),
              ),
              onTap: () {
                Navigator.of(context).pop();
                captureProvider.downloadChunkFile(fileName, deleteAfterDownload: true);
              },
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
            },
            child: const Text(
              'Cancel',
              style: TextStyle(color: Colors.white70),
            ),
          ),
        ],
      );
    },
  );
}

void _showDeleteConfirmation(BuildContext context, CaptureProvider captureProvider, String fileName) {
  showDialog(
    context: context,
    builder: (BuildContext context) {
      return AlertDialog(
        backgroundColor: const Color(0xFF1F1F25),
        title: const Text(
          'Delete File',
          style: TextStyle(color: Colors.white),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.warning,
              color: Colors.orange,
              size: 48,
            ),
            const SizedBox(height: 16),
            Text(
              'Are you sure you want to delete $fileName from the device?',
              style: const TextStyle(color: Colors.white70),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            const Text(
              'This action cannot be undone.',
              style: TextStyle(color: Colors.red, fontSize: 12),
              textAlign: TextAlign.center,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
            },
            child: const Text(
              'Cancel',
              style: TextStyle(color: Colors.white70),
            ),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
              captureProvider.deleteFileFromDevice(fileName);
            },
            child: const Text(
              'Delete',
              style: TextStyle(color: Colors.red),
            ),
          ),
        ],
      );
    },
  );
}
