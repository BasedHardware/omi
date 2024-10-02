import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/pages/memory_detail/page.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/widgets/confirmation_dialog.dart';
import 'package:gradient_borders/box_borders/gradient_box_border.dart';
import 'package:provider/provider.dart';
import 'package:friend_private/services/translation_service.dart';

class MemoryCapturingPage extends StatefulWidget {
  final String? topMemoryId;

  const MemoryCapturingPage({
    super.key,
    this.topMemoryId,
  });

  @override
  State<MemoryCapturingPage> createState() => _MemoryCapturingPageState();
}

class _MemoryCapturingPageState extends State<MemoryCapturingPage> with TickerProviderStateMixin {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  TabController? _controller;
  late bool showSummarizeConfirmation;

  @override
  void initState() {
    _controller = TabController(length: 2, vsync: this, initialIndex: 0);
    _controller!.addListener(() => setState(() {}));
    showSummarizeConfirmation = SharedPreferencesUtil().showSummarizeConfirmation;
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
      // var captureProvider = context.read<CaptureProvider>();
      // if (captureProvider.isGlasses) {
      //   memorySource = MemorySource.openglass;
      // }
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
                 Expanded(child: Text(TranslationService.translate( "In progress"))),
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
                        ? TranslationService.translate( 'Photos')
                        : memorySource == MemorySource.screenpipe
                            ? TranslationService.translate( 'Raw Data')
                            : TranslationService.translate( 'Transcript'),
                  ),
                   Tab(text: TranslationService.translate( 'Summary'))
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
                          provider.segments.isEmpty
                              ? Column(
                                  children: [
                                    const SizedBox(height: 80),
                                    Center(
                                        child: Text(memorySource == MemorySource.friend ? TranslationService.translate( "No transcript") : TranslationService.translate( "Empty"))),
                                  ],
                                )
                              : getTranscriptWidget(
                                  provider.memoryCreating,
                                  provider.segments,
                                  [],
                                  deviceProvider.connectedDevice,
                                )
                        ],
                      ),
                      Padding(
                        padding: const EdgeInsets.only(top: 140),
                        child: ListView(
                          shrinkWrap: true,
                          children: [
                            const SizedBox(height: 80),
                            Center(
                              child: Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 32.0),
                                child: Text(
                                  provider.segments.isEmpty
                                      ? TranslationService.translate( "No summary")
                                      : TranslationService.translate( "We summarize conversations 2 minutes after they end\n\nWant to end it now?"),
                                  textAlign: TextAlign.center,
                                  style: const TextStyle(fontSize: 16),
                                ),
                              ),
                            ),
                            const SizedBox(
                              height: 16,
                            ),
                            provider.segments.isEmpty
                                ? const SizedBox()
                                : Container(
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
                                    margin: const EdgeInsets.symmetric(horizontal: 48),
                                    child: MaterialButton(
                                      onPressed: () async {
                                        print(showSummarizeConfirmation);
                                        if (!showSummarizeConfirmation) {
                                          context.read<CaptureProvider>().createMemory();
                                          return;
                                        }
                                        showDialog(
                                            context: context,
                                            builder: (context) {
                                              return StatefulBuilder(builder: (context, setState) {
                                                return ConfirmationDialog(
                                                  title: TranslationService.translate( "Stop Recording?"),
                                                  description:
                                                TranslationService.translate( "Are you sure you want to stop recording and summarise the conversation now?"),
                                                  checkboxValue: !showSummarizeConfirmation,
                                                  checkboxText: "Don't ask me again",
                                                  updateCheckboxValue: (value) {
                                                    if (value != null) {
                                                      setState(() {
                                                        showSummarizeConfirmation = !value;
                                                      });
                                                    }
                                                  },
                                                  onCancel: () {
                                                    Navigator.of(context).pop();
                                                  },
                                                  onConfirm: () {
                                                    SharedPreferencesUtil().showSummarizeConfirmation =
                                                        showSummarizeConfirmation;
                                                    context.read<CaptureProvider>().createMemory();
                                                    Navigator.of(context).pop();
                                                  },
                                                );
                                              });
                                            });
                                      },
                                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                      child: const Padding(
                                        padding: EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                                        child: Text(
                                          'Stop Recording',
                                          style: TextStyle(
                                            color: Colors.white,
                                            fontSize: 16,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                          ],
                        ),
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
