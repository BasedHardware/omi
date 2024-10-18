import 'dart:math';
import 'dart:math' as math;
import 'package:flutter/material.dart';

class SdCardTransferProgress extends StatefulWidget {
  final double progress;
  final String displayPercentage;
  final String secondsRemaining;

  const SdCardTransferProgress({
    super.key,
    required this.progress,
    required this.displayPercentage,
    required this.secondsRemaining,
  });

  @override
  _SdCardTransferProgressState createState() => _SdCardTransferProgressState();
}

class _SdCardTransferProgressState extends State<SdCardTransferProgress> with TickerProviderStateMixin {
  bool _transferComplete = false;
  late AnimationController _particleController;

  @override
  void initState() {
    super.initState();

    _particleController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );
  }

  @override
  void didUpdateWidget(covariant SdCardTransferProgress oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.progress == 1.0 && !_transferComplete) {
      setState(() {
        _transferComplete = true;
      });
      _particleController.forward(from: 0.0);
    }
  }

  @override
  void dispose() {
    _particleController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        Stack(
          alignment: Alignment.center,
          children: [
            SizedBox(
              width: MediaQuery.sizeOf(context).height * 0.34,
              height: MediaQuery.sizeOf(context).height * 0.34,
              child: Padding(
                padding: const EdgeInsets.all(50.0),
                child: CircularProgressIndicator(
                  value: widget.progress,
                  strokeWidth: 10,
                  backgroundColor: Colors.grey[800],
                  valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
                ),
              ),
            ),
            TweenAnimationBuilder(
              tween: Tween<double>(
                begin: 0.0,
                end: widget.progress > 0.0 ? 1.0 : 0.0,
              ),
              duration: const Duration(milliseconds: 800),
              builder: (context, double value, child) {
                final angle = value * pi; // Rotate from 0 to 180 degrees
                return Transform(
                  alignment: Alignment.center,
                  transform: Matrix4.rotationY(angle),
                  child: value < 0.5
                      ? const Icon(
                          Icons.sd_card,
                          size: 68,
                          color: Colors.white,
                        )
                      : Transform.flip(
                          flipX: true,
                          child: Column(
                            children: [
                              Text(
                                '${widget.displayPercentage}%',
                                style: const TextStyle(
                                  fontSize: 32,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.white,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                secondsToHumanReadable(widget.secondsRemaining),
                                style: const TextStyle(
                                  fontSize: 16,
                                  color: Colors.white,
                                ),
                              ),
                              const Text('Remaining', style: TextStyle(fontSize: 16, color: Colors.white)),
                            ],
                          ),
                        ),
                );
              },
            ),
            if (_transferComplete) ..._buildParticles(),
          ],
        ),
        const SizedBox(height: 16),
      ],
    );
  }

  List<Widget> _buildParticles() {
    return List.generate(60, (index) {
      final random = math.Random();
      final size = random.nextDouble() * 10 + 5;
      final angle = random.nextDouble() * 2 * pi;
      const radius = 100.0;

      return AnimatedBuilder(
        animation: _particleController,
        builder: (context, child) {
          final progress = _particleController.value;
          final tween = Tween(begin: 0.0, end: 30.0).chain(CurveTween(curve: Curves.easeOut));
          final distance = tween.evaluate(_particleController);

          final dx = (radius + distance) * cos(angle);
          final dy = (radius + distance) * sin(angle);

          final opacity = (1 - progress).clamp(0.0, 1.0);

          return Positioned(
            left: 150 + dx,
            top: 150 + dy,
            child: Transform.rotate(
              angle: progress * 2 * pi,
              child: Opacity(
                opacity: opacity,
                child: Container(
                  width: size,
                  height: size,
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                  ),
                ),
              ),
            ),
          );
        },
      );
    });
  }
}

String secondsToHumanReadable(String seconds) {
  final intSeconds = int.parse(seconds.split('.')[0]);
  final int hours = intSeconds ~/ 3600;
  final int minutes = (intSeconds % 3600) ~/ 60;
  final int remainingSeconds = intSeconds % 60;

  final List<String> parts = [];
  if (hours > 0) {
    parts.add('${hours}h');
  }

  if (minutes > 0) {
    parts.add('${minutes}m');
  }

  if (remainingSeconds > 0) {
    parts.add('${remainingSeconds}s');
  }

  return parts.join(' ');
}
