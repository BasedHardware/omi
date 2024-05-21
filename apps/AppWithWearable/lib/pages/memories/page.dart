import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/pages/memories/widgets/summaries_buttons.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'widgets/empty_memories.dart';
import 'widgets/header_buttons.dart';
import 'widgets/memory_list_item.dart';
import 'widgets/memory_processing.dart';

class MemoriesPage extends StatefulWidget {
  final List<MemoryRecord> memories;
  final Function refreshMemories;

  const MemoriesPage({super.key, required this.memories, required this.refreshMemories});

  @override
  State<MemoriesPage> createState() => _MemoriesPageState();
}

class _MemoriesPageState extends State<MemoriesPage> {
  String? dailySummary;
  String? weeklySummary;
  String? monthlySummary;
  late AudioPlayer _audioPlayer;

  final scaffoldKey = GlobalKey<ScaffoldState>();
  final unFocusNode = FocusNode();

  _dailySummary() async {
    List<MemoryRecord> memories = await MemoryStorage.getMemoriesByDay(DateTime.now());
    dailySummary = memories.isNotEmpty ? (await requestSummary(memories)) : null;
  }

  _weeklySummary() async {
    List<MemoryRecord> memories = await MemoryStorage.getMemoriesOfLastWeek();
    weeklySummary = memories.isNotEmpty ? (await requestSummary(memories)) : null;
  }

  _monthlySummary() async {
    List<MemoryRecord> memories = await MemoryStorage.getMemoriesOfLastMonth();
    monthlySummary = memories.isNotEmpty ? (await requestSummary(memories)) : null;
  }

  void _resetMemoriesState(String? memoryId) {
    // FIXME implement
  }

  void _playAudio(MemoryRecord memory) async {
    if (memory.audioFileName == null) return;
    String fileName = memory.audioFileName!;
    File? gcpFile = await downloadFile(fileName, fileName);
    if (gcpFile == null) {
      // show dialog
      showDialog(
          context: context,
          builder: (_) => const AlertDialog(
                title: Text('Error'),
                content: Text(
                    'Failed to retrieve the audio file, please check your credentials and GCP bucket settings are set.'),
              ));
      return;
    }
    _audioPlayer.play(DeviceFileSource(gcpFile.path ?? ''));
    debugPrint('Duration: ${(await _audioPlayer.getDuration())?.inSeconds} seconds');
    _resetMemoriesState(memory.id);
  }

  void _pauseAudio(MemoryRecord memory) async {
    if (memory.audioFileName == null) return;
    await _audioPlayer.pause();
    setState(() {
      memory.playerState = PlayerState.paused;
    });
  }

  void _resumeAudio(MemoryRecord memory) async {
    if (memory.audioFileName == null) return;
    await _audioPlayer.resume();
    setState(() {
      memory.playerState = PlayerState.playing;
    });
  }

  void _stopAudio(MemoryRecord memory) async {
    if (memory.audioFileName == null) return;
    await _audioPlayer.stop();
    setState(() {
      memory.playerState = PlayerState.stopped;
    });
  }

  @override
  void initState() {
    super.initState();
    _dailySummary();
    _weeklySummary();
    _monthlySummary();
    _audioPlayer = AudioPlayer();
    _audioPlayer.onPlayerComplete.listen((event) {
      _resetMemoriesState(null);
    });
  }

  @override
  void dispose() {
    _audioPlayer.stop();
    _audioPlayer.dispose();
    unFocusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Builder(
      builder: (context) => GestureDetector(
        onTap: () => unFocusNode.canRequestFocus
            ? FocusScope.of(context).requestFocus(unFocusNode)
            : FocusScope.of(context).unfocus(),
        child: Scaffold(
          key: scaffoldKey,
          backgroundColor: FlutterFlowTheme.of(context).primary,
          body: Stack(
            children: [
              const BlurBotWidget(),
              ListView(
                children: [
                  const SizedBox(height: 16),
                  HomePageSummariesButtons(
                    unFocusNode: unFocusNode,
                    dailySummary: dailySummary,
                    weeklySummary: weeklySummary,
                    monthlySummary: monthlySummary,
                  ),
                  const SizedBox(height: 8),
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: (widget.memories.isEmpty)
                        ? const Center(
                            child: Padding(
                              padding: EdgeInsets.only(top: 32.0),
                              child: EmptyMemoriesWidget(),
                            ),
                          )
                        : ListView.builder(
                            itemCount: widget.memories.length,
                            primary: false,
                            shrinkWrap: true,
                            scrollDirection: Axis.vertical,
                            itemBuilder: (context, index) {
                              if (widget.memories[index].rawMemory == 'in_progress') {
                                return const MemoryProcessing();
                              }
                              return MemoryListItem(
                                memory: widget.memories[index],
                                unFocusNode: unFocusNode,
                                playAudio: _playAudio,
                                pauseAudio: _pauseAudio,
                                resumeAudio: _resumeAudio,
                                stopAudio: _stopAudio,
                                loadMemories: widget.refreshMemories,
                              );
                            },
                          ),
                  ),
                ],
              )
            ],
          ),
        ),
      ),
    );
  }
}
