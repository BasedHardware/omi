import 'package:flutter/material.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/flutter_flow/flutter_flow_util.dart';
import 'package:friend_private/flutter_flow/flutter_flow_widgets.dart';
import 'package:friend_private/pages/memories/widgets/memory_operations.dart';
import 'package:friend_private/pages/memories/widgets/structured_memory.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';
import 'package:google_fonts/google_fonts.dart';

class MemoryDetailPage extends StatefulWidget {
  final dynamic memory;

  const MemoryDetailPage({super.key, this.memory});

  @override
  State<MemoryDetailPage> createState() => _MemoryDetailPageState();
}

class _MemoryDetailPageState extends State<MemoryDetailPage> {
  final scaffoldKey = GlobalKey<ScaffoldState>();
  final unFocusNode = FocusNode();

  late MemoryRecord memory;

  @override
  void initState() {
    memory = MemoryRecord.fromJson(widget.memory);
    debugPrint(memory.toString());
    super.initState();
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
          appBar: AppBar(
            automaticallyImplyLeading: false,
            backgroundColor: FlutterFlowTheme.of(context).primary,
            title: Row(
              mainAxisSize: MainAxisSize.max,
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                FFButtonWidget(
                  onPressed: () async {
                    context.safePop();
                  },
                  text: '',
                  icon: const Icon(
                    Icons.arrow_back_rounded,
                    size: 24.0,
                  ),
                  options: FFButtonOptions(
                    width: 44.0,
                    height: 44.0,
                    padding: const EdgeInsetsDirectional.fromSTEB(8.0, 0.0, 0.0, 0.0),
                    iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                    color: const Color(0x1AF7F4F4),
                    textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                          fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          useGoogleFonts:
                              GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
                        ),
                    elevation: 3.0,
                    borderSide: const BorderSide(
                      color: Colors.transparent,
                      width: 1.0,
                    ),
                    borderRadius: BorderRadius.circular(24.0),
                  ),
                ),
                const Text('Memory Detail'),
                getDeleteMemoryOperationWidget(memory, unFocusNode, setState,
                    iconSize: 24, onDelete: () => Navigator.pop(context))
              ],
            ),
          ),
          body: Stack(
            children: [
              const BlurBotWidget(),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16.0),
                child: ListView(
                  children: [
                    const SizedBox(height: 32),
                    Padding(
                      padding: const EdgeInsets.only(left: 4.0),
                      child: Text(dateTimeFormat('MMM d, h:mm a', memory.date),
                          style: FlutterFlowTheme.of(context).titleMedium),
                    ),
                    const SizedBox(height: 24),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Padding(
                          padding: const EdgeInsets.only(left: 4.0),
                          child: Text('Structured Memory:', style: FlutterFlowTheme.of(context).titleMedium),
                        ),
                        Container(
                          padding: const EdgeInsetsDirectional.symmetric(horizontal: 12, vertical: 8),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              geyShareMemoryOperationWidget(memory, iconSize: 22),
                              const SizedBox(width: 16),
                              getEditMemoryOperationWidget(memory, unFocusNode, setState, iconSize: 22,
                                  onMemoryEdited: (String updated) {
                                debugPrint('onMemoryEdited $updated');
                                setState(() {
                                  memory.structuredMemory = updated;
                                });
                              }),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    Container(
                      padding: const EdgeInsetsDirectional.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: const Color(0x1AF7F4F4),
                        borderRadius: BorderRadius.circular(24.0),
                      ),
                      child: getStructuredMemoryWidget(context, memory, includePadding: false),
                    ),
                    const SizedBox(height: 32),
                    Padding(
                      padding: const EdgeInsets.only(left: 4.0),
                      child: Text('Raw Transcript:', style: FlutterFlowTheme.of(context).titleMedium),
                    ),
                    const SizedBox(height: 16),
                    Container(
                      padding: const EdgeInsetsDirectional.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: const Color(0x1AF7F4F4),
                        borderRadius: BorderRadius.circular(24.0),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.only(top: 4.0),
                        child: Text(
                          memory.rawMemory,
                          style: FlutterFlowTheme.of(context).bodyMedium.override(
                                fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                                useGoogleFonts:
                                    GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
                                lineHeight: 1.5,
                              ),
                        ),
                      ),
                    ),
                  ],
                ),
              )
            ],
          ),
        ),
      ),
    );
  }
}
