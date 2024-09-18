import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/widgets/transcript.dart';

class CompareTranscriptsPage extends StatefulWidget {
  final ServerMemory memory;

  const CompareTranscriptsPage({super.key, required this.memory});

  @override
  State<CompareTranscriptsPage> createState() => _CompareTranscriptsPageState();
}

class _CompareTranscriptsPageState extends State<CompareTranscriptsPage> {
  int _selectedTab = 0;
  TranscriptsResponse? transcripts;

  @override
  void initState() {
    getMemoryTranscripts(widget.memory.id).then((result) {
      setState(() {
        transcripts = result;
      });
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        title: const Text('Compare Transcripts'),
        backgroundColor: Theme.of(context).colorScheme.primary,
      ),
      body: DefaultTabController(
        length: 3,
        initialIndex: 0,
        child: Column(
          children: [
            TabBar(
              indicatorSize: TabBarIndicatorSize.label,
              isScrollable: false,
              onTap: (value) {
                setState(() {
                  _selectedTab = value;
                });
              },
              padding: EdgeInsets.zero,
              indicatorPadding: EdgeInsets.zero,
              labelStyle: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 18),
              tabs: const [Tab(text: 'Deepgram'), Tab(text: 'Soniox'), Tab(text: 'Whisper-x')],
              indicator: BoxDecoration(color: Colors.transparent, borderRadius: BorderRadius.circular(16)),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Builder(builder: (context) {
                  return TabBarView(
                    physics: const NeverScrollableScrollPhysics(),
                    children: [
                      ListView(
                        shrinkWrap: true,
                        children: [
                          TranscriptWidget(
                            segments: transcripts?.deepgram ?? [],
                            horizontalMargin: false,
                            topMargin: false,
                            canDisplaySeconds: true,
                            isMemoryDetail: true,
                          )
                        ],
                      ),
                      ListView(
                        shrinkWrap: true,
                        children: [
                          TranscriptWidget(
                            segments: transcripts?.soniox ?? [],
                            horizontalMargin: false,
                            topMargin: false,
                            canDisplaySeconds: true,
                            isMemoryDetail: true,
                          )
                        ],
                      ),
                      ListView(
                        shrinkWrap: true,
                        children: [
                          const SizedBox(height: 16),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 4),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.start,
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Text(
                                  'Status',
                                  style: Theme.of(context)
                                      .textTheme
                                      .titleLarge!
                                      .copyWith(fontSize: 18, fontWeight: FontWeight.bold),
                                ),
                                const SizedBox(width: 24),
                                Text(
                                  widget.memory.postprocessing?.status.toString().split('.')[1].toUpperCase() ??
                                      'UNKNOWN',
                                  style: const TextStyle(fontSize: 16, decoration: TextDecoration.underline),
                                ),
                              ],
                            ),
                          ),
                          widget.memory.postprocessing?.failReason != null
                              ? const SizedBox(height: 8)
                              : const SizedBox(height: 0),
                          widget.memory.postprocessing?.failReason != null
                              ? Padding(
                                  padding: const EdgeInsets.symmetric(horizontal: 4),
                                  child: Text(widget.memory.postprocessing?.failReason ?? ''),
                                )
                              : const SizedBox(height: 0),
                          widget.memory.postprocessing?.failReason != null
                              ? const SizedBox(height: 16)
                              : const SizedBox(height: 0),
                          TranscriptWidget(
                            segments: transcripts?.whisperx ?? [],
                            horizontalMargin: false,
                            topMargin: false,
                            canDisplaySeconds: true,
                            isMemoryDetail: true,
                          )
                        ],
                      )
                    ],
                  );
                }),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
