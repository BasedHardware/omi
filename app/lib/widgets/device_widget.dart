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
            _buildDeviceImage()
          ],
        ),
      ),
    );
  }

  Widget _buildDeviceImage() {
    final double imageHeight = (MediaQuery.sizeOf(context).height <= 700 ? 130 : 160) * widget.sizeMultiplier;
    final double imageWidth = (MediaQuery.sizeOf(context).height <= 700 ? 130 : 160) * widget.sizeMultiplier;

    // Special stacked approach for "Omi" device
    if (widget.deviceName != null && widget.deviceName == 'Omi') {
      return Stack(
        alignment: Alignment.center,
        children: [
          // Bottom layer: turned-off image (always visible)
          Image.asset(
          Assets.images.omiWithoutRopeTurnedOff.path,
            height: imageHeight,
            width: imageWidth,
          ),
          // Top layer: turned-on image (visible only when connected)
          AnimatedOpacity(
            opacity: widget.isConnected ? 1.0 : 0.0,
            duration: const Duration(milliseconds: 300),
            child: Image.asset(
              Assets.images.omiWithoutRope.path,
              height: imageHeight,
              width: imageWidth,
            ),
          ),
        ],
      );
    }

    // For all other devices, use the regular single image approach
    return Image.asset(
      _getImagePath(),
      height: imageHeight,
      width: imageWidth,
    );
  }

  String _getImagePath() {
    // Show device image for both connected and paired devices
    if (widget.deviceName != null && widget.deviceName!.contains('Glass')) {
      return Assets.images.omiGlass.path;
    }

    if (widget.deviceName != null && widget.deviceName!.contains('Omi DevKit')) {
      return Assets.images.omiDevkitWithoutRope.path;
    }

    // Default to omi device image, fallback to hero logo only if no device name
    if (widget.deviceName != null && widget.deviceName!.isNotEmpty) {
      return Assets.images.omiWithoutRope.path;
    }

    return Assets.images.herologo.path;
  }
}
