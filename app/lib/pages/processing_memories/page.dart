import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/pages/memory_detail/page.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:provider/provider.dart';

class ProcessingMemoryPage extends StatefulWidget {
  final ServerMemory memory;

  const ProcessingMemoryPage({
    super.key,
    required this.memory,
  });

  @override
  State<ProcessingMemoryPage> createState() => _ProcessingMemoryPageState();
}

class _ProcessingMemoryPageState extends State<ProcessingMemoryPage> with TickerProviderStateMixin {
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
    return Consumer<MemoryProvider>(builder: (context, provider, child) {
      // Track memory // FIXME
      // if (widget.memory.status == ServerProcessingMemoryStatus.done &&
      //     provider.memories.firstWhereOrNull((e) => e.id == widget.memory.memoryId) != null) {
      //   _pushNewMemory(context, provider.memories.firstWhereOrNull((e) => e.id == widget.memory.memoryId));
      // }

      // Memory source
      var memorySource = MemorySource.friend;
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
                const Expanded(child: Text("In progress")),
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
                          widget.memory.transcriptSegments.isEmpty
                              ? const Column(
                                  children: [
                                    SizedBox(height: 80),
                                    Center(child: Text("No Transcript")),
                                  ],
                                )
                              : getTranscriptWidget(false, widget.memory.transcriptSegments, [], null)
                        ],
                      ),
                      ListView(
                        shrinkWrap: true,
                        children: [
                          const SizedBox(height: 80),
                          Center(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 16.0),
                              child: Text(
                                widget.memory.transcriptSegments.isEmpty ? "No summary" : "Processing",
                                textAlign: TextAlign.center,
                                style: const TextStyle(fontSize: 16),
                              ),
                            ),
                          ),
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
