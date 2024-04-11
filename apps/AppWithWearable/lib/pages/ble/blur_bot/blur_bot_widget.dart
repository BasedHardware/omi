import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'blur_bot_model.dart';
export 'blur_bot_model.dart';

class BlurBotWidget extends StatefulWidget {
  const BlurBotWidget({super.key});

  @override
  State<BlurBotWidget> createState() => _BlurBotWidgetState();
}

class _BlurBotWidgetState extends State<BlurBotWidget> {
  late BlurBotModel _model;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => BlurBotModel());

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
      width: double.infinity,
      height: double.infinity,
      decoration: BoxDecoration(),
      child: ClipRect(
        child: ImageFiltered(
          imageFilter: ImageFilter.blur(
            sigmaX: 48.0,
            sigmaY: 48.0,
          ),
          child: Container(
            width: double.infinity,
            height: double.infinity,
            decoration: BoxDecoration(
              color: FlutterFlowTheme.of(context).primary,
            ),
            child: Container(
              width: double.infinity,
              height: double.infinity,
              child: Stack(
                alignment: AlignmentDirectional(0.0, 0.0),
                children: [
                  Align(
                    alignment: AlignmentDirectional(1.0, 1.0),
                    child: Container(
                      width: 240.0,
                      height: 240.0,
                      decoration: BoxDecoration(
                        color: Color(0xFFFE480D),
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                  Align(
                    alignment: AlignmentDirectional(-1.0, 1.0),
                    child: Padding(
                      padding:
                          EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 40.0),
                      child: Container(
                        width: 200.0,
                        height: 200.0,
                        decoration: BoxDecoration(
                          color: Color(0xFF97ADAA),
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
