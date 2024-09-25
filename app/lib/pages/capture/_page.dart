import 'package:flutter/material.dart';

@Deprecated("Capture page is deprecated, use @pages > memories > widgets > capture instead.")
class CapturePage extends StatefulWidget {
  const CapturePage({
    super.key,
  });

  @override
  State<CapturePage> createState() => CapturePageState();
}

class CapturePageState extends State<CapturePage> {
  @override
  Widget build(BuildContext context) {
    return const Text("Depreacted");
  }
}
