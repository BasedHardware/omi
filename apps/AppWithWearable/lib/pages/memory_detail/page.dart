import 'package:flutter/material.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/flutter_flow/flutter_flow_util.dart';
import 'package:friend_private/flutter_flow/flutter_flow_widgets.dart';
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
            title: const Text('Memory Detail'),
            leading: FFButtonWidget(
              onPressed: () async {
                context.pop();
              },
              text: '',
              icon: const Icon(
                Icons.arrow_back_rounded,
                size: 24.0,
              ),
              options: FFButtonOptions(
                width: 24.0,
                height: 24.0,
                padding: const EdgeInsetsDirectional.fromSTEB(8.0, 0.0, 0.0, 0.0),
                iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                color: const Color(0x1AF7F4F4),
                textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                      fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                      useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
                    ),
                elevation: 3.0,
                borderSide: const BorderSide(
                  color: Colors.transparent,
                  width: 1.0,
                ),
                borderRadius: BorderRadius.circular(24.0),
              ),
            ),
            centerTitle: true,
          ),
          body: Stack(
            children: [
              const BlurBotWidget(),
            ],
          ),
        ),
      ),
    );
  }
}
