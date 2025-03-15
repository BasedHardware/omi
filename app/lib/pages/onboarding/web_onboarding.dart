import 'package:flutter/material.dart';
import 'package:friend_private/pages/web_home_page.dart';
import 'package:friend_private/providers/web_auth_provider.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/widgets/sign_in_button.dart';
import 'package:provider/provider.dart';

/// Web-specific onboarding flow that doesn't rely on device connections
class WebOnboardingPage extends StatefulWidget {
  const WebOnboardingPage({Key? key}) : super(key: key);

  @override
  State<WebOnboardingPage> createState() => _WebOnboardingPageState();
}

class _WebOnboardingPageState extends State<WebOnboardingPage> {
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    debugPrint('WebOnboardingPage initialized');
    // Check if WebAuthenticationProvider is available
    WidgetsBinding.instance.addPostFrameCallback((_) {
      try {
        final authProvider = Provider.of<WebAuthenticationProvider>(context, listen: false);
        debugPrint('WebAuthenticationProvider found: ${authProvider.isSignedIn()}');
      } catch (e) {
        debugPrint('Error accessing WebAuthenticationProvider: $e');
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    debugPrint('Building WebOnboardingPage');

    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24.0),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  const SizedBox(height: 40),
                  // Use a placeholder icon instead of missing image
                  const Icon(
                    Icons.devices_rounded,
                    size: 120,
                    color: Colors.white,
                  ),
                  const SizedBox(height: 40),
                  const Text(
                    'Welcome to Omi',
                    style: TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'Scale yourself with Omi',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 16,
                      color: Colors.white70,
                    ),
                  ),
                  const SizedBox(height: 60),
                  _buildGetStartedButton(),
                  const SizedBox(height: 24),
                  _buildSignInOptions(),
                  const SizedBox(height: 40),
                  _buildTermsAndPrivacy(),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildGetStartedButton() {
    return SizedBox(
      width: double.infinity,
      child: ElevatedButton(
        onPressed: _isLoading ? null : _handleGetStarted,
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.white,
          foregroundColor: Colors.black,
          padding: const EdgeInsets.symmetric(vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
          ),
        ),
        child: _isLoading
            ? const SizedBox(
                height: 24,
                width: 24,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.black),
                ),
              )
            : const Text(
                'Get Started',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
              ),
      ),
    );
  }

  Widget _buildSignInOptions() {
    return Column(
      children: [
        const Text(
          'Already have an account?',
          style: TextStyle(
            color: Colors.white70,
            fontSize: 14,
          ),
        ),
        const SizedBox(height: 16),
        SignInButton.withGoogle(
          onTap: () => _handleSignIn(SignInMethod.google),
          title: 'Sign in with Google',
        ),
        const SizedBox(height: 12),
        SignInButton.withApple(
          onTap: () => _handleSignIn(SignInMethod.apple),
          title: 'Sign in with Apple',
        ),
      ],
    );
  }

  Widget _buildTermsAndPrivacy() {
    return Column(
      children: [
        const Text(
          'By continuing, you agree to our',
          style: TextStyle(
            color: Colors.white70,
            fontSize: 12,
          ),
        ),
        const SizedBox(height: 4),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            GestureDetector(
              onTap: () => context.read<WebAuthenticationProvider>().openTermsOfService(),
              child: const Text(
                'Terms of Service',
                style: TextStyle(
                  color: Colors.blue,
                  fontSize: 12,
                ),
              ),
            ),
            const Text(
              ' and ',
              style: TextStyle(
                color: Colors.white70,
                fontSize: 12,
              ),
            ),
            GestureDetector(
              onTap: () => context.read<WebAuthenticationProvider>().openPrivacyPolicy(),
              child: const Text(
                'Privacy Policy',
                style: TextStyle(
                  color: Colors.blue,
                  fontSize: 12,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  void _handleGetStarted() {
    setState(() {
      _isLoading = true;
    });
    
    debugPrint('Get Started button clicked');
    
    // Use a direct navigation approach without Firebase dependencies
    try {
      // Navigate directly without using WidgetsBinding
      Navigator.of(context).pushReplacement(
        PageRouteBuilder(
          pageBuilder: (context, animation, secondaryAnimation) => const WebHomePage(),
          transitionsBuilder: (context, animation, secondaryAnimation, child) {
            return FadeTransition(opacity: animation, child: child);
          },
        ),
      );
    } catch (e) {
      debugPrint('Error navigating to WebHomePage: $e');
      AppSnackbar.showSnackbarError('Error navigating to home page. Please try again.');
      
      // Reset loading state
      setState(() {
        _isLoading = false;
      });
    }
  }

  void _handleSignIn(SignInMethod method) {
    final authProvider = context.read<WebAuthenticationProvider>();
    
    switch (method) {
      case SignInMethod.google:
        authProvider.onGoogleSignIn(() {
          _onSignInSuccess();
        });
        break;
      case SignInMethod.apple:
        authProvider.onAppleSignIn(() {
          _onSignInSuccess();
        });
        break;
    }
  }

  void _onSignInSuccess() {
    AppSnackbar.showSnackbarSuccess('Successfully signed in');
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (context) => const WebHomePage()),
    );
  }
}

enum SignInMethod {
  google,
  apple,
}
