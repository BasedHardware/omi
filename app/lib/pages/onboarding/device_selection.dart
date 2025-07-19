import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:posthog_flutter/posthog_flutter.dart';
import 'package:video_player/video_player.dart';

class DeviceSelectionPage extends StatefulWidget {
  const DeviceSelectionPage({super.key});

  @override
  State<DeviceSelectionPage> createState() => _DeviceSelectionPageState();
}

class _DeviceSelectionPageState extends State<DeviceSelectionPage> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late Animation<double> _arrowAnimation;
  late VideoPlayerController _videoController;
  bool _isVideoInitialized = false;
  double _videoProgress = 0.0;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    )..repeat(reverse: true);

    _arrowAnimation = Tween<double>(
      begin: 0,
      end: 4,
    ).animate(CurvedAnimation(
      parent: _controller,
      curve: Curves.easeInOut,
    ));

    _initializeVideo();
  }

  void _initializeVideo() async {
    _videoController = VideoPlayerController.asset('assets/images/onboarding.mp4');
    try {
      await _videoController.initialize();
      setState(() {
        _isVideoInitialized = true;
      });
      _videoController.setLooping(true);
      _videoController.play();

      // Listen to video progress
      _videoController.addListener(_updateVideoProgress);
    } catch (e) {
      print('Error initializing video: $e');
    }
  }

  void _updateVideoProgress() {
    if (_videoController.value.isInitialized) {
      final position = _videoController.value.position;
      final duration = _videoController.value.duration;
      if (duration.inMilliseconds > 0) {
        setState(() {
          _videoProgress = position.inMilliseconds / duration.inMilliseconds;
        });
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _videoController.removeListener(_updateVideoProgress);
    _videoController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      child: Scaffold(
        backgroundColor: Colors.white,
        body: Stack(
          children: [
            // Main content
            Column(
              children: [
                // Video background area - constrained to available space
                Expanded(
                  child: Container(
                    width: double.infinity,
                    margin: const EdgeInsets.only(top: 60, bottom: 20),
                    child: _isVideoInitialized
                        ? FittedBox(
                            fit: BoxFit.cover,
                            child: SizedBox(
                              width: _videoController.value.size.width,
                              height: _videoController.value.size.height,
                              child: VideoPlayer(_videoController),
                            ),
                          )
                        : Container(
                            color: Colors.white,
                          ),
                  ),
                ),

                // Bottom drawer card - wraps content
                Container(
                  width: double.infinity,
                  padding: EdgeInsets.fromLTRB(32, 24, 32, 20),
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.only(
                      topLeft: Radius.circular(40),
                      topRight: Radius.circular(40),
                    ),
                  ),
                  child: SafeArea(
                    top: false,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // Title and subtitle
                        const Text(
                          'Omi – Your AI Companion',
                          style: TextStyle(
                            color: Colors.black,
                            fontSize: 34,
                            fontWeight: FontWeight.bold,
                            height: 1.2,
                            fontFamily: 'Manrope',
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'Capture every moment. Get AI-powered\nsummaries. Never take notes again.',
                          style: TextStyle(
                            color: Colors.black.withOpacity(0.7),
                            fontSize: 16,
                            height: 1.4,
                            fontFamily: 'Manrope',
                          ),
                          textAlign: TextAlign.center,
                        ),

                        const SizedBox(height: 20),

                        // Continue button
                        SizedBox(
                          width: double.infinity,
                          height: 56,
                          child: ElevatedButton(
                            onPressed: () async {
                              HapticFeedback.mediumImpact();
                              await Posthog().capture(
                                eventName: 'clicked_get_started',
                              );
                              if (mounted) {
                                routeToPage(context, const OnboardingWrapper());
                              }
                            },
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.black,
                              foregroundColor: Colors.white,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(28),
                              ),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const Text(
                                  'Get Started',
                                  style: TextStyle(
                                    fontSize: 18,
                                    fontWeight: FontWeight.w600,
                                    fontFamily: 'Manrope',
                                  ),
                                ),
                                const SizedBox(width: 8),
                                AnimatedBuilder(
                                  animation: _arrowAnimation,
                                  builder: (context, child) {
                                    return Transform.translate(
                                      offset: Offset(_arrowAnimation.value, 0),
                                      child: const Icon(Icons.arrow_forward, size: 20),
                                    );
                                  },
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),

            // Video progress indicator in top right
            if (_isVideoInitialized)
              Positioned(
                top: 60,
                right: 20,
                child: SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                    value: _videoProgress,
                    strokeWidth: 2,
                    backgroundColor: Colors.grey.withOpacity(0.3),
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.grey[700]!),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
