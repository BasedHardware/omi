import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';

class ProcessingConversationPage extends StatefulWidget {
  final ServerConversation conversation;

  const ProcessingConversationPage({
    super.key,
    required this.conversation,
  });

  @override
  State<ProcessingConversationPage> createState() => _ProcessingConversationPageState();
}

class _ProcessingConversationPageState extends State<ProcessingConversationPage> with TickerProviderStateMixin {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  TabController? _controller;

  @override
  void initState() {
    _controller = TabController(length: 2, vsync: this, initialIndex: 0);
    _controller!.addListener(() => setState(() {}));
    super.initState();
  }

  void _pushNewConversation(BuildContext context, conversation) async {
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (c) => ConversationDetailPage(
          conversation: conversation,
        ),
      ));
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(builder: (context, provider, child) {
      // Track memory // FIXME
      // if (widget.memory.status == ServerProcessingMemoryStatus.done &&
      //     provider.memories.firstWhereOrNull((e) => e.id == widget.memory.memoryId) != null) {
      //   _pushNewMemory(context, provider.memories.firstWhereOrNull((e) => e.id == widget.memory.memoryId));
      // }

      // Conversation source
      var convoSource = widget.conversation.source;
      bool hasPhotos = (widget.conversation.photos ?? []).isNotEmpty;

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
                Text(hasPhotos ? "📸" : "🎙️"),
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
                    text: convoSource == ConversationSource.openglass
                        ? 'Photos'
                        : convoSource == ConversationSource.screenpipe
                            ? 'Raw Data'
                            : 'Content',
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
                          if (widget.conversation.transcriptSegments.isNotEmpty ||
                              widget.conversation.photos.isNotEmpty)
                            getTranscriptWidget(
                                false, widget.conversation.transcriptSegments, widget.conversation.photos, null),
                          if (!hasPhotos && widget.conversation.transcriptSegments.isEmpty)
                            const Column(
                              children: [
                                SizedBox(height: 80),
                                Center(child: Text("No content to display")),
                              ],
                            ),
                          const SizedBox(height: 32),
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
                                widget.conversation.transcriptSegments.isEmpty ? "No summary" : "Processing",
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
