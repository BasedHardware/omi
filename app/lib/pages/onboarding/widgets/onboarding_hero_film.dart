import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:video_player/video_player.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/ui/ui.dart';

/// The launch film behind sign-in and data & privacy ([OnboardingHero.video]): full-screen, muted,
/// looping, darkened toward the bottom so the white type and buttons read. Under Reduce Motion it
/// holds its first frame.
class OnboardingHeroFilm extends StatefulWidget {
  const OnboardingHeroFilm({super.key});

  @override
  State<OnboardingHeroFilm> createState() => _OnboardingHeroFilmState();
}

class _OnboardingHeroFilmState extends State<OnboardingHeroFilm> {
  late final VideoPlayerController _film = VideoPlayerController.asset(
    Assets.videos.onboardingLaunchLoop,
    videoPlayerOptions: VideoPlayerOptions(mixWithOthers: true),
  );
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    _film.initialize().then((_) async {
      if (!mounted) return;
      await _film.setVolume(0);
      await _film.setLooping(true);
      if (!mounted) return;
      if (!MediaQuery.disableAnimationsOf(context)) await _film.play();
      if (mounted) setState(() => _ready = true);
    }).catchError((Object _) {});
  }

  @override
  void dispose() {
    _film.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ink = OmiPalette.light.textPrimary;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light,
      child: ColoredBox(
        color: ink,
        child: Stack(
          fit: StackFit.expand,
          children: [
            AnimatedOpacity(
              opacity: _ready ? 1 : 0,
              duration: const Duration(milliseconds: 600),
              child: _ready
                  ? FittedBox(
                      fit: BoxFit.cover,
                      clipBehavior: Clip.hardEdge,
                      child: SizedBox(
                        width: _film.value.size.width,
                        height: _film.value.size.height,
                        child: VideoPlayer(_film),
                      ),
                    )
                  : const SizedBox.shrink(),
            ),
            // A little shade under the status bar, and a deep one where the type and buttons sit: the
            // film has captions burned in near the bottom, so the shade is near-solid behind the text.
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    ink.withValues(alpha: 0.35),
                    ink.withValues(alpha: 0.0),
                    ink.withValues(alpha: 0.0),
                    ink.withValues(alpha: 0.85),
                    ink.withValues(alpha: 0.97),
                    ink.withValues(alpha: 0.98),
                  ],
                  stops: const [0.0, 0.18, 0.36, 0.58, 0.72, 1.0],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
