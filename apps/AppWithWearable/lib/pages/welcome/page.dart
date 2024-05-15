import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:flutter_tilt/flutter_tilt.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'package:lottie/lottie.dart';
import 'dart:math';
import 'package:permission_handler/permission_handler.dart';

class WelcomeWidget extends StatefulWidget {
  const WelcomeWidget({super.key});

  @override
  State<WelcomeWidget> createState() => _WelcomeWidgetState();
}

class _WelcomeWidgetState extends State<WelcomeWidget> with SingleTickerProviderStateMixin {
  final unfocusNode = FocusNode();
  late AnimationController _animationController;
  late Animation<double> _animation;
  late Animation<double> _bounceAnimation;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();

    // Hide the status bar
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.manual, overlays: []);

    // Initialize the animation controller and animation
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 1),
    )..repeat(reverse: true);

    _animation = Tween<double>(begin: pi / 200, end: pi / 200).animate(_animationController);

    // Initialize the bounce animation
    _bounceAnimation = Tween<double>(begin: 0, end: 10).animate(
      CurvedAnimation(
        parent: _animationController,
        curve: Curves.easeInOut,
      ),
    );

    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  void dispose() {
    _animationController.dispose();
    unfocusNode.dispose();

    // Show the status bar again when the widget is disposed
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.manual, overlays: SystemUiOverlay.values);

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => unfocusNode.canRequestFocus
          ? FocusScope.of(context).requestFocus(unfocusNode)
          : FocusScope.of(context).unfocus(),
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: FlutterFlowTheme.of(context).primary,
        body: Stack(
          children: [
            const BlurBotWidget(),
            Column(
              mainAxisSize: MainAxisSize.max,
              children: [
                Expanded(
                  child: Tilt(
                    shadowConfig: const ShadowConfig(disable: true),
                    lightConfig: const LightConfig(disable: true),
                    tiltConfig: const TiltConfig(
                      angle: 30,
                      moveDuration: Duration(milliseconds: 0),
                    ),
                    child: AnimatedBuilder(
                      animation: _bounceAnimation,
                      builder: (context, child) {
                        return Transform.translate(
                          offset: Offset(0, -_bounceAnimation.value),
                          child: Transform.rotate(
                            angle: _animation.value,
                            child: Image.asset(
                              'assets/images/hero_image.png',
                              fit: BoxFit.cover,
                              width: double.infinity,
                              height: double.infinity,
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                ),
                Align(
                  alignment: Alignment.bottomCenter,
                  child: Padding(
                    padding: const EdgeInsetsDirectional.fromSTEB(30.0, 80.0, 30.0, 40.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          "Friend helps you remember everything",
                          textAlign: TextAlign.start,
                          style: FlutterFlowTheme.of(context).bodyMedium.override(
                                fontFamily: 'SF Pro Display',
                                color: Colors.white,
                                fontSize: 29.0,
                                letterSpacing: 0.0,
                                fontWeight: FontWeight.w900,
                                useGoogleFonts: GoogleFonts.asMap().containsKey('SF Pro Display'),
                                lineHeight: 1.2,
                              ),
                        ),
                        const SizedBox(height: 10.0),
                        const Text(
                          "Your Personal growth journey with AI that listens to your every word",
                          style: TextStyle(
                            color: Color.fromARGB(255, 101, 101, 101),
                            fontSize: 14.0,
                            fontWeight: FontWeight.w700,
                            height: 1.5,
                          ),
                        ),
                        const SizedBox(height: 20.0),
                        Center(
                          child: Material(
                            elevation: 4.0,
                            shape: const CircleBorder(),
                            child: InkWell(
                              splashColor: Colors.transparent,
                              focusColor: Colors.transparent,
                              hoverColor: Colors.transparent,
                              highlightColor: Colors.transparent,
                              mouseCursor: SystemMouseCursors.click,
                              onTap: () async {
                                // Check if Bluetooth and location permissions are granted
                                PermissionStatus bluetoothStatus = await Permission.bluetooth.status;
                                PermissionStatus locationStatus = await Permission.location.status;

                                if (bluetoothStatus.isGranted && locationStatus.isGranted) {
                                  // Both permissions are already granted
                                  // Request notification permission
                                  PermissionStatus notificationStatus = await Permission.notification.request();

                                  // Navigate to the 'scanDevices' screen
                                  context.goNamed('findDevices');
                                } else {
                                  // Request both Bluetooth and location permissions
                                  if (await Permission.bluetooth.request().isGranted &&
                                      await Permission.location.request().isGranted) {
                                    // Both permissions are granted now
                                    // Request notification permission
                                    PermissionStatus notificationStatus = await Permission.notification.request();

                                    // Navigate to the 'scanDevices' screen
                                    context.goNamed('findDevices');
                                  } else {
                                    // Either permission is denied
                                    // Show a dialog to inform the user and provide an action to open app settings
                                    showDialog(
                                      context: context,
                                      builder: (BuildContext context) {
                                        return AlertDialog(
                                          backgroundColor: Colors.grey[900],
                                          title: const Text(
                                            'Permissions Required',
                                            style: TextStyle(
                                              color: Colors.white,
                                              fontSize: 20,
                                              fontWeight: FontWeight.bold,
                                            ),
                                          ),
                                          content: const Text(
                                            'This app needs Bluetooth and Location permissions to function properly. Please enable them in the settings.',
                                            style: TextStyle(
                                              color: Colors.white,
                                              fontSize: 16,
                                            ),
                                          ),
                                          actions: [
                                            TextButton(
                                              onPressed: () {
                                                Navigator.of(context).pop();
                                                openAppSettings();
                                              },
                                              child: const Text(
                                                'OK',
                                                style: TextStyle(
                                                  color: Colors.blue,
                                                  fontSize: 16,
                                                  fontWeight: FontWeight.bold,
                                                ),
                                              ),
                                            ),
                                          ],
                                        );
                                      },
                                    );
                                  }
                                }
                              },
                              child: ShaderMask(
                                shaderCallback: (Rect bounds) {
                                  return RadialGradient(
                                    center: Alignment.center,
                                    radius: 0.45,
                                    colors: [Colors.white, Colors.white.withOpacity(0.0)],
                                    stops: [0.9, 1.0],
                                  ).createShader(bounds);
                                },
                                child: Container(
                                  width: 100,
                                  height: 100,
                                  decoration: const BoxDecoration(
                                    shape: BoxShape.circle,
                                  ),
                                  child: Transform(
                                    transform: Matrix4.identity()
                                      ..setEntry(3, 2, 0.001) // Perspective
                                      ..rotateX(0.1) // Rotation around X-axis
                                      ..rotateY(-0.1), // Rotation around Y-axis
                                    alignment: Alignment.center,
                                    child: ClipOval(
                                      child: Stack(
                                        children: [
                                          Opacity(
                                            opacity: 0.8,
                                            child: Lottie.asset(
                                              'assets/images/grid_wave.json',
                                              width: 150,
                                              height: 150,
                                              fit: BoxFit.cover,
                                            ),
                                          ),
                                          Center(
                                            child: Transform.rotate(
                                              angle: -pi / 4,
                                              child: const Icon(
                                                Icons.arrow_forward,
                                                size: 60,
                                                color: Colors.white,
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),
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
        ),
      ),
    );
  }
}
