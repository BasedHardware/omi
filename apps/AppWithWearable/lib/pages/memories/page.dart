import 'package:friend_private/backend/api_requests/api_calls.dart';
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

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => MemoriesPageModel());
    _dailySummary();
    _weeklySummary();
    _monthlySummary();
    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  void dispose() {
    _model.dispose();
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
                    SingleChildScrollView(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
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
                            padding: const EdgeInsetsDirectional.fromSTEB(16.0, 4.0, 16.0, 0.0),
                            child: Container(
                              width: double.infinity,
                              height: MediaQuery.sizeOf(context).height * 0.9,
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(12.0),
                                shape: BoxShape.rectangle,
                                border: Border.all(
                                  color: const Color(0x00E0E3E7),
                                ),
                              ),
                              child: (FFAppState().memories.isEmpty && !FFAppState().memoryCreationProcessing)
                                  ? Center(
                                      child: SizedBox(
                                        width: MediaQuery.sizeOf(context).width * 1.0,
                                        height: MediaQuery.sizeOf(context).height * 0.4,
                                        child: const EmptyMemoriesWidget(),
                                      ),
                                    )
                                  : ListView.builder(
                                      padding: EdgeInsets.zero,
                                      primary: false,
                                      shrinkWrap: true,
                                      scrollDirection: Axis.vertical,
                                      itemCount: FFAppState().memories.length,
                                      itemBuilder: (context, index) {
                                        return MemoryListItem(memory: FFAppState().memories[index], model: _model);
                                      },
                                    ),
                            ),
                          ),
                        ],
                      ),
                    )
                  ],
                )),
          ),
        ),
      ),
    );
  }
}
