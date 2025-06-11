import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopPermissionsScreen extends StatefulWidget {
  final VoidCallback onNext;
  final VoidCallback onBack;

  const DesktopPermissionsScreen({
    super.key,
    required this.onNext,
    required this.onBack,
  });

  @override
  State<DesktopPermissionsScreen> createState() => _DesktopPermissionsScreenState();
}

class _DesktopPermissionsScreenState extends State<DesktopPermissionsScreen> {
  Map<Permission, PermissionStatus> permissionStatuses = {};
  bool isRequestingPermissions = false;

  final List<PermissionInfo> permissions = [
    PermissionInfo(
      permission: Permission.microphone,
      title: 'Microphone Access',
      description: 'Required for voice conversations and audio recording',
      icon: Icons.mic,
      isRequired: true,
    ),
    PermissionInfo(
      permission: Permission.notification,
      title: 'Notifications',
      description: 'Stay updated with important alerts and messages',
      icon: Icons.notifications,
      isRequired: false,
    ),
    PermissionInfo(
      permission: Permission.camera,
      title: 'Camera Access',
      description: 'Optional for video calls and visual features',
      icon: Icons.camera_alt,
      isRequired: false,
    ),
  ];

  @override
  void initState() {
    super.initState();
    _checkPermissionStatuses();
  }

  Future<void> _checkPermissionStatuses() async {
    final Map<Permission, PermissionStatus> statuses = {};
    for (final permissionInfo in permissions) {
      statuses[permissionInfo.permission] = await permissionInfo.permission.status;
    }

    if (mounted) {
      setState(() {
        permissionStatuses = statuses;
      });
    }
  }

  Future<void> _requestPermission(Permission permission) async {
    setState(() {
      isRequestingPermissions = true;
    });

    try {
      final status = await permission.request();
      if (mounted) {
        setState(() {
          permissionStatuses[permission] = status;
        });
      }
    } catch (e) {
      // Handle permission request error
      debugPrint('Error requesting permission: $e');
    } finally {
      if (mounted) {
        setState(() {
          isRequestingPermissions = false;
        });
      }
    }
  }

  void _continueWithPermissions() {
    // Check if all required permissions are granted
    final micPermission = permissionStatuses[Permission.microphone];
    if (micPermission != PermissionStatus.granted) {
      // Show warning but allow to continue
      _showPermissionWarning();
      return;
    }

    widget.onNext();
  }

  void _showPermissionWarning() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A1A),
        title: const Text(
          'Microphone Access Required',
          style: TextStyle(color: Colors.white),
        ),
        content: const Text(
          'Omi needs microphone access to function properly. You can grant this permission later in system settings.',
          style: TextStyle(color: Colors.grey),
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
              widget.onNext();
            },
            child: const Text(
              'Continue Anyway',
              style: TextStyle(color: Colors.grey),
            ),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.of(context).pop();
              _requestPermission(Permission.microphone);
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF667EEA),
            ),
            child: const Text('Grant Permission'),
          ),
        ],
      ),
    );
  }

  void _skipPermissions() {
    widget.onNext();
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return Center(
      child: Container(
        constraints: BoxConstraints(
          maxWidth: responsive.maxContainerWidth(baseMaxWidth: 600),
          maxHeight: responsive.safeAreaHeight,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Icon
              Container(
                width: responsive.iconSize(baseSize: 80, minSize: 60, maxSize: 100),
                height: responsive.iconSize(baseSize: 80, minSize: 60, maxSize: 100),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [
                      Color(0xFF667EEA),
                      Color(0xFF764BA2),
                    ],
                  ),
                  borderRadius:
                      BorderRadius.circular(responsive.spacing(baseSpacing: 20, minSpacing: 15, maxSpacing: 25)),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF667EEA).withOpacity(0.3),
                      blurRadius: responsive.spacing(baseSpacing: 15, minSpacing: 10, maxSpacing: 20),
                      offset: Offset(0, responsive.spacing(baseSpacing: 5, minSpacing: 3, maxSpacing: 7)),
                    ),
                  ],
                ),
                child: Icon(
                  Icons.security,
                  color: Colors.white,
                  size: responsive.iconSize(baseSize: 40, minSize: 30, maxSize: 50),
                ),
              ),

              SizedBox(height: responsive.spacing(baseSpacing: 32, minSpacing: 24, maxSpacing: 40)),

              // Title
              Text(
                'Grant permissions',
                style: responsive.titleMedium,
                textAlign: TextAlign.center,
              ),

              SizedBox(height: responsive.spacing(baseSpacing: 12, minSpacing: 8, maxSpacing: 16)),

              // Subtitle
              Text(
                'Enable features for the best Omi experience',
                style: responsive.bodyMedium,
                textAlign: TextAlign.center,
              ),

              SizedBox(height: responsive.spacing(baseSpacing: 40, minSpacing: 32, maxSpacing: 48)),

              // Permissions list
              ...permissions.map((permissionInfo) {
                final status = permissionStatuses[permissionInfo.permission];
                return Padding(
                  padding: EdgeInsets.only(bottom: responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20)),
                  child: _buildPermissionCard(
                    permissionInfo: permissionInfo,
                    status: status,
                    responsive: responsive,
                  ),
                );
              }).toList(),

              SizedBox(height: responsive.spacing(baseSpacing: 48, minSpacing: 32, maxSpacing: 64)),

              // Continue button
              Container(
                width: double.infinity,
                height: responsive.buttonHeight(),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [
                      Color(0xFF667EEA),
                      Color(0xFF764BA2),
                    ],
                  ),
                  borderRadius:
                      BorderRadius.circular(responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20)),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF667EEA).withOpacity(0.3),
                      blurRadius: responsive.spacing(baseSpacing: 12, minSpacing: 8, maxSpacing: 16),
                      offset: Offset(0, responsive.spacing(baseSpacing: 4, minSpacing: 3, maxSpacing: 6)),
                    ),
                  ],
                ),
                child: Material(
                  color: Colors.transparent,
                  child: InkWell(
                    borderRadius:
                        BorderRadius.circular(responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20)),
                    onTap: isRequestingPermissions ? null : _continueWithPermissions,
                    child: Center(
                      child: isRequestingPermissions
                          ? SizedBox(
                              width: responsive.iconSize(baseSize: 20, minSize: 16, maxSize: 24),
                              height: responsive.iconSize(baseSize: 20, minSize: 16, maxSize: 24),
                              child: const CircularProgressIndicator(
                                color: Colors.white,
                                strokeWidth: 2,
                              ),
                            )
                          : Text(
                              'Continue',
                              style: responsive.titleMedium,
                            ),
                    ),
                  ),
                ),
              ),

              SizedBox(height: responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20)),

              // Skip button
              TextButton(
                onPressed: isRequestingPermissions ? null : _skipPermissions,
                child: Text(
                  'Skip for now',
                  style: responsive.responsiveTextStyle(
                    baseFontSize: 16,
                    minFontSize: 14,
                    maxFontSize: 18,
                    color: Colors.grey.shade500,
                  ),
                ),
              ),

              SizedBox(height: responsive.spacing(baseSpacing: 24, minSpacing: 16, maxSpacing: 32)),

              // Back button
              TextButton(
                onPressed: isRequestingPermissions ? null : widget.onBack,
                child: Text(
                  'Back',
                  style: responsive.responsiveTextStyle(
                    baseFontSize: 16,
                    minFontSize: 14,
                    maxFontSize: 18,
                    color: Colors.grey.shade500,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPermissionCard({
    required PermissionInfo permissionInfo,
    required PermissionStatus? status,
    required ResponsiveHelper responsive,
  }) {
    final isGranted = status == PermissionStatus.granted;
    final isDenied = status == PermissionStatus.denied || status == PermissionStatus.permanentlyDenied;
    final isLoading = isRequestingPermissions;

    Color cardColor;
    Color borderColor;
    Color iconColor;
    IconData trailingIcon;

    if (isGranted) {
      cardColor = const Color(0xFF4CAF50).withOpacity(0.1);
      borderColor = const Color(0xFF4CAF50);
      iconColor = const Color(0xFF4CAF50);
      trailingIcon = Icons.check_circle;
    } else if (isDenied) {
      cardColor = Colors.red.withOpacity(0.1);
      borderColor = Colors.red.withOpacity(0.5);
      iconColor = Colors.red;
      trailingIcon = Icons.error;
    } else {
      cardColor = Colors.white.withOpacity(0.05);
      borderColor = Colors.white.withOpacity(0.1);
      iconColor = const Color(0xFF667EEA);
      trailingIcon = Icons.arrow_forward_ios;
    }

    return Container(
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20)),
        border: Border.all(color: borderColor, width: 1),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20)),
          onTap: (!isGranted && !isLoading) ? () => _requestPermission(permissionInfo.permission) : null,
          child: Container(
            padding: responsive.cardPadding(),
            child: Row(
              children: [
                // Permission icon
                Container(
                  width: responsive.iconSize(baseSize: 48, minSize: 40, maxSize: 56),
                  height: responsive.iconSize(baseSize: 48, minSize: 40, maxSize: 56),
                  decoration: BoxDecoration(
                    color: iconColor.withOpacity(0.2),
                    borderRadius:
                        BorderRadius.circular(responsive.spacing(baseSpacing: 12, minSpacing: 10, maxSpacing: 14)),
                  ),
                  child: Icon(
                    permissionInfo.icon,
                    color: iconColor,
                    size: responsive.iconSize(baseSize: 24, minSize: 20, maxSize: 28),
                  ),
                ),

                SizedBox(width: responsive.spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20)),

                // Permission info
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              permissionInfo.title,
                              style: responsive.responsiveTextStyle(
                                baseFontSize: 16,
                                minFontSize: 14,
                                maxFontSize: 18,
                                fontWeight: FontWeight.w600,
                                color: Colors.white,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          if (permissionInfo.isRequired)
                            Container(
                              padding: EdgeInsets.symmetric(
                                horizontal: responsive.spacing(baseSpacing: 8, minSpacing: 6, maxSpacing: 10),
                                vertical: responsive.spacing(baseSpacing: 2, minSpacing: 1, maxSpacing: 3),
                              ),
                              decoration: BoxDecoration(
                                color: const Color(0xFF667EEA).withOpacity(0.2),
                                borderRadius: BorderRadius.circular(
                                    responsive.spacing(baseSpacing: 8, minSpacing: 6, maxSpacing: 10)),
                              ),
                              child: Text(
                                'Required',
                                style: responsive.responsiveTextStyle(
                                  baseFontSize: 12,
                                  minFontSize: 10,
                                  maxFontSize: 14,
                                  color: const Color(0xFF667EEA),
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                        ],
                      ),
                      SizedBox(height: responsive.spacing(baseSpacing: 4, minSpacing: 3, maxSpacing: 6)),
                      Text(
                        permissionInfo.description,
                        style: responsive.bodySmall,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),

                SizedBox(width: responsive.spacing(baseSpacing: 12, minSpacing: 8, maxSpacing: 16)),

                // Status indicator
                Icon(
                  trailingIcon,
                  color: iconColor,
                  size: responsive.iconSize(baseSize: 20, minSize: 16, maxSize: 24),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class PermissionInfo {
  final Permission permission;
  final String title;
  final String description;
  final IconData icon;
  final bool isRequired;

  PermissionInfo({
    required this.permission,
    required this.title,
    required this.description,
    required this.icon,
    required this.isRequired,
  });
}
