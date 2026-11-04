import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/home_bottom_bar.dart';

/// The light surface Home's bottom controls share: white on the light canvas, a step up from the
/// page in dark mode. It presses in slightly under the finger.
class HomeControlSurface extends StatefulWidget {
  const HomeControlSurface({
    super.key,
    required this.child,
    required this.semanticsLabel,
    this.semanticsHint,
    this.onTap,
    this.onLongPress,
    this.longPressHint,
    this.width,
    this.semanticsActions,
  });

  final Widget child;
  final String semanticsLabel;
  final String? semanticsHint;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final String? longPressHint;

  /// Fixed width (a circle); null fills the space it is given (the pill).
  final double? width;

  /// Actions of controls inside the surface, which its single label otherwise hides (the live
  /// pill's stop button).
  final Map<CustomSemanticsAction, VoidCallback>? semanticsActions;

  // White on the canvas like Home's cards, lifted by a soft, wide shadow because the controls
  // float over the list (a hairline would read as a form field).
  static BoxDecoration decoration() => BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.pillAll,
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 24, offset: const Offset(0, 6)),
          BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 4, offset: const Offset(0, 1)),
        ],
      );

  @override
  State<HomeControlSurface> createState() => _HomeControlSurfaceState();
}

class _HomeControlSurfaceState extends State<HomeControlSurface> {
  bool _pressed = false;

  void _press(bool down) {
    if (_pressed != down) setState(() => _pressed = down);
  }

  @override
  Widget build(BuildContext context) {
    final motion = OmiMotion.of(context);
    return Semantics(
      container: true,
      button: true,
      enabled: widget.onTap != null,
      label: widget.semanticsLabel,
      hint: widget.semanticsHint,
      onTap: widget.onTap,
      onLongPress: widget.onLongPress,
      onLongPressHint: widget.onLongPress == null ? null : widget.longPressHint,
      customSemanticsActions: widget.semanticsActions,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: widget.onTap == null ? null : (_) => _press(true),
        onTapUp: (_) => _press(false),
        onTapCancel: () => _press(false),
        onTap: widget.onTap,
        onLongPress: widget.onLongPress,
        child: AnimatedScale(
          scale: _pressed ? 0.96 : 1,
          duration: motion.quick,
          curve: Curves.easeOut,
          child: Container(
            width: widget.width,
            height: kHomeChatBarHeight,
            decoration: HomeControlSurface.decoration(),
            child: widget.child,
          ),
        ),
      ),
    );
  }
}

/// Ask Omi: a quiet circle at the left of the record pill. Tap to type, hold to talk.
class HomeChatButton extends StatelessWidget {
  const HomeChatButton({super.key, required this.onTap, required this.onLongPress});

  final VoidCallback onTap;
  final VoidCallback onLongPress;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return HomeControlSurface(
      key: const ValueKey('home_ask_omi_button'),
      width: kHomeChatBarHeight,
      semanticsLabel: l10n.askOmi,
      onTap: onTap,
      onLongPress: onLongPress,
      longPressHint: l10n.voiceMode,
      child: Center(child: FaIcon(FontAwesomeIcons.solidComment, size: 22, color: OmiColors.textPrimary)),
    );
  }
}

/// A 28pt ink disc holding a glyph: the pill's one point of contrast, so it reads as the
/// primary control without turning the whole bar dark.
class _Disc extends StatelessWidget {
  const _Disc({required this.child, this.color});

  final Widget child;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 28,
      height: 28,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: color ?? OmiColors.accent, shape: BoxShape.circle),
      child: child,
    );
  }
}

TextStyle _pillLabel() => OmiType.headline.copyWith(fontWeight: FontWeight.w500, color: OmiColors.textPrimary);

/// "+ New Recording": start a recording with this phone. While the microphone opens, a spinner
/// takes the plus's place.
class HomeNewPillContent extends StatelessWidget {
  const HomeNewPillContent({super.key, required this.starting});

  final bool starting;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox(
            width: 24,
            height: 24,
            child: Center(
              child: starting
                  ? OmiSpinner(size: OmiSpinnerSize.small, color: OmiColors.textPrimary)
                  : Icon(Icons.add_rounded, size: 26, color: OmiColors.textPrimary),
            ),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              context.l10n.homeNewRecordingButton,
              style: _pillLabel(),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          // Optical centre: the plus is lighter than the words, so the pair sits a hair right.
          const SizedBox(width: 4),
        ],
      ),
    );
  }
}

/// The phone recording, in place of "New": a breathing dot, what it is doing and the newest words
/// (the pill opens the live transcript), with its own stop button at the end. While the recording
/// finishes, the square becomes a spinner.
class HomeLivePillContent extends StatelessWidget {
  const HomeLivePillContent({
    super.key,
    required this.status,
    required this.onStop,
    this.lastLine,
    this.live = true,
    this.attention = false,
    this.stopping = false,
    this.onResume,
  });

  final String status;
  final String? lastLine;
  final bool live;

  /// Something the person should look at (tap the pill for why): an orange dot.
  final bool attention;
  final bool stopping;
  final VoidCallback? onStop;

  /// Paused by the person: the one control is Resume (Stop is in the sheet the pill opens).
  final VoidCallback? onResume;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const SizedBox(width: OmiSpacing.md + 2),
        HomeLiveDot(live: live, attention: attention),
        const SizedBox(width: OmiSpacing.sm),
        Expanded(child: _StatusAndWords(status: status, lastLine: lastLine)),
        if (onResume != null)
          Semantics(
            button: true,
            label: context.l10n.resume,
            child: GestureDetector(
              key: const ValueKey('home_record_pill_resume_button'),
              behavior: HitTestBehavior.opaque,
              onTap: onResume,
              child: SizedBox(
                width: kHomeChatBarHeight,
                height: kHomeChatBarHeight,
                child: Center(
                  child: _Disc(
                    color: OmiColors.textPrimary,
                    child: Icon(Icons.play_arrow_rounded, size: 20, color: OmiColors.surface1),
                  ),
                ),
              ),
            ),
          )
        else
          Semantics(
            button: true,
            label: context.l10n.stopRecording,
            child: GestureDetector(
              key: const ValueKey('home_record_pill_stop_button'),
              behavior: HitTestBehavior.opaque,
              onTap: stopping ? null : onStop,
              child: SizedBox(
                width: kHomeChatBarHeight,
                height: kHomeChatBarHeight,
                child: Center(
                  child: _Disc(
                    color: OmiColors.danger,
                    child: stopping
                        ? const OmiSpinner(size: OmiSpinnerSize.small, color: Colors.white)
                        : Container(
                            width: 10,
                            height: 10,
                            decoration: const BoxDecoration(
                              color: Colors.white,
                              borderRadius:
                                  BorderRadius.all(Radius.circular(2.5)), // omi-ux-allow: radius-literal -- a glyph
                            ),
                          ),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// One line of status, or, once words arrive, the status small above the newest words. The words
/// run in from the right and fade out at the left, so the latest is always what shows.
class _StatusAndWords extends StatelessWidget {
  const _StatusAndWords({required this.status, this.lastLine, this.title});

  final String status;
  final String? lastLine;

  /// The device name, before the status.
  final String? title;

  @override
  Widget build(BuildContext context) {
    final words = lastLine?.trim() ?? '';
    final secondary = OmiType.headline.copyWith(fontWeight: FontWeight.w400, color: OmiColors.textSecondary);
    if (words.isEmpty) {
      return Text.rich(
        TextSpan(children: [
          if (title != null) TextSpan(text: '$title  ', style: _pillLabel()),
          TextSpan(text: status, style: title == null ? _pillLabel() : secondary),
        ]),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      );
    }
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title == null ? status : '$title · $status',
          style: OmiType.caption.copyWith(color: OmiColors.textSecondary),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        SizedBox(
          height: 20,
          child: ShaderMask(
            shaderCallback: (rect) => const LinearGradient(
              colors: [Colors.transparent, Colors.black],
              stops: [0, 0.16],
            ).createShader(rect),
            blendMode: BlendMode.dstIn,
            child: ClipRect(
              child: OverflowBox(
                maxWidth: double.infinity,
                alignment: Alignment.centerRight,
                child: Text(
                  words,
                  key: const ValueKey('home_pill_last_words'),
                  style: OmiType.callout.copyWith(color: OmiColors.textPrimary),
                  maxLines: 1,
                  softWrap: false,
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// The connected device in place of "New": its picture with a live dot, its name and what it is
/// doing. (Its battery is in the header pill.)
class HomeDevicePillContent extends StatelessWidget {
  const HomeDevicePillContent({
    super.key,
    required this.device,
    required this.status,
    required this.live,
    this.lastLine,
    this.attention = false,
  });

  final BtDevice device;

  /// Something the person should look at: an orange dot.
  final bool attention;
  final String status;
  final String? lastLine;

  /// Capturing now: the dot is red and breathes; otherwise it is a still grey dot.
  final bool live;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox(
            width: 28,
            height: 28,
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                Positioned.fill(
                  child: Image.asset(
                    DeviceUtils.getDeviceImagePath(
                      deviceType: device.type,
                      modelNumber: device.modelNumber,
                      deviceName: device.name,
                    ),
                    fit: BoxFit.contain,
                  ),
                ),
                Positioned(right: -2, bottom: -1, child: HomeLiveDot(live: live, attention: attention)),
              ],
            ),
          ),
          const SizedBox(width: OmiSpacing.sm),
          Flexible(child: _StatusAndWords(title: device.name, status: status, lastLine: lastLine)),
        ],
      ),
    );
  }
}

/// A 10pt status dot ringed in the pill's colour so it reads on top of the device picture. Live:
/// red, breathing (still under Reduce Motion). Idle or paused: grey. Needs a look: orange, still.
class HomeLiveDot extends StatefulWidget {
  const HomeLiveDot({super.key, required this.live, this.attention = false});

  final bool live;
  final bool attention;

  @override
  State<HomeLiveDot> createState() => _HomeLiveDotState();
}

class _HomeLiveDotState extends State<HomeLiveDot> with SingleTickerProviderStateMixin {
  late final AnimationController _breath =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1400), lowerBound: 0.4, value: 1);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sync();
  }

  @override
  void didUpdateWidget(HomeLiveDot oldWidget) {
    super.didUpdateWidget(oldWidget);
    _sync();
  }

  void _sync() {
    final breathe = widget.live && !widget.attention && OmiMotion.of(context).standard != Duration.zero;
    if (breathe && !_breath.isAnimating) {
      _breath.repeat(reverse: true);
    } else if (!breathe) {
      _breath
        ..stop()
        ..value = 1;
    }
  }

  @override
  void dispose() {
    _breath.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 12,
      height: 12,
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(color: OmiColors.surface1, shape: BoxShape.circle),
      child: FadeTransition(
        opacity: _breath,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: widget.attention ? OmiColors.warning : (widget.live ? OmiColors.danger : OmiColors.textTertiary),
            shape: BoxShape.circle,
          ),
        ),
      ),
    );
  }
}
