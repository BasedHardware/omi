import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:provider/provider.dart';

class ConversationCapturingPage extends StatefulWidget {
  final String? topConversationId;

  const ConversationCapturingPage({
    super.key,
    this.topConversationId,
  });

  @override
  State<ConversationCapturingPage> createState() => _ConversationCapturingPageState();
}

class _ConversationCapturingPageState extends State<ConversationCapturingPage> with TickerProviderStateMixin {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  TabController? _controller;
  late bool showSummarizeConfirmation;
  Timer? _timer;
  int _elapsedTime = 0;

  @override
  void initState() {
    _controller = TabController(length: 2, vsync: this, initialIndex: 0);
    _controller!.addListener(() => setState(() {}));
    showSummarizeConfirmation = SharedPreferencesUtil().showSummarizeConfirmation;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final captureProvider = context.read<CaptureProvider>();
      if (captureProvider.segments.isNotEmpty) {
        if (captureProvider.inProgressConversation != null) {
          setState(() {
            _elapsedTime = convertDateTimeToSeconds(captureProvider.inProgressConversation!.createdAt);
          });
        }
        _startTimer();
      }
    });
    super.initState();
  }

  int convertDateTimeToSeconds(DateTime dateTime) {
    DateTime now = DateTime.now();
    Duration difference = now.difference(dateTime);

    return difference.inSeconds;
  }

  String convertToHHMMSS(int seconds) {
    int hours = seconds ~/ 3600;
    int minutes = (seconds % 3600) ~/ 60;
    int remainingSeconds = seconds % 60;

    String twoDigits(int n) => n.toString().padLeft(2, '0');

    return '${twoDigits(hours)}:${twoDigits(minutes)}:${twoDigits(remainingSeconds)}';
  }

  void _startTimer() {
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      setState(() {
        _elapsedTime++;
      });
    });
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
  dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<CaptureProvider, DeviceProvider>(
      builder: (context, provider, deviceProvider, child) {
        // Track memory
        // if ((provider.memoryProvider?.memories ?? []).isNotEmpty &&
        //     (provider.memoryProvider!.memories.first.id != widget.topMemoryId || widget.topMemoryId == null)) {
        //   _pushNewMemory(context, provider.memoryProvider!.memories.first);
        // }

        // Conversation source
        var conversationSource = ConversationSource.omi;
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
                  const Expanded(child: Text("In progress")),
                  if (SharedPreferencesUtil().devModeJoanFollowUpEnabled)
                    IconButton(
                      onPressed: () async {
                        getFollowUpQuestion().then((v) {
                          debugPrint('Follow up question: $v');
                        });
                      },
                      icon: const Icon(Icons.question_answer),
                    )
                ],
              ),
            ),
            body: Column(
              children: [
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: TabBarView(
                      controller: _controller,
                      physics: const NeverScrollableScrollPhysics(),
                      children: [
                        // Transcript tab
                        ListView(
                          shrinkWrap: true,
                          children: [
                            const SizedBox(height: 16),
                            provider.segments.isEmpty
                                ? Column(
                                    children: [
                                      const SizedBox(height: 80),
                                      Center(
                                        child: Text(
                                          conversationSource == ConversationSource.omi ? "No transcript" : "Empty",
                                        ),
                                      ),
                                    ],
                                  )
                                : getTranscriptWidget(
                                    false,
                                    provider.segments,
                                    [],
                                    deviceProvider.connectedDevice,
                                  ),
                            const SizedBox(height: 100), // Add space at bottom for the floating bar
                          ],
                        ),
                        // Summary tab
                        Padding(
                          padding: const EdgeInsets.only(top: 40),
                          child: ListView(
                            shrinkWrap: true,
                            children: [
                              const SizedBox(height: 80),
                              Center(
                                child: Padding(
                                  padding: const EdgeInsets.symmetric(horizontal: 32.0),
                                  child: Text(
                                    provider.segments.isEmpty
                                        ? "No summary"
                                        : "Conversation is summarized after 2 minutes of no speech 🤫",
                                    textAlign: TextAlign.center,
                                    style: TextStyle(fontSize: provider.segments.isEmpty ? 16 : 22),
                                  ),
                                ),
                              ),
                              const SizedBox(
                                height: 16,
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
            floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
            floatingActionButton: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                provider.segments.isEmpty
                    ? const SizedBox()
                    : AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        height: 30,
                        child: Text(
                          _elapsedTime > 0 ? convertToHHMMSS(_elapsedTime) : "",
                          style: const TextStyle(fontSize: 16, color: Colors.white),
                        ),
                      ),
                const SizedBox(height: 8),
                provider.segments.isEmpty
                    ? const SizedBox()
                    : ConversationBottomBar(
                        mode: ConversationBottomBarMode.recording,
                        selectedTabIndex: _controller!.index,
                        hasSegments: provider.segments.isNotEmpty,
                        onTabSelected: (index) {
                          _controller!.animateTo(index);
                          setState(() {});
                        },
                        onStopPressed: () {
                          if (provider.segments.isNotEmpty) {
                            if (!showSummarizeConfirmation) {
                              context.read<CaptureProvider>().forceProcessingCurrentConversation();
                              Navigator.of(context).pop();
                              return;
                            }
                            showDialog(
                              context: context,
                              builder: (context) {
                                return StatefulBuilder(
                                  builder: (context, setState) {
                                    return ConfirmationDialog(
                                      title: "Finished Conversation?",
                                      description: "Are you sure you want to stop recording and summarize the conversation now?",
                                      checkboxValue: !showSummarizeConfirmation,
                                      checkboxText: "Don't ask me again",
                                      onCheckboxChanged: (value) {
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
                                        SharedPreferencesUtil().showSummarizeConfirmation = showSummarizeConfirmation;
                                        context.read<CaptureProvider>().forceProcessingCurrentConversation();
                                        Navigator.of(context).pop();
                                        Navigator.of(context).pop();
                                      },
                                    );
                                  },
                                );
                              },
                            );
                          }
                        },
                      ),
              ],
            ),
          ),
        );
      },
    );
  }
}

String transcriptElapsedTime(String timepstamp) {
  timepstamp = timepstamp.split(' - ')[1];
  return timepstamp;
}
