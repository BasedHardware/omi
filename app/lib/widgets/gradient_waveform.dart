import 'package:flutter/material.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'dart:math' as math;

class GradientWaveform extends StatelessWidget {
  final double width;
  final double height;
  final List<double>? barHeights;
  final List<double>? audioLevels; // Real-time audio levels
  final int barCount;
  final double barWidth;
  final double spacing;
  final List<Color>? gradientColors;
  final bool animated;
  final bool isDeviceRecording; // New parameter to distinguish device vs phone recording
  final Duration animationDuration;

  const GradientWaveform({
    super.key,
    this.width = 80,
    this.height = 40,
    this.barHeights,
    this.audioLevels, // New parameter for real-time audio
    this.barCount = 4,
    this.barWidth = 8,
    this.spacing = 4,
    this.gradientColors,
    this.animated = false,
    this.isDeviceRecording = false, // Default to phone recording
    this.animationDuration = const Duration(milliseconds: 1200),
  });

  @override
  Widget build(BuildContext context) {
    final colors = gradientColors ??
        [
          ResponsiveHelper.purplePrimary.withValues(alpha: 0.8),
          ResponsiveHelper.purpleSecondary,
          ResponsiveHelper.purpleLight,
        ];

    // Use real-time audio levels if provided, otherwise use static bar heights
    List<double> heights;
    if (audioLevels != null && audioLevels!.isNotEmpty) {
      heights = List.filled(barCount, 0.15);

      if (audioLevels!.length >= barCount) {
        // If we have enough audio levels, use the most recent ones
        final recentLevels = audioLevels!.sublist(audioLevels!.length - barCount);
        for (int i = 0; i < barCount; i++) {
          heights[i] = recentLevels[i].clamp(0.15, 1.6);
        }
      } else {
        // If we have fewer audio levels than bars, distribute them across all bars
        // by interpolating and repeating the available levels
        for (int i = 0; i < barCount; i++) {
          // Map bar index to audio level index with interpolation
          final sourceIndex = (i * audioLevels!.length / barCount).floor() % audioLevels!.length;
          final nextIndex = ((sourceIndex + 1) % audioLevels!.length);

          // Simple interpolation between adjacent audio levels
          final fraction = (i * audioLevels!.length / barCount) - sourceIndex;
          final currentLevel = audioLevels![sourceIndex];
          final nextLevel = audioLevels![nextIndex];

          final interpolatedLevel = currentLevel + (nextLevel - currentLevel) * fraction;
          heights[i] = interpolatedLevel.clamp(0.15, 1.6);
        }
      }
    } else {
      heights = barHeights ?? [0.2, 0.4, 0.7, 1.0, 0.8, 0.5, 0.3, 0.25];
    }

    // Use different animation based on recording type
    if (isDeviceRecording) {
      // Device recording - use random animated values
      return RandomAnimatedWaveform(
        width: width,
        height: height,
        barCount: barCount,
        barWidth: barWidth,
        spacing: spacing,
        colors: colors,
      );
    } else if (animated && audioLevels == null) {
      // Not recording - use subtle breathing animation
      return AnimatedWaveform(
        width: width,
        height: height,
        barCount: barCount,
        barWidth: barWidth,
        spacing: spacing,
        colors: colors,
        animationDuration: animationDuration,
        initialHeights: heights,
      );
    }

    // Phone recording - use real-time audio levels with subtle animation
    return SubtleAnimatedWaveform(
      width: width,
      height: height,
      barCount: barCount,
      barWidth: barWidth,
      spacing: spacing,
      colors: colors,
      baseHeights: heights.take(barCount).toList(),
    );
  }
}

class AudioResponsiveWaveform extends StatefulWidget {
  final double width;
  final double height;
  final int barCount;
  final double barWidth;
  final double spacing;
  final List<Color>? gradientColors;
  final bool isRecording;

  const AudioResponsiveWaveform({
    super.key,
    required this.width,
    required this.height,
    required this.barCount,
    required this.barWidth,
    required this.spacing,
    this.gradientColors,
    required this.isRecording,
  });

  @override
  State<AudioResponsiveWaveform> createState() => _AudioResponsiveWaveformState();
}

class _AudioResponsiveWaveformState extends State<AudioResponsiveWaveform> with SingleTickerProviderStateMixin {
  // Audio visualization levels
  final List<double> _audioLevels = List.generate(8, (_) => 0.15);
  late AnimationController _animationController;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 150),
    );
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  // Method to update audio levels from external source
  void updateAudioLevels(List<double> newLevels) {
    if (!mounted) return;

    setState(() {
      // Update levels with smoothing
      for (int i = 0; i < math.min(newLevels.length, _audioLevels.length); i++) {
        final newLevel = newLevels[i].clamp(0.15, 1.6);
        // Apply less smoothing for more responsiveness
        _audioLevels[i] = (_audioLevels[i] * 0.5) + (newLevel * 0.5);
      }
    });

    // Trigger animation for smooth updates
    _animationController.forward().then((_) {
      if (mounted) {
        _animationController.reset();
      }
    });
  }

  // Method to process raw audio bytes (similar to voice recorder)
  void processAudioBytes(List<int> bytes) {
    if (bytes.isEmpty || !widget.isRecording) return;

    double rms = 0;

    // Process bytes as 16-bit samples (2 bytes per sample)
    for (int i = 0; i < bytes.length - 1; i += 2) {
      // Convert two bytes to a 16-bit signed integer
      int sample = bytes[i] | (bytes[i + 1] << 8);

      // Convert to signed value (if high bit is set)
      if (sample > 32767) {
        sample = sample - 65536;
      }

      // Square the sample and add to sum
      rms += sample * sample;
    }

    // Calculate RMS and normalize to 0.0-1.0 range
    int sampleCount = bytes.length ~/ 2;
    if (sampleCount > 0) {
      rms = math.sqrt(rms / sampleCount) / 32768.0;
    } else {
      rms = 0;
    }

    // Apply non-linear scaling for better dynamic range - quieter on silence, same on noise
    final level = (math.pow(rms, 0.3).toDouble() * 2.1).clamp(0.15, 1.6);

    // Shift all values left and add new level
    for (int i = 0; i < _audioLevels.length - 1; i++) {
      _audioLevels[i] = _audioLevels[i + 1];
    }
    _audioLevels[_audioLevels.length - 1] = level;

    if (mounted) {
      setState(() {});
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = widget.gradientColors ??
        [
          ResponsiveHelper.purplePrimary.withValues(alpha: 0.8),
          ResponsiveHelper.purpleSecondary,
          ResponsiveHelper.purpleLight,
        ];

    // Show static bars when not recording
    final displayLevels = widget.isRecording ? _audioLevels : [0.2, 0.4, 0.7, 1.0, 0.8, 0.5, 0.3, 0.25];

    return AnimatedBuilder(
      animation: _animationController,
      builder: (context, child) {
        return CustomPaint(
          size: Size(widget.width, widget.height),
          painter: WaveformPainter(
            barHeights: displayLevels.take(widget.barCount).toList(),
            barWidth: widget.barWidth,
            spacing: widget.spacing,
            gradientColors: colors,
          ),
        );
      },
    );
  }
}

class RandomAnimatedWaveform extends StatefulWidget {
  final double width;
  final double height;
  final int barCount;
  final double barWidth;
  final double spacing;
  final List<Color> colors;

  const RandomAnimatedWaveform({
    super.key,
    required this.width,
    required this.height,
    required this.barCount,
    required this.barWidth,
    required this.spacing,
    required this.colors,
  });

  @override
  State<RandomAnimatedWaveform> createState() => _RandomAnimatedWaveformState();
}

class _RandomAnimatedWaveformState extends State<RandomAnimatedWaveform> with TickerProviderStateMixin {
  late AnimationController _mainController;
  late List<AnimationController> _barControllers;
  late List<Animation<double>> _barAnimations;
  final math.Random _random = math.Random();

  @override
  void initState() {
    super.initState();

    // Main controller for triggering random updates (slower for smoother feel)
    _mainController = AnimationController(
      duration: const Duration(milliseconds: 200),
      vsync: this,
    )..repeat();

    // Individual controllers for each bar with different random durations
    _barControllers = List.generate(widget.barCount, (index) {
      return AnimationController(
        duration: Duration(milliseconds: 500 + _random.nextInt(1500)), // 500-2000ms random duration
        vsync: this,
      );
    });

    // Initialize individual animations for each bar
    _barAnimations = _barControllers.asMap().entries.map((entry) {
      final controller = entry.value;
      return _createRandomAnimation(controller);
    }).toList();

    // Start all controllers with random delays
    for (int i = 0; i < _barControllers.length; i++) {
      Future.delayed(Duration(milliseconds: _random.nextInt(500)), () {
        if (mounted) {
          _barControllers[i].repeat();
        }
      });
    }

    // Periodically create completely new random animations
    _mainController.addListener(() {
      if (_random.nextDouble() < 0.02) {
        // 2% chance each frame (less frequent for smoother animation)
        _randomizeRandomBar();
      }
    });
  }

  Animation<double> _createRandomAnimation(AnimationController controller) {
    return Tween<double>(
      begin: 0.15 + _random.nextDouble() * 0.3, // Random start: 0.15-0.45
      end: 0.25 + _random.nextDouble() * 0.5, // Random end: 0.25-0.75 (reduced max height)
    ).animate(CurvedAnimation(
      parent: controller,
      curve: _getRandomCurve(),
    ));
  }

  Curve _getRandomCurve() {
    // Use only the smoothest curves for fluid animation
    final curves = [
      Curves.easeInOut,
      Curves.easeInOutCubic,
      Curves.easeInOutSine,
      Curves.decelerate,
      Curves.fastOutSlowIn,
      Curves.easeInOutQuart,
    ];
    return curves[_random.nextInt(curves.length)];
  }

  void _randomizeRandomBar() {
    if (!mounted) return;

    final barIndex = _random.nextInt(widget.barCount);

    // Create completely new animation with new random values
    _barAnimations[barIndex] = _createRandomAnimation(_barControllers[barIndex]);

    // Randomize controller duration
    _barControllers[barIndex].duration = Duration(
      milliseconds: 300 + _random.nextInt(1200), // 300-1500ms
    );

    // Reset and restart with new random settings
    _barControllers[barIndex].reset();
    _barControllers[barIndex].repeat();
  }

  @override
  void dispose() {
    _mainController.dispose();
    for (final controller in _barControllers) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([_mainController, ..._barControllers]),
      builder: (context, child) {
        // Generate smooth random heights for each bar
        final animatedHeights = _barAnimations.asMap().entries.map((entry) {
          final index = entry.key;
          final animation = entry.value;

          // Smooth base height from animation (no per-frame noise for smoothness)
          final baseHeight = animation.value;

          // Add stable, smooth sine wave for each bar (no random values per frame)
          final stablePhase = (index * 0.7) + (_mainController.value * 2 * math.pi * 0.3);
          final smoothing = 0.02 * math.sin(stablePhase);

          return (baseHeight + smoothing).clamp(0.3, 1.2);
        }).toList();

        return CustomPaint(
          size: Size(widget.width, widget.height),
          painter: WaveformPainter(
            barHeights: animatedHeights,
            barWidth: widget.barWidth,
            spacing: widget.spacing,
            gradientColors: widget.colors,
          ),
        );
      },
    );
  }
}

class SubtleAnimatedWaveform extends StatefulWidget {
  final double width;
  final double height;
  final int barCount;
  final double barWidth;
  final double spacing;
  final List<Color> colors;
  final List<double> baseHeights;

  const SubtleAnimatedWaveform({
    super.key,
    required this.width,
    required this.height,
    required this.barCount,
    required this.barWidth,
    required this.spacing,
    required this.colors,
    required this.baseHeights,
  });

  @override
  State<SubtleAnimatedWaveform> createState() => _SubtleAnimatedWaveformState();
}

class _SubtleAnimatedWaveformState extends State<SubtleAnimatedWaveform> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 2000),
      vsync: this,
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        // Create subtle breathing effect
        final animatedHeights = widget.baseHeights.asMap().entries.map((entry) {
          final index = entry.key;
          final baseHeight = entry.value;

          // Add subtle sine wave variation with different phase for each bar
          final phase = (index * 0.5) + (_controller.value * 2 * math.pi);
          final breathingEffect = 0.12 * math.sin(phase);

          // Combine base height with subtle breathing
          return (baseHeight + breathingEffect).clamp(0.15, 1.6);
        }).toList();

        return CustomPaint(
          size: Size(widget.width, widget.height),
          painter: WaveformPainter(
            barHeights: animatedHeights,
            barWidth: widget.barWidth,
            spacing: widget.spacing,
            gradientColors: widget.colors,
          ),
        );
      },
    );
  }
}

class AnimatedWaveform extends StatefulWidget {
  final double width;
  final double height;
  final int barCount;
  final double barWidth;
  final double spacing;
  final List<Color> colors;
  final Duration animationDuration;
  final List<double> initialHeights;

  const AnimatedWaveform({
    super.key,
    required this.width,
    required this.height,
    required this.barCount,
    required this.barWidth,
    required this.spacing,
    required this.colors,
    required this.animationDuration,
    required this.initialHeights,
  });

  @override
  State<AnimatedWaveform> createState() => _AnimatedWaveformState();
}

class _AnimatedWaveformState extends State<AnimatedWaveform> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late List<Animation<double>> _heightAnimations;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: widget.animationDuration,
      vsync: this,
    );

    _setupAnimations();
    _controller.repeat(reverse: true);
  }

  void _setupAnimations() {
    _heightAnimations = List.generate(widget.barCount, (index) {
      final baseHeight = index < widget.initialHeights.length ? widget.initialHeights[index] : 0.5;

      return Tween<double>(
        begin: baseHeight * 0.3,
        end: baseHeight,
      ).animate(
        CurvedAnimation(
          parent: _controller,
          curve: Interval(
            (index / widget.barCount).clamp(0.0, 0.8),
            1.0,
            curve: Curves.easeInOut,
          ),
        ),
      );
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return CustomPaint(
          size: Size(widget.width, widget.height),
          painter: WaveformPainter(
            barHeights: _heightAnimations.map((anim) => anim.value).toList(),
            barWidth: widget.barWidth,
            spacing: widget.spacing,
            gradientColors: widget.colors,
          ),
        );
      },
    );
  }
}

class WaveformPainter extends CustomPainter {
  final List<double> barHeights;
  final double barWidth;
  final double spacing;
  final List<Color> gradientColors;

  WaveformPainter({
    required this.barHeights,
    required this.barWidth,
    required this.spacing,
    required this.gradientColors,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (barHeights.isEmpty) return;

    // Calculate ideal dimensions
    final idealTotalBarsWidth = barHeights.length * barWidth;
    final idealTotalSpacing = (barHeights.length - 1) * spacing;
    final idealTotalWidth = idealTotalBarsWidth + idealTotalSpacing;

    // Determine actual dimensions that fit within container
    late double actualBarWidth;
    late double actualSpacing;
    late double actualTotalWidth;

    if (idealTotalWidth <= size.width) {
      // Ideal dimensions fit, use them as-is
      actualBarWidth = barWidth;
      actualSpacing = spacing;
      actualTotalWidth = idealTotalWidth;
    } else {
      // Scale down to fit within container
      final scaleFactor = (size.width - 8) / idealTotalWidth; // Leave 4px padding on each side
      actualBarWidth = (barWidth * scaleFactor).clamp(2.0, barWidth); // Minimum 2px bar width
      actualSpacing = (spacing * scaleFactor).clamp(1.0, spacing); // Minimum 1px spacing

      // Recalculate total width with scaled dimensions
      final scaledTotalBarsWidth = barHeights.length * actualBarWidth;
      final scaledTotalSpacing = (barHeights.length - 1) * actualSpacing;
      actualTotalWidth = scaledTotalBarsWidth + scaledTotalSpacing;

      // If still too wide after scaling, reduce spacing further
      if (actualTotalWidth > size.width - 8) {
        final excessWidth = actualTotalWidth - (size.width - 8);
        final spacingReduction = excessWidth / (barHeights.length - 1);
        actualSpacing = (actualSpacing - spacingReduction).clamp(0.5, actualSpacing);
        actualTotalWidth = scaledTotalBarsWidth + ((barHeights.length - 1) * actualSpacing);
      }
    }

    // Center the waveform horizontally
    final startX = (size.width - actualTotalWidth) / 2;

    for (int i = 0; i < barHeights.length; i++) {
      final x = startX + (i * (actualBarWidth + actualSpacing));
      final barHeight = barHeights[i] * size.height;
      final y = (size.height - barHeight) / 2;

      // Create gradient for each bar
      final gradient = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: gradientColors,
        stops: const [0.0, 0.5, 1.0],
      );

      final paint = Paint()
        ..shader = gradient.createShader(
          Rect.fromLTWH(x, y, actualBarWidth, barHeight),
        )
        ..strokeCap = StrokeCap.round;

      // Draw rounded rectangle bar
      final rect = RRect.fromRectAndRadius(
        Rect.fromLTWH(x, y, actualBarWidth, barHeight),
        Radius.circular(actualBarWidth / 2),
      );

      canvas.drawRRect(rect, paint);
    }
  }

  @override
  bool shouldRepaint(WaveformPainter oldDelegate) {
    return oldDelegate.barHeights != barHeights || oldDelegate.gradientColors != gradientColors;
  }
}
