import 'package:flutter/material.dart';

import '/flutter_flow/flutter_flow_util.dart';
import 'logo_main_model.dart';

export 'logo_main_model.dart';

class LogoMainWidget extends StatefulWidget {
  const LogoMainWidget({super.key});

  @override
  State<LogoMainWidget> createState() => _LogoMainWidgetState();
}

class _LogoMainWidgetState extends State<LogoMainWidget> {
  late LogoMainModel _model;

  @override
  void setState(VoidCallback callback) {
    super.setState(callback);
    _model.onUpdate();
  }

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => LogoMainModel());

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
      decoration: BoxDecoration(),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8.0),
        child: Image.asset(
          'assets/images/favicon.png',
          width: 60.0,
          height: 60.0,
          fit: BoxFit.contain,
        ),
      ),
    );
  }
}
