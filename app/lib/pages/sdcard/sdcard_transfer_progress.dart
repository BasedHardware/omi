import 'dart:math';
import 'package:flutter/material.dart';

class SdCardTransferProgress extends StatefulWidget {
  final double progress;
  final String displayPercentage;

  const SdCardTransferProgress({super.key, required this.progress, required this.displayPercentage});

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
              width: MediaQuery.sizeOf(context).height * 0.32,
              height: MediaQuery.sizeOf(context).height * 0.32,
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
            const Icon(
              Icons.sd_card,
              size: 64,
              color: Colors.white,
            ),
            if (_transferComplete) ..._buildParticles(),
          ],
        ),
        const SizedBox(height: 20),
        Text(
          _transferComplete ? 'Transfer Complete!' : '${widget.displayPercentage}%',
          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Colors.white),
        ),
        const SizedBox(height: 16),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List.generate(3, (index) {
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: widget.progress > index / 3 ? Colors.white : Colors.grey[800],
                ),
              ),
            );
          }),
        ),
      ],
    );
  }

  List<Widget> _buildParticles() {
    return List.generate(60, (index) {
      final random = Random();
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
