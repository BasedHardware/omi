import 'dart:io';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:provider/provider.dart';

class DesktopAuthScreen extends StatefulWidget {
  final VoidCallback onSignIn;

  const DesktopAuthScreen({super.key, required this.onSignIn});

  @override
  State<DesktopAuthScreen> createState() => _DesktopAuthScreenState();
}

class _DesktopAuthScreenState extends State<DesktopAuthScreen> {
  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return Scaffold(
      backgroundColor: ResponsiveHelper.backgroundPrimary,
      body: Container(
        decoration: BoxDecoration(
          gradient: responsive.backgroundGradient,
        ),
        child: SafeArea(
          child: Center(
            child: Container(
              constraints: const BoxConstraints(maxWidth: 480),
              padding: responsive.contentPadding(basePadding: 40),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // Logo/Icon with minimal design
                  Container(
                    width: 88,
                    height: 88,
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.backgroundSecondary,
                      borderRadius: BorderRadius.circular(24),
                    ),
                    child: Assets.images.logoTransparent.image(
                      width: 88,
                      height: 88,
                    ),
                  ),

                  SizedBox(height: responsive.spacing(baseSpacing: 32)),

                  // Title with clean typography
                  Text(
                    'Welcome to Omi',
                    style: responsive.headlineLarge.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                    textAlign: TextAlign.center,
                  ),

                  SizedBox(height: responsive.spacing(baseSpacing: 12)),

                  // Subtitle with minimal styling
                  Text(
                    'Your personal growth journey with AI that listens to your every word.',
                    style: responsive.bodyLarge.copyWith(
                      color: ResponsiveHelper.textSecondary,
                    ),
                    textAlign: TextAlign.center,
                  ),

                  SizedBox(height: responsive.spacing(baseSpacing: 48)),

                  // Auth buttons with loading state
                  Consumer<AuthenticationProvider>(
                    builder: (context, provider, child) {
                      return Column(
                        children: [
                          // Loading indicator
                          SizedBox(
                            height: 32,
                            child: provider.loading
                                ? const CircularProgressIndicator(
                                    valueColor: AlwaysStoppedAnimation(ResponsiveHelper.purplePrimary),
                                  )
                                : null,
                          ),

                          SizedBox(height: responsive.spacing(baseSpacing: 24)),

                          // Apple Sign In (if available)
                          if (Platform.isMacOS) ...[
                            _DesktopSignInButton(
                              icon: Icons.apple,
                              title: 'Continue with Apple',
                              onTap: provider.loading ? null : () => _handleAppleSignIn(provider),
                              isEnabled: !provider.loading,
                            ),
                            SizedBox(height: responsive.spacing(baseSpacing: 16)),
                          ],

                          // Google Sign In
                          _DesktopSignInButton(
                            icon: Icons.g_mobiledata,
                            title: 'Continue with Google',
                            onTap: provider.loading ? null : () => _handleGoogleSignIn(provider),
                            isEnabled: !provider.loading,
                          ),

                          SizedBox(height: responsive.spacing(baseSpacing: 24)),

                          // Terms and privacy with clickable links
                          RichText(
                            textAlign: TextAlign.center,
                            text: TextSpan(
                              style: responsive.bodySmall.copyWith(
                                color: ResponsiveHelper.textTertiary,
                              ),
                              children: [
                                const TextSpan(text: 'By continuing, you agree to our '),
                                TextSpan(
                                  text: 'Terms of Service',
                                  style: responsive.bodySmall.copyWith(
                                    color: ResponsiveHelper.textSecondary,
                                    decoration: TextDecoration.underline,
                                  ),
                                  recognizer: TapGestureRecognizer()..onTap = provider.openTermsOfService,
                                ),
                                const TextSpan(text: ' and '),
                                TextSpan(
                                  text: 'Privacy Policy',
                                  style: responsive.bodySmall.copyWith(
                                    color: ResponsiveHelper.textSecondary,
                                    decoration: TextDecoration.underline,
                                  ),
                                  recognizer: TapGestureRecognizer()..onTap = provider.openPrivacyPolicy,
                                ),
                                const TextSpan(text: '.'),
                              ],
                            ),
                          ),
                        ],
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _handleAppleSignIn(AuthenticationProvider provider) {
    _showConsentDialog(
      context,
      authMethod: 'apple',
      onContinue: () async {
        final user = FirebaseAuth.instance.currentUser;
        if (user != null && user.isAnonymous && SharedPreferencesUtil().hasPersonaCreated) {
          await provider.linkWithApple();
          if (mounted) {
            SharedPreferencesUtil().hasOmiDevice = true;
            SharedPreferencesUtil().verifiedPersonaId = null;
            widget.onSignIn();
          }
        } else {
          provider.onAppleSignIn(widget.onSignIn);
        }
      },
    );
  }

  void _handleGoogleSignIn(AuthenticationProvider provider) {
    _showConsentDialog(
      context,
      authMethod: 'google',
      onContinue: () async {
        final user = FirebaseAuth.instance.currentUser;
        if (user != null && user.isAnonymous && SharedPreferencesUtil().hasPersonaCreated) {
          await provider.linkWithGoogle();
          if (mounted) {
            SharedPreferencesUtil().hasOmiDevice = true;
            SharedPreferencesUtil().verifiedPersonaId = null;
            widget.onSignIn();
          }
        } else {
          provider.onGoogleSignIn(widget.onSignIn);
        }
      },
    );
  }

  void _showConsentDialog(
    BuildContext context, {
    required String authMethod,
    required VoidCallback onContinue,
  }) {
    final responsive = ResponsiveHelper(context);

    showDialog(
      context: context,
      barrierDismissible: true,
      barrierColor: Colors.black.withOpacity(0.6),
      builder: (BuildContext context) {
        return Dialog(
          backgroundColor: Colors.transparent,
          insetPadding: EdgeInsets.all(responsive.spacing(baseSpacing: 24)),
          child: Container(
            constraints: const BoxConstraints(maxWidth: 520),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary,
              borderRadius: BorderRadius.circular(responsive.radiusLarge),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.5),
                width: 1,
              ),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.25),
                  blurRadius: 32,
                  offset: const Offset(0, 16),
                ),
                BoxShadow(
                  color: ResponsiveHelper.purplePrimary.withOpacity(0.1),
                  blurRadius: 16,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(responsive.radiusLarge),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Header with gradient background
                  Container(
                    padding: EdgeInsets.all(responsive.spacing(baseSpacing: 32)),
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: [
                          ResponsiveHelper.backgroundTertiary,
                          ResponsiveHelper.backgroundSecondary,
                        ],
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Title with icon
                        Row(
                          children: [
                            Container(
                              padding: EdgeInsets.all(responsive.spacing(baseSpacing: 8)),
                              decoration: BoxDecoration(
                                color: ResponsiveHelper.purplePrimary.withOpacity(0.1),
                                borderRadius: BorderRadius.circular(responsive.radiusSmall),
                              ),
                              child: Icon(
                                Icons.privacy_tip_outlined,
                                color: ResponsiveHelper.purplePrimary,
                                size: 20,
                              ),
                            ),
                            SizedBox(width: responsive.spacing(baseSpacing: 12)),
                            Expanded(
                              child: Text(
                                'Data & Privacy',
                                style: responsive.titleLarge.copyWith(
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ],
                        ),

                        SizedBox(height: responsive.spacing(baseSpacing: 16)),

                        // Auth method indicator with enhanced design
                        Container(
                          padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
                            borderRadius: BorderRadius.circular(responsive.radiusSmall),
                            border: Border.all(
                              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                              width: 1,
                            ),
                          ),
                          child: Row(
                            children: [
                              Container(
                                padding: EdgeInsets.all(responsive.spacing(baseSpacing: 10)),
                                decoration: BoxDecoration(
                                  color: authMethod == 'apple' ? Colors.white : const Color(0xFF4285F4),
                                  borderRadius: BorderRadius.circular(responsive.radiusSmall),
                                  boxShadow: [
                                    BoxShadow(
                                      color: Colors.black.withOpacity(0.1),
                                      blurRadius: 4,
                                      offset: const Offset(0, 2),
                                    ),
                                  ],
                                ),
                                child: Icon(
                                  authMethod == 'apple' ? Icons.apple : Icons.g_mobiledata,
                                  color: authMethod == 'apple' ? Colors.black : Colors.white,
                                  size: 20,
                                ),
                              ),
                              SizedBox(width: responsive.spacing(baseSpacing: 12)),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      'Continue with ${authMethod == 'apple' ? 'Apple' : 'Google'}',
                                      style: responsive.bodyLarge.copyWith(
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                    SizedBox(height: responsive.spacing(baseSpacing: 4)),
                                    Text(
                                      'Secure authentication via ${authMethod == 'apple' ? 'Apple ID' : 'Google Account'}',
                                      style: responsive.bodySmall.copyWith(
                                        color: ResponsiveHelper.textTertiary,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),

                  // Content area
                  Container(
                    padding: EdgeInsets.all(responsive.spacing(baseSpacing: 32)),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Main consent message with better formatting
                        Container(
                          padding: EdgeInsets.all(responsive.spacing(baseSpacing: 20)),
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                            borderRadius: BorderRadius.circular(responsive.radiusSmall),
                            border: Border.all(
                              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                              width: 1,
                            ),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Icon(
                                    Icons.info_outline,
                                    color: ResponsiveHelper.purplePrimary,
                                    size: 20,
                                  ),
                                  SizedBox(width: responsive.spacing(baseSpacing: 8)),
                                  Text(
                                    'What we collect',
                                    style: responsive.bodyLarge.copyWith(
                                      fontWeight: FontWeight.w500,
                                      color: ResponsiveHelper.textPrimary,
                                    ),
                                  ),
                                ],
                              ),
                              SizedBox(height: responsive.spacing(baseSpacing: 12)),
                              Text(
                                'By continuing, your conversations, recordings, and personal information will be securely stored on our servers to provide AI-powered insights and enable all app features.',
                                style: responsive.bodyMedium.copyWith(
                                  height: 1.5,
                                  color: ResponsiveHelper.textSecondary,
                                ),
                              ),
                            ],
                          ),
                        ),

                        SizedBox(height: responsive.spacing(baseSpacing: 20)),

                        // Privacy links with enhanced design
                        Container(
                          padding: EdgeInsets.all(responsive.spacing(baseSpacing: 16)),
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.2),
                            borderRadius: BorderRadius.circular(responsive.radiusSmall),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Icon(
                                    Icons.shield_outlined,
                                    color: ResponsiveHelper.textTertiary,
                                    size: 16,
                                  ),
                                  SizedBox(width: responsive.spacing(baseSpacing: 8)),
                                  Text(
                                    'Data Protection',
                                    style: responsive.bodyMedium.copyWith(
                                      fontWeight: FontWeight.w500,
                                      color: ResponsiveHelper.textSecondary,
                                    ),
                                  ),
                                ],
                              ),
                              SizedBox(height: responsive.spacing(baseSpacing: 8)),
                              RichText(
                                text: TextSpan(
                                  style: responsive.bodySmall.copyWith(
                                    color: ResponsiveHelper.textTertiary,
                                    height: 1.4,
                                  ),
                                  children: [
                                    const TextSpan(text: 'Your data is protected and governed by our '),
                                    TextSpan(
                                      text: 'Privacy Policy',
                                      style: responsive.bodySmall.copyWith(
                                        color: ResponsiveHelper.purplePrimary,
                                        decoration: TextDecoration.underline,
                                        fontWeight: FontWeight.w500,
                                      ),
                                      recognizer: TapGestureRecognizer()
                                        ..onTap = () {
                                          context.read<AuthenticationProvider>().openPrivacyPolicy();
                                        },
                                    ),
                                    const TextSpan(text: ' and '),
                                    TextSpan(
                                      text: 'Terms of Service',
                                      style: responsive.bodySmall.copyWith(
                                        color: ResponsiveHelper.purplePrimary,
                                        decoration: TextDecoration.underline,
                                        fontWeight: FontWeight.w500,
                                      ),
                                      recognizer: TapGestureRecognizer()
                                        ..onTap = () {
                                          context.read<AuthenticationProvider>().openTermsOfService();
                                        },
                                    ),
                                    const TextSpan(text: '.'),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),

                        SizedBox(height: responsive.spacing(baseSpacing: 32)),

                        // Enhanced action buttons
                        Row(
                          children: [
                            // Cancel button with better styling
                            Expanded(
                              child: Container(
                                decoration: BoxDecoration(
                                  border: Border.all(
                                    color: ResponsiveHelper.backgroundTertiary,
                                    width: 1,
                                  ),
                                  borderRadius: BorderRadius.circular(responsive.radiusSmall),
                                ),
                                child: TextButton(
                                  onPressed: () => Navigator.of(context).pop(),
                                  style: TextButton.styleFrom(
                                    foregroundColor: ResponsiveHelper.textSecondary,
                                    padding: EdgeInsets.symmetric(
                                      vertical: responsive.spacing(baseSpacing: 16),
                                    ),
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(responsive.radiusSmall),
                                    ),
                                  ),
                                  child: Text(
                                    'Cancel',
                                    style: responsive.labelMedium.copyWith(
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ),
                              ),
                            ),

                            SizedBox(width: responsive.spacing(baseSpacing: 16)),

                            // Continue button with enhanced gradient and shadow
                            Expanded(
                              flex: 2,
                              child: Container(
                                decoration: BoxDecoration(
                                  gradient: responsive.purpleGradient,
                                  borderRadius: BorderRadius.circular(responsive.radiusSmall),
                                  boxShadow: [
                                    BoxShadow(
                                      color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                                      blurRadius: 8,
                                      offset: const Offset(0, 4),
                                    ),
                                  ],
                                ),
                                child: ElevatedButton.icon(
                                  onPressed: () {
                                    Navigator.of(context).pop();
                                    onContinue();
                                  },
                                  icon: Icon(
                                    authMethod == 'apple' ? Icons.apple : Icons.g_mobiledata,
                                    size: 18,
                                  ),
                                  label: Text(
                                    'Continue with ${authMethod == 'apple' ? 'Apple' : 'Google'}',
                                    style: responsive.labelMedium.copyWith(
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: Colors.transparent,
                                    foregroundColor: Colors.white,
                                    shadowColor: Colors.transparent,
                                    padding: EdgeInsets.symmetric(
                                      vertical: responsive.spacing(baseSpacing: 16),
                                      horizontal: responsive.spacing(baseSpacing: 20),
                                    ),
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(responsive.radiusSmall),
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
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _DesktopSignInButton extends StatefulWidget {
  final IconData icon;
  final String title;
  final VoidCallback? onTap;
  final bool isEnabled;

  const _DesktopSignInButton({
    required this.icon,
    required this.title,
    required this.onTap,
    this.isEnabled = true,
  });

  @override
  State<_DesktopSignInButton> createState() => _DesktopSignInButtonState();
}

class _DesktopSignInButtonState extends State<_DesktopSignInButton> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: widget.isEnabled ? widget.onTap : null,
            borderRadius: BorderRadius.circular(responsive.radiusSmall),
            child: Container(
              width: double.infinity,
              padding: EdgeInsets.symmetric(
                horizontal: responsive.spacing(baseSpacing: 24),
                vertical: responsive.spacing(baseSpacing: 16),
              ),
              decoration: BoxDecoration(
                color: _isHovered && widget.isEnabled
                    ? ResponsiveHelper.backgroundTertiary
                    : ResponsiveHelper.backgroundSecondary,
                borderRadius: BorderRadius.circular(responsive.radiusSmall),
                border: Border.all(
                  color: _isHovered && widget.isEnabled
                      ? ResponsiveHelper.purplePrimary.withOpacity(0.3)
                      : ResponsiveHelper.backgroundTertiary,
                  width: 1,
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    widget.icon,
                    color: widget.isEnabled ? ResponsiveHelper.textPrimary : ResponsiveHelper.textQuaternary,
                    size: 20,
                  ),
                  SizedBox(width: responsive.spacing(baseSpacing: 12)),
                  Text(
                    widget.title,
                    style: responsive.labelMedium.copyWith(
                      color: widget.isEnabled ? ResponsiveHelper.textPrimary : ResponsiveHelper.textQuaternary,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
