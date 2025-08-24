import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

class WelcomePage extends StatefulWidget {
  final VoidCallback goNext;
  final VoidCallback? onSkip;

  const WelcomePage({super.key, required this.goNext, this.onSkip});

  @override
  State<WelcomePage> createState() => _WelcomePageState();
}

class _WelcomePageState extends State<WelcomePage> with TickerProviderStateMixin {
  late AnimationController _arrowController1;
  late AnimationController _arrowController2;
  late AnimationController _expansionController;
  late Animation<double> _arrowAnimation1;
  late Animation<double> _arrowAnimation2;
  late Animation<double> _expansionAnimation;
  late Animation<double> _fadeToBlackAnimation;
  late Animation<double> _buttonFadeAnimation;

  bool _isExpandingTop = false;

  @override
  void initState() {
    super.initState();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.manual, overlays: []);

    // Initialize arrow animations for both buttons
    _arrowController1 = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    )..repeat(reverse: true);

    _arrowController2 = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    )..repeat(reverse: true);

    // Initialize expansion animation
    _expansionController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );

    _arrowAnimation1 = Tween<double>(
      begin: 0,
      end: 4,
    ).animate(CurvedAnimation(
      parent: _arrowController1,
      curve: Curves.easeInOut,
    ));

    _arrowAnimation2 = Tween<double>(
      begin: 0,
      end: 4,
    ).animate(CurvedAnimation(
      parent: _arrowController2,
      curve: Curves.easeInOut,
    ));

    _expansionAnimation = Tween<double>(
      begin: 0.5,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _expansionController,
      curve: Curves.easeInOut,
    ));

    // Fade to black animation (starts at 0, goes to 1)
    _fadeToBlackAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _expansionController,
      curve: Curves.easeInOut,
    ));

    // Button fade animation (1 to 0 - fade out buttons)
    _buttonFadeAnimation = Tween<double>(
      begin: 1.0,
      end: 0.0,
    ).animate(CurvedAnimation(
      parent: _expansionController,
      curve: const Interval(0.0, 0.3, curve: Curves.easeOut),
    ));
  }

  @override
  void dispose() {
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.manual, overlays: SystemUiOverlay.values);
    _arrowController1.dispose();
    _arrowController2.dispose();
    _expansionController.dispose();
    super.dispose();
  }

  void _handleTopButtonPress() async {
    // Medium haptic feedback
    HapticFeedback.mediumImpact();

    // Show expansion
    setState(() {
      _isExpandingTop = true;
    });

    // Start expansion animation
    _expansionController.forward();

    final provider = Provider.of<OnboardingProvider>(context, listen: false);
    await provider.askForBluetoothPermissions();
    if (provider.hasBluetoothPermission) {
      // Wait for expansion to complete
      await Future.delayed(const Duration(milliseconds: 600));
      widget.goNext();
    } else {
      // Reset animations if permission denied
      setState(() {
        _isExpandingTop = false;
      });
      _expansionController.reset();

      showDialog(
        context: context,
        builder: (c) => getDialog(
          context,
          () {
            Navigator.of(context).pop();
            openAppSettings();
          },
          () {},
          'Permissions Required',
          'This app needs Bluetooth and Location permissions to function properly. Please enable them in the settings.',
          okButtonText: 'Open Settings',
          singleButton: true,
        ),
        barrierDismissible: false,
      );
    }
  }

  void _handleBottomButtonPress() async {
    // Medium haptic feedback
    HapticFeedback.mediumImpact();

    // Navigate immediately without transition
    if (widget.onSkip != null) {
      widget.onSkip!();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<OnboardingProvider>(
      builder: (context, provider, child) {
        return AnimatedBuilder(
          animation: _expansionController,
          builder: (context, child) {
            return Stack(
              children: [
                // Main content
                Column(
                  children: [
                    // Top half - Connect Device
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 800),
                      curve: Curves.easeInOut,
                      height: _isExpandingTop
                          ? MediaQuery.of(context).size.height
                          : MediaQuery.of(context).size.height * _expansionAnimation.value,
                      child: Container(
                        width: double.infinity,
                        decoration: BoxDecoration(
                          image: DecorationImage(
                            image: ResizeImage(
                              AssetImage(Assets.images.onboardingBg51.path),
                              width:
                                  (MediaQuery.of(context).size.width * MediaQuery.of(context).devicePixelRatio).round(),
                              height: (MediaQuery.of(context).size.height * MediaQuery.of(context).devicePixelRatio)
                                  .round(),
                            ),
                            fit: BoxFit.cover,
                          ),
                        ),
                        child: Stack(
                          children: [
                            // Dim overlay
                            Container(
                              color: Colors.black.withOpacity(0.4),
                            ),
                            // Fade to black overlay (increases during expansion)
                            if (_isExpandingTop)
                              Container(
                                color: Colors.black.withOpacity(_fadeToBlackAnimation.value * 0.9),
                              ),
                            // Content positioned in lower half
                            Positioned(
                              bottom: 60,
                              left: 20,
                              right: 20,
                              child: Opacity(
                                opacity: _buttonFadeAnimation.value,
                                child: Center(
                                  child: Material(
                                    color: Colors.white,
                                    borderRadius: BorderRadius.circular(28),
                                    elevation: 4,
                                    child: InkWell(
                                      onTap: _handleTopButtonPress,
                                      borderRadius: BorderRadius.circular(28),
                                      splashColor: Colors.green.withOpacity(0.7),
                                      highlightColor: Colors.green.withOpacity(0.1),
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                                        child: Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            const Text(
                                              'Connect Omi / OmiGlass',
                                              style: TextStyle(
                                                color: Colors.black87,
                                                fontSize: 18,
                                                fontWeight: FontWeight.w600,
                                                fontFamily: 'Manrope',
                                              ),
                                            ),
                                            const SizedBox(width: 8),
                                            AnimatedBuilder(
                                              animation: _arrowAnimation1,
                                              builder: (context, child) {
                                                return Transform.translate(
                                                  offset: Offset(_arrowAnimation1.value, 0),
                                                  child: const Icon(
                                                    Icons.arrow_forward,
                                                    size: 20,
                                                    color: Colors.black87,
                                                  ),
                                                );
                                              },
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),

                    // Bottom half - Continue Without Device
                    if (!_isExpandingTop)
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 800),
                        curve: Curves.easeInOut,
                        height: MediaQuery.of(context).size.height * (1 - _expansionAnimation.value),
                        child: Container(
                          width: double.infinity,
                          decoration: BoxDecoration(
                            image: DecorationImage(
                              image: ResizeImage(
                                AssetImage(Assets.images.onboardingBg52.path),
                                width: (MediaQuery.of(context).size.width * MediaQuery.of(context).devicePixelRatio)
                                    .round(),
                                height: (MediaQuery.of(context).size.height * MediaQuery.of(context).devicePixelRatio)
                                    .round(),
                              ),
                              fit: BoxFit.cover,
                            ),
                          ),
                          child: Stack(
                            children: [
                              // Dim overlay
                              Container(
                                color: Colors.black.withOpacity(0.5),
                              ),

                              // Content positioned in lower half
                              Positioned(
                                bottom: 60,
                                left: 20,
                                right: 20,
                                child: Opacity(
                                  opacity: _buttonFadeAnimation.value,
                                  child: Center(
                                    child: Material(
                                      color: Colors.transparent,
                                      borderRadius: BorderRadius.circular(28),
                                      child: InkWell(
                                        onTap: _handleBottomButtonPress,
                                        borderRadius: BorderRadius.circular(28),
                                        splashColor: Colors.green.withOpacity(0.7),
                                        highlightColor: Colors.green.withOpacity(0.1),
                                        child: Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                                          decoration: BoxDecoration(
                                            borderRadius: BorderRadius.circular(28),
                                            border: Border.all(color: Colors.white, width: 2),
                                          ),
                                          child: Row(
                                            mainAxisSize: MainAxisSize.min,
                                            children: [
                                              const Text(
                                                'Continue Without Device',
                                                style: TextStyle(
                                                  color: Colors.white,
                                                  fontSize: 18,
                                                  fontWeight: FontWeight.w600,
                                                  fontFamily: 'Manrope',
                                                ),
                                              ),
                                              const SizedBox(width: 8),
                                              AnimatedBuilder(
                                                animation: _arrowAnimation2,
                                                builder: (context, child) {
                                                  return Transform.translate(
                                                    offset: Offset(_arrowAnimation2.value, 0),
                                                    child: const Icon(
                                                      Icons.arrow_forward,
                                                      size: 20,
                                                      color: Colors.white,
                                                    ),
                                                  );
                                                },
                                              ),
                                            ],
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
              ],
            );
          },
        );
      },
    );
  }
}
