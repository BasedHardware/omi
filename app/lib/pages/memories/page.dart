import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/capture/location_service.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/pages/memories/widgets/date_list_item.dart';
import 'package:friend_private/pages/memories/widgets/processing_capture.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:geolocator/geolocator.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:location/location.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'widgets/empty_memories.dart';
import 'widgets/memory_list_item.dart';

class MemoriesPage extends StatefulWidget {
  const MemoriesPage({super.key});

  @override
  State<MemoriesPage> createState() => _MemoriesPageState();
}

class _MemoriesPageState extends State<MemoriesPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (Provider.of<MemoryProvider>(context, listen: false).memories.isEmpty) {
        await Provider.of<MemoryProvider>(context, listen: false).getInitialMemories();
      }
      if (await LocationService().displayPermissionsDialog()) {
        await showDialog(
          context: context,
          builder: (c) => getDialog(
            context,
            () => Navigator.of(context).pop(),
            () async {
              await LocationService().enableService();
              if (await LocationService().isServiceEnabled()) {
                var res = await Geolocator.requestPermission();
                print('Location permission: $res');
                if (res == LocationPermission.whileInUse) {
                  await Geolocator.openAppSettings();
                } else if (res != LocationPermission.always && res != LocationPermission.whileInUse) {
                  debugPrint('Location permission denied forever');
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text(
                          'If you change your mind, you can change location permission in your device settings.',
                          style: TextStyle(color: Colors.white, fontSize: 14),
                        ),
                      ),
                    );
                  }
                }
                SharedPreferencesUtil().locationEnabled = res == LocationPermission.always;
                MixpanelManager().setUserProperty('Location Enabled', SharedPreferencesUtil().locationEnabled);
              }
              if (mounted) Navigator.of(context).pop();
            },
            'Enable Location?  🌍',
            'Allow location access to tag your memories. Set to "Always Allow" in Settings',
            singleButton: false,
            okButtonText: 'Continue',
          ),
        );
      }
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    print('building memories page');
    super.build(context);
    return Consumer<MemoryProvider>(builder: (context, memoryProvider, child) {
      return RefreshIndicator(
        backgroundColor: Colors.black,
        color: Colors.white,
        onRefresh: () async {
          return await memoryProvider.getInitialMemories();
        },
        child: CustomScrollView(
          slivers: [
            const SliverToBoxAdapter(child: SizedBox(height: 32)),
            SliverToBoxAdapter(child: speechProfileWidget(context)),
            SliverToBoxAdapter(child: getMemoryCaptureWidget()),
            if (memoryProvider.memoriesWithDates.isEmpty && !memoryProvider.isLoadingMemories)
              const SliverToBoxAdapter(
                child: Center(
                  child: Padding(
                    padding: EdgeInsets.only(top: 32.0),
                    child: EmptyMemoriesWidget(),
                  ),
                ),
              )
            else if (memoryProvider.memoriesWithDates.isEmpty && memoryProvider.isLoadingMemories)
              const SliverToBoxAdapter(
                child: Center(
                  child: Padding(
                    padding: EdgeInsets.only(top: 32.0),
                    child: CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                    ),
                  ),
                ),
              )
            else
              SliverList(
                delegate: SliverChildBuilderDelegate(
                  (context, index) {
                    if (index == memoryProvider.memoriesWithDates.length) {
                      if (memoryProvider.isLoadingMemories) {
                        return const Center(
                          child: Padding(
                            padding: EdgeInsets.only(top: 32.0),
                            child: CircularProgressIndicator(
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          ),
                        );
                      }
                      // widget.loadMoreMemories(); // CALL this only when visible
                      return VisibilityDetector(
                        key: const Key('memory-loader'),
                        onVisibilityChanged: (visibilityInfo) {
                          if (visibilityInfo.visibleFraction > 0 && !memoryProvider.isLoadingMemories) {
                            memoryProvider.getMoreMemoriesFromServer();
                          }
                        },
                        child: const SizedBox(height: 80, width: double.maxFinite),
                      );
                    }

                    if (memoryProvider.memoriesWithDates[index].runtimeType == DateTime) {
                      return DateListItem(
                          date: memoryProvider.memoriesWithDates[index] as DateTime, isFirst: index == 0);
                    }
                    var memory = memoryProvider.memoriesWithDates[index] as ServerMemory;
                    return MemoryListItem(
                      memoryIdx: memoryProvider.memoriesWithDates.indexOf(memory),
                      memory: memory,
                    );
                  },
                  childCount: memoryProvider.memoriesWithDates.length + 1,
                ),
              ),
            const SliverToBoxAdapter(
              child: SizedBox(height: 80),
            ),
          ],
        ),
      );
    });
  }
}
