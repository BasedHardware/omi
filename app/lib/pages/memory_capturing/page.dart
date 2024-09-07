import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/pages/memory_detail/page.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:provider/provider.dart';

class MemoryCapturingPage extends StatefulWidget {
  String? topMemoryId;
  MemoryCapturingPage({
    super.key,
    this.topMemoryId,
  });

  @override
  State<MemoryCapturingPage> createState() => _MemoryCapturingPageState();
}

class _MemoryCapturingPageState extends State<MemoryCapturingPage> with TickerProviderStateMixin {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  TabController? _controller;

  @override
  void initState() {
    _controller = TabController(length: 2, vsync: this, initialIndex: 0);
    _controller!.addListener(() => setState(() {}));
    super.initState();
  }

  void _pushNewMemory(BuildContext context, memory) async {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (c) => MemoryDetailPage(
          memory: memory,
        ),
      ));
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(builder: (context, provider, deviceProvider, child) {
      // Track memory
      if ((provider.memoryProvider?.memories ?? []).isNotEmpty &&
          (provider.memoryProvider!.memories.first.id != widget.topMemoryId || widget.topMemoryId == null)) {
        _pushNewMemory(context, provider.memoryProvider!.memories.first);
      }

      // Memory source
      var memorySource = MemorySource.friend;
      var captureProvider = context.read<CaptureProvider>();
      if (captureProvider.isGlasses) {
        memorySource = MemorySource.openglass;
      }
      return PopScope(
        canPop: true,
        child: Scaffold(
          key: scaffoldKey,
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            automaticallyImplyLeading: false,
            backgroundColor: Theme.of(context).colorScheme.primary,
            title: Row(
              mainAxisSize: MainAxisSize.max,
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                IconButton(
                  onPressed: () {
                    Navigator.pop(context);
                    return;
                  },
                  icon: const Icon(Icons.arrow_back_rounded, size: 24.0),
                ),
                const SizedBox(width: 4),
                const Text("🎙️"),
                const SizedBox(width: 4),
                Expanded(child: const Text("Live")),
              ],
            ),
          ),
          body: Column(
            children: [
              TabBar(
                indicatorSize: TabBarIndicatorSize.label,
                isScrollable: false,
                padding: EdgeInsets.zero,
                indicatorPadding: EdgeInsets.zero,
                controller: _controller,
                labelStyle: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 18),
                tabs: [
                  Tab(
                    text: memorySource == MemorySource.openglass
                        ? 'Photos'
                        : memorySource == MemorySource.screenpipe
                            ? 'Raw Data'
                            : 'Transcript',
                  ),
                  const Tab(text: 'Summary')
                ],
                indicator: BoxDecoration(color: Colors.transparent, borderRadius: BorderRadius.circular(16)),
              ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: TabBarView(
                    controller: _controller,
                    physics: const NeverScrollableScrollPhysics(),
                    children: [
                      ListView(
                        shrinkWrap: true,
                        children: [
                          provider.segments.isEmpty && provider.photos.isEmpty
                              ? Column(
                                  children: [
                                    const SizedBox(height: 80),
                                    Center(
                                        child: Text(memorySource == MemorySource.friend ? "No transcript" : "Empty")),
                                  ],
                                )
                              : getTranscriptWidget(provider.memoryCreating, provider.segments, provider.photos,
                                  deviceProvider.connectedDevice)
                        ],
                      ),
                      ListView(
                        shrinkWrap: true,
                        children: [
                          const SizedBox(height: 80),
                          Center(child: Text(provider.segments.isEmpty ? "No summary" : "Processing")),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    });
  }
}
