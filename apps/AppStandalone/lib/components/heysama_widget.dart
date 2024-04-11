import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'heysama_model.dart';
export 'heysama_model.dart';

class HeysamaWidget extends StatefulWidget {
  const HeysamaWidget({super.key});

  @override
  State<HeysamaWidget> createState() => _HeysamaWidgetState();
}

class _HeysamaWidgetState extends State<HeysamaWidget> {
  late HeysamaModel _model;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => HeysamaModel());

    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  void dispose() {
    _model.maybeDispose();

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: MediaQuery.sizeOf(context).width * 0.746,
      height: 40.0,
      decoration: BoxDecoration(
        color: FlutterFlowTheme.of(context).primary,
        borderRadius: BorderRadius.circular(10.0),
        border: Border.all(
          color: const Color(0xFFC169EF),
          width: 0.4,
        ),
      ),
      child: Align(
        alignment: const AlignmentDirectional(0.0, 0.0),
        child: Text(
          'Say \"Hey Sama\" and ask any question!',
          textAlign: TextAlign.center,
          style: FlutterFlowTheme.of(context).bodyMedium.override(
                fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                color: const Color(0xFFC169EF),
                fontSize: 16.0,
                fontWeight: FontWeight.w500,
                useGoogleFonts: GoogleFonts.asMap()
                    .containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
              ),
        ),
      ),
    );
  }
}
