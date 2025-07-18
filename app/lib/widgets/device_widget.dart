import 'package:flutter/material.dart';
import 'package:omi/gen/assets.gen.dart';

class DeviceAnimationWidget extends StatefulWidget {
  final bool animatedBackground;
  final double sizeMultiplier;
  final bool isConnected;
  final String? deviceName;

  const DeviceAnimationWidget({
    super.key,
    this.sizeMultiplier = 1.0,
    this.animatedBackground = true,
    this.isConnected = false,
    this.deviceName,
  });

  @override
  State<DeviceAnimationWidget> createState() => _DeviceAnimationWidgetState();
}

class _DeviceAnimationWidgetState extends State<DeviceAnimationWidget> with TickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  @override
  void initState() {
    _controller = AnimationController(
      duration: const Duration(milliseconds: 2000),
      vsync: this,
    )..repeat(reverse: true);
    _animation = Tween<double>(begin: 1, end: 0.8).animate(_controller);
    super.initState();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: MediaQuery.sizeOf(context).height <= 700 ? 220 * widget.sizeMultiplier : 340 * widget.sizeMultiplier,
      child: Center(
        child: Stack(
          alignment: Alignment.center,
          children: [
            Image.asset(
              Assets.images.stars.path,
            ),
            widget.animatedBackground
                ? AnimatedBuilder(
                    animation: _animation,
                    builder: (context, child) {
                      return Image.asset(
                        Assets.images.blob.path,
                        height: (MediaQuery.sizeOf(context).height <= 700 ? 360 : 390) * widget.sizeMultiplier * _animation.value,
                        width: (MediaQuery.sizeOf(context).height <= 700 ? 360 : 390) * widget.sizeMultiplier * _animation.value,
                      );
                    },
                  )
                : Container(),
            // Image.asset("assets/images/blob.png"),
            Image.asset(
              _getImagePath(),
              height: (MediaQuery.sizeOf(context).height <= 700 ? 130 : 160) * widget.sizeMultiplier,
              width: (MediaQuery.sizeOf(context).height <= 700 ? 130 : 160) * widget.sizeMultiplier,
            )
          ],
        ),
      ),
    );
  }

  String _getImagePath() {
    // Show device image for both connected and paired devices
    if (widget.deviceName != null && widget.deviceName!.contains('Glass')) {
      return 'assets/images/omi-glass.png';
    }

    if (widget.deviceName != null && widget.deviceName!.contains('Omi DevKit')) {
      return 'assets/images/omi-devkit-without-rope.png';
    }

    // Default to omi device image, fallback to hero logo only if no device name
    if (widget.deviceName != null && widget.deviceName!.isNotEmpty) {
      return 'assets/images/omi-without-rope.png';
    }

    return Assets.images.herologo.path;
  }
}
