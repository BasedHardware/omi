import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/pages/ble/blur_bot/blur_bot_widget.dart';
import 'package:friend_private/pages/memories/widgets/summaries_buttons.dart';

import '/flutter_flow/flutter_flow_util.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'widgets/empty_memories.dart';
import 'widgets/header_buttons.dart';
import 'model.dart';
import 'widgets/memory_list_item.dart';
import 'widgets/memory_processing.dart';

class MemoriesPage extends StatefulWidget {
  const MemoriesPage({super.key});

  @override
  State<MemoriesPage> createState() => _MemoriesPageState();
}

class _MemoriesPageState extends State<MemoriesPage> {
  late MemoriesPageModel _model;
  String? dailySummary;
  String? weeklySummary;
  String? monthlySummary;
  late AudioPlayer _audioPlayer;

  final scaffoldKey = GlobalKey<ScaffoldState>();

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
    var memories = FFAppState().memories;
    for (var m in memories) {
      if (m.id == memory.id) {
        m.playerState = PlayerState.playing;
      } else {
        m.playerState = PlayerState.stopped;
      }
    }
    FFAppState().update(() {
      FFAppState().memories = memories;
    });
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
    _model = createModel(context, () => MemoriesPageModel());
    _dailySummary();
    _weeklySummary();
    _monthlySummary();
    _audioPlayer = AudioPlayer();
  }

  @override
  void dispose() {
    _model.dispose();
    _audioPlayer.stop();
    _audioPlayer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    context.watch<FFAppState>();

    return Builder(
      builder: (context) => GestureDetector(
        onTap: () => _model.unfocusNode.canRequestFocus
            ? FocusScope.of(context).requestFocus(_model.unfocusNode)
            : FocusScope.of(context).unfocus(),
        child: Scaffold(
          key: scaffoldKey,
          backgroundColor: FlutterFlowTheme.of(context).primary,
          appBar: AppBar(
            automaticallyImplyLeading: false,
            backgroundColor: FlutterFlowTheme.of(context).primary,
            title: const HomePageHeaderButtons(),
            centerTitle: true,
          ),
          body: SafeArea(
            top: true,
            child: SizedBox(
                height: MediaQuery.sizeOf(context).height * 1.0,
                child: Stack(
                  children: [
                    const Align(
                      alignment: AlignmentDirectional(0.0, 0.0),
                      child: BlurBotWidget(),
                    ),
                    ListView(
                      children: [
                        const SizedBox(height: 16),
                        HomePageSummariesButtons(
                          model: _model,
                          dailySummary: dailySummary,
                          weeklySummary: weeklySummary,
                          monthlySummary: monthlySummary,
                        ),
                        const SizedBox(height: 8),
                        if (FFAppState().memoryCreationProcessing) const MemoryProcessing(),
                        Padding(
                          padding: const EdgeInsets.all(16),
                          child: (FFAppState().memories.isEmpty && !FFAppState().memoryCreationProcessing)
                              ? const Center(
                                  child: Padding(
                                    padding: EdgeInsets.only(top: 32.0),
                                    child: EmptyMemoriesWidget(),
                                  ),
                                )
                              : ListView.builder(
                                  padding: EdgeInsets.zero,
                                  primary: false,
                                  shrinkWrap: true,
                                  scrollDirection: Axis.vertical,
                                  itemCount: FFAppState().memories.length,
                                  itemBuilder: (context, index) {
                                    return MemoryListItem(
                                      memory: FFAppState().memories[index],
                                      model: _model,
                                      playAudio: _playAudio,
                                      pauseAudio: _pauseAudio,
                                      resumeAudio: _resumeAudio,
                                      stopAudio: _stopAudio,
                                    );
                                  },
                                ),
                        ),
                      ],
                    )
                  ],
                )),
          ),
        ),
      ),
    );
  }
}
