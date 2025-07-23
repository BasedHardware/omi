import 'package:flutter/material.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/ui/atoms/omi_text_input.dart';
import 'package:omi/ui/atoms/omi_button.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class DesktopNameScreen extends StatefulWidget {
  final VoidCallback onNext;
  final VoidCallback onBack;

  const DesktopNameScreen({
    super.key,
    required this.onNext,
    required this.onBack,
  });

  @override
  State<DesktopNameScreen> createState() => _DesktopNameScreenState();
}

class _DesktopNameScreenState extends State<DesktopNameScreen> with SingleTickerProviderStateMixin {
  final TextEditingController _nameController = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;

  bool _isValid = true;
  String _errorMessage = '';
  bool _hasInteracted = false;

  @override
  void initState() {
    super.initState();

    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );

    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _fadeController,
      curve: Curves.easeOut,
    ));

    // Load existing name if available
    final currentName = SharedPreferencesUtil().givenName;
    if (currentName.isNotEmpty) {
      _nameController.text = currentName;
      _hasInteracted = true;
    }

    _fadeController.forward();

    // Auto-focus the input field after animation
    Future.delayed(const Duration(milliseconds: 400), () {
      if (mounted) _focusNode.requestFocus();
    });

    _focusNode.addListener(_onFocusChanged);
  }

  @override
  void dispose() {
    _nameController.dispose();
    _focusNode.dispose();
    _fadeController.dispose();
    super.dispose();
  }

  void _onFocusChanged() {
    setState(() {});
  }

  void _validateAndProceed() {
    setState(() {
      _hasInteracted = true;
    });

    final name = _nameController.text.trim();

    if (name.isEmpty) {
      setState(() {
        _isValid = false;
        _errorMessage = 'Please enter your name';
      });
      return;
    }

    if (name.length < 2) {
      setState(() {
        _isValid = false;
        _errorMessage = 'Name must be at least 2 characters';
      });
      return;
    }

    // Save the name
    SharedPreferencesUtil().givenName = name;

    setState(() {
      _isValid = true;
      _errorMessage = '';
    });

    MixpanelManager().onboardingStepCompleted('Name');
    widget.onNext();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: double.infinity,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Expanded(
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(
                      color: const Color(0xFF1A1A1A),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Icon(
                      Icons.person_rounded,
                      color: Colors.white,
                      size: 28,
                    ),
                  ),
                  const SizedBox(height: 32),
                  const Text(
                    'What\'s your name?',
                    style: TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.w600,
                      color: Colors.white,
                      letterSpacing: -0.5,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  Container(
                    constraints: const BoxConstraints(maxWidth: 480),
                    padding: const EdgeInsets.symmetric(horizontal: 40),
                    child: const Text(
                      'Tell us how you\'d like to be addressed. This helps personalize your Omi experience.',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w400,
                        color: Color(0xFF9CA3AF),
                        height: 1.5,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ),
                  const SizedBox(height: 48),
                  Container(
                    constraints: const BoxConstraints(maxWidth: 400),
                    margin: const EdgeInsets.symmetric(horizontal: 40),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        OmiTextInput(
                          controller: _nameController,
                          focusNode: _focusNode,
                          hint: 'Enter your name',
                          onChanged: (_) {
                            if (_hasInteracted) setState(() {});
                          },
                        ),
                        if (_errorMessage.isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Row(
                            children: [
                              const Icon(
                                Icons.error_outline_rounded,
                                color: Color(0xFFDC2626),
                                size: 16,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                _errorMessage,
                                style: const TextStyle(
                                  color: Color(0xFFDC2626),
                                  fontSize: 14,
                                ),
                              ),
                            ],
                          ),
                        ],
                        if (_nameController.text.isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Align(
                            alignment: Alignment.centerRight,
                            child: Text(
                              '${_nameController.text.length} characters',
                              style: const TextStyle(
                                color: Color(0xFF6B7280),
                                fontSize: 12,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          Container(
            padding: const EdgeInsets.fromLTRB(40, 24, 40, 40),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    OmiButton(
                      label: 'Continue',
                      onPressed: _validateAndProceed,
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                OmiButton(
                  label: 'Back',
                  type: OmiButtonType.text,
                  onPressed: widget.onBack,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
