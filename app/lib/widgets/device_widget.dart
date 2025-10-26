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
            widget.animatedBackground
                ? RepaintBoundary(
                    child: AnimatedBuilder(
                      animation: _animation,
                      builder: (context, child) {
                        return Transform.scale(
                          scale: _animation.value,
                          child: child,
                        );
                      },
                      child: Image.asset(
                        Assets.images.blob.path,
                        height: (MediaQuery.sizeOf(context).height <= 700 ? 360 : 390) * widget.sizeMultiplier,
                        width: (MediaQuery.sizeOf(context).height <= 700 ? 360 : 390) * widget.sizeMultiplier,
                        cacheHeight:
                            ((MediaQuery.sizeOf(context).height <= 700 ? 360 : 390) * widget.sizeMultiplier).round(),
                        cacheWidth:
                            ((MediaQuery.sizeOf(context).height <= 700 ? 360 : 390) * widget.sizeMultiplier).round(),
                      ),
                    ),
                  )
                : const SizedBox.shrink(),
            _buildDeviceImage()
          ],
        ),
      ),
    );
  }

  Widget _buildDeviceImage() {
    final pixelRatio = MediaQuery.of(context).devicePixelRatio;
    final double imageHeight = (MediaQuery.sizeOf(context).height <= 700 ? 130 : 160) * widget.sizeMultiplier;
    final double imageWidth = (MediaQuery.sizeOf(context).height <= 700 ? 130 : 160) * widget.sizeMultiplier;

    if (widget.deviceName != null && widget.deviceName == 'Omi') {
      return Stack(
        alignment: Alignment.center,
        children: [
          // Base image
          Image.asset(
            Assets.images.omiWithoutRopeTurnedOff.path,
            height: imageHeight,
            width: imageWidth,
            cacheHeight: (imageHeight * pixelRatio).round(),
            cacheWidth: (imageWidth * pixelRatio).round(),
          ),
          // Blue light overlay when connected TODO: improve this or just use the image itself
          AnimatedOpacity(
            opacity: widget.isConnected ? 1.0 : 0.0,
            duration: const Duration(milliseconds: 300),
            child: Container(
              width: imageWidth * 0.06,
              height: imageHeight * 0.06,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.blue.withOpacity(0.8),
                boxShadow: [
                  BoxShadow(
                    color: Colors.blue.withOpacity(0.5),
                    blurRadius: 8,
                    spreadRadius: 2,
                  ),
                ],
              ),
            ),
          ),
        ],
      );
    }

    return Image.asset(
      _getImagePath(),
      height: imageHeight,
      width: imageWidth,
      cacheHeight: (imageHeight * pixelRatio).round(),
      cacheWidth: (imageWidth * pixelRatio).round(),
    );
  }

  String _getImagePath() {
    // Check for PLAUD
    if (widget.deviceName != null && widget.deviceName!.toUpperCase().contains('PLAUD')) {
      return Assets.images.plaudNotePin.path;
    }

    // Show device image for both connected and paired devices
    if (widget.deviceName != null && widget.deviceName!.contains('Glass')) {
      return Assets.images.omiGlass.path;
    }

    if (widget.deviceName != null && widget.deviceName!.contains('Omi DevKit')) {
      return Assets.images.omiDevkitWithoutRope.path;
    }

    if (widget.deviceName != null && widget.deviceName!.contains('Apple Watch')) {
      return Assets.images.appleWatch.path;
    }

    // Default to omi device image, fallback to hero logo only if no device name
    if (widget.deviceName != null && widget.deviceName!.isNotEmpty) {
      return Assets.images.omiWithoutRope.path;
    }

    return Assets.images.herologo.path;
  }
}
