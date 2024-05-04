import 'package:flutter/material.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'blur_bot_model.dart';
export 'blur_bot_model.dart';
import 'package:lottie/lottie.dart';


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
      decoration: BoxDecoration(
        image: DecorationImage(
          image: AssetImage('assets/images/background.png'),
          fit: BoxFit.cover,
        ),
      ),
    );
  }
}