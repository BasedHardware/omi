import 'package:flutter/material.dart';
import 'package:omi/services/cortex/agent_activity.dart';

/// Wraps the app and paints a pulsing blue glow around the screen edges whenever
/// the Cortex agent is taking actions. Pointer-transparent, so it never blocks
/// the user — the agent works in the background and this is just a signal.
class CortexAgentEdgeOverlay extends StatefulWidget {
  final Widget child;
  const CortexAgentEdgeOverlay({super.key, required this.child});

  @override
  State<CortexAgentEdgeOverlay> createState() => _CortexAgentEdgeOverlayState();
}

class _CortexAgentEdgeOverlayState extends State<CortexAgentEdgeOverlay> with SingleTickerProviderStateMixin {
  static const _accent = Color(0xFF2F6BFF);
  late final AnimationController _pulse =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1600))..repeat(reverse: true);

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        widget.child,
        Positioned.fill(
          child: IgnorePointer(
            child: ValueListenableBuilder<bool>(
              valueListenable: CortexAgentActivity.instance.active,
              builder: (context, active, _) {
                if (!active) return const SizedBox.shrink();
                return AnimatedBuilder(
                  animation: _pulse,
                  builder: (context, _) {
                    final t = 0.55 + 0.45 * _pulse.value;
                    return DecoratedBox(
                      decoration: BoxDecoration(
                        border: Border.all(color: _accent.withOpacity(t), width: 3),
                        boxShadow: [
                          BoxShadow(color: _accent.withOpacity(0.5 * t), blurRadius: 24, spreadRadius: 2),
                        ],
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ),
      ],
    );
  }
}
