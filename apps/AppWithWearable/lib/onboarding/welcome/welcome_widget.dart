import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:google_fonts/google_fonts.dart';

import '/components/logo/logo_main/logo_main_widget.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import '/pages/ble/blur_bot/blur_bot_widget.dart';
import 'welcome_model.dart';
import 'package:lottie/lottie.dart';
import 'dart:math';
import 'dart:ui';
import 'package:permission_handler/permission_handler.dart';


class WelcomeWidget extends StatefulWidget {
  const WelcomeWidget({super.key});

  @override
  State<WelcomeWidget> createState() => _WelcomeWidgetState();
}

class _WelcomeWidgetState extends State<WelcomeWidget> with SingleTickerProviderStateMixin {
  late WelcomeModel _model;
  late AnimationController _animationController;
  late Animation<double> _animation;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => WelcomeModel());

    // Hide the status bar
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.manual, overlays: []);

    // Initialize the animation controller and animation
    _animationController = AnimationController(
      vsync: this,
      duration: Duration(seconds: 1),
    )..repeat(reverse: true);

    _animation = Tween<double>(begin: pi / 8.2, end: pi / 9).animate(_animationController);

    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  void dispose() {
    _model.dispose();
    _animationController.dispose();

    // Show the status bar again when the widget is disposed
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.manual,
        overlays: SystemUiOverlay.values);

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => _model.unfocusNode.canRequestFocus
          ? FocusScope.of(context).requestFocus(_model.unfocusNode)
          : FocusScope.of(context).unfocus(),
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: FlutterFlowTheme.of(context).primary,
        body: Stack(
          children: [
            wrapWithModel(
              model: _model.blurBotModel,
              updateCallback: () => setState(() {}),
              child: BlurBotWidget(),
            ),
            Column(
              mainAxisSize: MainAxisSize.max,
              children: [
                Expanded(
                  flex: 2,
                  child: AnimatedBuilder(
                    animation: _animation,
                    builder: (context, child) {
                      return Transform.rotate(
                        angle: _animation.value,
                        child: Image.asset(
                          'assets/images/hero_image.png',
                          fit: BoxFit.cover,
                          width: double.infinity,
                        ),
                      );
                    },
                  ),
                ),
                Align(
                  alignment: AlignmentDirectional(0.0, 1.0),
                  child: Padding(
                    padding: EdgeInsetsDirectional.fromSTEB(30.0, 140.0, 30.0, 40.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
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
                                useGoogleFonts:
                                    GoogleFonts.asMap().containsKey('SF Pro Display'),
                                lineHeight: 1.2,
                              ),
                        ),
                        SizedBox(height: 10.0),
                        Text(
                          "Your Personal growth journey with AI that listens to your every word",
                          style: TextStyle(
                            color: Color.fromARGB(255, 101, 101, 101),
                            fontSize: 14.0,
                            fontWeight: FontWeight.w700,
                            height: 1.5,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: EdgeInsetsDirectional.fromSTEB(0.0, 20.0, 0.0, 20.0),
                  child: Material(
                    elevation: 4.0,
                    shape: CircleBorder(),
                    child: InkWell(
                      splashColor: Colors.transparent,
                      focusColor: Colors.transparent,
                      hoverColor: Colors.transparent,
                      highlightColor: Colors.transparent,
                      mouseCursor: SystemMouseCursors.click,
                      onTap: () async {
                        // Check if Bluetooth permission is granted
                        PermissionStatus bluetoothStatus = await Permission.bluetooth.status;
                        if (bluetoothStatus.isGranted) {
                          // Bluetooth permission is already granted
                          // Request notification permission
                          PermissionStatus notificationStatus = await Permission.notification.request();

                          // Navigate to the 'scanDevices' screen
                          context.goNamed('findDevices');
                        } else {
                          // Bluetooth permission is not granted
                          if (await Permission.bluetooth.request().isGranted) {
                            // Bluetooth permission is granted now
                            // Request notification permission
                            PermissionStatus notificationStatus = await Permission.notification.request();

                            // Navigate to the 'scanDevices' screen
                            context.goNamed('findDevices');
                          } else {
                            // Bluetooth permission is denied
                            // Show a dialog to inform the user and provide an action to open app settings
                            showDialog(
                              context: context,
                              builder: (BuildContext context) {
                                return AlertDialog(
                                  backgroundColor: Colors.grey[900],
                                  title: Text(
                                    'Bluetooth Required',
                                    style: TextStyle(
                                      color: Colors.white,
                                      fontSize: 20,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                  content: Text(
                                    'This app needs Bluetooth to function properly. Please enable it in the settings.',
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
                                      child: Text(
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
                            colors: [
                              Colors.white,
                              Colors.white.withOpacity(0.0)
                            ],
                            stops: [0.9, 1.0],
                          ).createShader(bounds);
                        },
                        child: Container(
                          width: 100,
                          height: 100,
                          decoration: BoxDecoration(
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
                                      child: Icon(
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
          ],
        ),
      ),
    );
  }
}
