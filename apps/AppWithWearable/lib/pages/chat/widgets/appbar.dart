import 'package:flutter/material.dart';
import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/flutter_flow/flutter_flow_widgets.dart';
import 'package:google_fonts/google_fonts.dart';

getChatAppBar(BuildContext context) {
  return AppBar(
    backgroundColor: FlutterFlowTheme.of(context).primary,
    automaticallyImplyLeading: false,
    title: const Text('Chat'),
    centerTitle: true,
    elevation: 2.0,
  );
}
