import 'package:flutter/material.dart';


class BlurBotWidget extends StatefulWidget {
  const BlurBotWidget({super.key});

  @override
  State<BlurBotWidget> createState() => _BlurBotWidgetState();
}

class _BlurBotWidgetState extends State<BlurBotWidget> {

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      decoration: const BoxDecoration(
        image: DecorationImage(
          image: AssetImage('assets/images/background.png'),
          fit: BoxFit.cover,
        ),
      ),
    );
  }
}