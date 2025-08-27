import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:video_player/video_player.dart';

class DeviceOnboardingPage extends StatefulWidget {
  final int slideIndex;
  final VoidCallback onNext;
  final VoidCallback? onBack;
  final bool isFirstSlide;
  final bool isLastSlide;

  const DeviceOnboardingPage({
    super.key,
    required this.slideIndex,
    required this.onNext,
    this.onBack,
    this.isFirstSlide = false,
    this.isLastSlide = false,
  });

  @override
  State<DeviceOnboardingPage> createState() => _DeviceOnboardingPageState();
}

class _DeviceOnboardingPageState extends State<DeviceOnboardingPage> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late Animation<double> _arrowAnimation;
  late VideoPlayerController _videoController;
  bool _isVideoInitialized = false;
  double _videoProgress = 0.0;

  // Content for each slide
  final List<Map<String, String>> _slideContent = [
    {
      'title': 'Charging Your Omi',
      'subtitle': 'Place your Omi on the charging dock. An orange light indicates that it\'s charging.',
      'buttonText': 'Got it'
    },
    {
      'title': 'Device Disconnected',
      'subtitle': 'When disconnected, your Omi will show a red light to indicate offline status.',
      'buttonText': 'Understood'
    },
    {
      'title': 'Device Connected',
      'subtitle': 'A blue light indicates that your Omi is connected and capturing conversations.',
      'buttonText': 'Perfect'
    },
    {
      'title': 'Ask Questions',
      'subtitle': 'Long press Omi and speak out to ask questions. Omi will respond through notifications.',
      'buttonText': 'Cool'
    },
    {
      'title': 'Power Control',
      'subtitle': 'Short press the button to turn your Omi device on or off as needed.',
      'buttonText': 'Let\'s Go!'
    },
  ];

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
    final videoIndex = widget.slideIndex + 1;
    _videoController = VideoPlayerController.asset('assets/images/$videoIndex.mov');
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
    final content = _slideContent[widget.slideIndex];

    return Material(
      child: Scaffold(
        backgroundColor: Colors.black,
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
                            color: Colors.black,
                          ),
                  ),
                ),

                // Bottom drawer card - wraps content
                Container(
                  width: double.infinity,
                  padding: EdgeInsets.fromLTRB(32, 24, 32, 20),
                  decoration: const BoxDecoration(
                    color: Colors.black,
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
                        Text(
                          content['title']!,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 34,
                            fontWeight: FontWeight.bold,
                            height: 1.2,
                            fontFamily: 'Manrope',
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 12),
                        Text(
                          content['subtitle']!,
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.7),
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
                            onPressed: () {
                              HapticFeedback.mediumImpact();
                              widget.onNext();
                            },
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.white,
                              foregroundColor: Colors.black,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(28),
                              ),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Text(
                                  content['buttonText']!,
                                  style: const TextStyle(
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

            // Back button at top left
            if (!widget.isFirstSlide && widget.onBack != null)
              Positioned(
                top: MediaQuery.of(context).padding.top + 40,
                left: 24,
                child: Container(
                  width: 36,
                  height: 36,
                  margin: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.grey.withValues(alpha: 0.3),
                    shape: BoxShape.circle,
                  ),
                  child: IconButton(
                    padding: EdgeInsets.zero,
                    onPressed: widget.onBack,
                    icon: const FaIcon(FontAwesomeIcons.arrowLeft, size: 16.0, color: Colors.white),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
