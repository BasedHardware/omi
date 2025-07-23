import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/ui/atoms/omi_button.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class DesktopLanguageScreen extends StatefulWidget {
  final VoidCallback onNext;
  final VoidCallback onBack;

  const DesktopLanguageScreen({
    super.key,
    required this.onNext,
    required this.onBack,
  });

  @override
  State<DesktopLanguageScreen> createState() => _DesktopLanguageScreenState();
}

class _DesktopLanguageScreenState extends State<DesktopLanguageScreen> with TickerProviderStateMixin {
  String? selectedLanguage;
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;
  final TextEditingController _searchController = TextEditingController();
  List<LanguageOption> filteredLanguages = [];
  final FocusNode _searchFocusNode = FocusNode();

  // Comprehensive flag mapping for all supported languages
  final Map<String, String> _languageFlags = {
    'en': '🇺🇸',
    'es': '🇪🇸',
    'zh': '🇨🇳',
    'hi': '🇮🇳',
    'pt': '🇵🇹',
    'ru': '🇷🇺',
    'ja': '🇯🇵',
    'de': '🇩🇪',
    'bg': '🇧🇬',
    'ca': '🇪🇸',
    'zh-TW': '🇹🇼',
    'zh-HK': '🇭🇰',
    'cs': '🇨🇿',
    'da': '🇩🇰',
    'nl': '🇳🇱',
    'et': '🇪🇪',
    'fi': '🇫🇮',
    'nl-BE': '🇧🇪',
    'fr': '🇫🇷',
    'de-CH': '🇨🇭',
    'el': '🇬🇷',
    'hu': '🇭🇺',
    'id': '🇮🇩',
    'it': '🇮🇹',
    'ko': '🇰🇷',
    'lv': '🇱🇻',
    'lt': '🇱🇹',
    'ms': '🇲🇾',
    'no': '🇳🇴',
    'pl': '🇵🇱',
    'ro': '🇷🇴',
    'sk': '🇸🇰',
    'sv': '🇸🇪',
    'th': '🇹🇭',
    'tr': '🇹🇷',
    'uk': '🇺🇦',
    'vi': '🇻🇳',
    'ar': '🇸🇦',
  };

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

    WidgetsBinding.instance.addPostFrameCallback((_) {
      final homeProvider = Provider.of<HomeProvider>(context, listen: false);
      // Only set selected language if user has previously saved one
      final savedLanguage = homeProvider.userPrimaryLanguage;
      if (savedLanguage != null && savedLanguage.isNotEmpty) {
        setState(() {
          selectedLanguage = savedLanguage;
        });
      }
      _buildLanguageList();
      _fadeController.forward();
    });

    _searchController.addListener(_onSearchChanged);
    _searchFocusNode.addListener(_onSearchFocusChanged);
  }

  @override
  void dispose() {
    _fadeController.dispose();
    _searchController.dispose();
    _searchFocusNode.dispose();
    super.dispose();
  }

  void _buildLanguageList() {
    final homeProvider = Provider.of<HomeProvider>(context, listen: false);
    filteredLanguages = homeProvider.availableLanguages.entries.map((entry) {
      return LanguageOption(
        code: entry.value,
        name: entry.key,
        flag: _languageFlags[entry.value] ?? '🌐',
      );
    }).toList();
  }

  void _onSearchChanged() {
    setState(() {
      final query = _searchController.text.toLowerCase();
      if (query.isEmpty) {
        _buildLanguageList();
      } else {
        final homeProvider = Provider.of<HomeProvider>(context, listen: false);
        filteredLanguages = homeProvider.availableLanguages.entries
            .where((entry) => entry.key.toLowerCase().contains(query) || entry.value.toLowerCase().contains(query))
            .map((entry) => LanguageOption(
                  code: entry.value,
                  name: entry.key,
                  flag: _languageFlags[entry.value] ?? '🌐',
                ))
            .toList();
      }
    });
  }

  void _onSearchFocusChanged() {
    setState(() {});
  }

  void _selectLanguage(String languageCode) {
    setState(() {
      selectedLanguage = languageCode;
    });
  }

  void _continueWithLanguage() async {
    if (selectedLanguage == null) {
      // Show error message like mobile version
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Please select your primary language'),
          backgroundColor: ResponsiveHelper.errorColor,
          behavior: SnackBarBehavior.floating,
          margin: const EdgeInsets.all(16),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      );
      return;
    }

    final homeProvider = Provider.of<HomeProvider>(context, listen: false);
    await homeProvider.updateUserPrimaryLanguage(selectedLanguage!);

    MixpanelManager().onboardingStepCompleted('Primary Language');
    widget.onNext();
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return SizedBox(
      width: double.infinity,
      height: double.infinity,
      child: Column(
        children: [
          // Header Section
          FadeTransition(
            opacity: _fadeAnimation,
            child: Container(
              padding: EdgeInsets.only(
                top: responsive.spacing(baseSpacing: 40),
                bottom: responsive.spacing(baseSpacing: 32),
              ),
              child: Column(
                children: [
                  Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(
                      color: const Color(0xFF1A1A1A),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Icon(
                      Icons.language_rounded,
                      color: Colors.white,
                      size: 28,
                    ),
                  ),
                  SizedBox(height: responsive.spacing(baseSpacing: 24)),
                  const Text(
                    'Choose your language',
                    style: TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.w600,
                      color: Colors.white,
                      letterSpacing: -0.5,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  SizedBox(height: responsive.spacing(baseSpacing: 8)),
                  const Text(
                    'Select your preferred language for the best Omi experience',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w400,
                      color: Color(0xFF9CA3AF),
                      height: 1.5,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
          ),

          FadeTransition(
            opacity: _fadeAnimation,
            child: Container(
              constraints: const BoxConstraints(
                maxWidth: 480,
              ),
              margin: const EdgeInsets.symmetric(
                horizontal: 40,
                vertical: 16,
              ),
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1A1A),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: _searchFocusNode.hasFocus
                        ? ResponsiveHelper.purplePrimary.withOpacity(0.6)
                        : const Color(0xFF2A2A2A),
                    width: 1,
                  ),
                ),
                child: TextField(
                  controller: _searchController,
                  focusNode: _searchFocusNode,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w400,
                  ),
                  decoration: const InputDecoration(
                    hintText: 'Search languages...',
                    hintStyle: TextStyle(
                      color: Color(0xFF6B7280),
                      fontSize: 15,
                    ),
                    prefixIcon: Icon(
                      Icons.search_rounded,
                      color: Color(0xFF6B7280),
                      size: 20,
                    ),
                    border: InputBorder.none,
                    contentPadding: EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 16,
                    ),
                  ),
                ),
              ),
            ),
          ),

          Expanded(
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: Container(
                constraints: const BoxConstraints(maxWidth: 520),
                margin: const EdgeInsets.symmetric(horizontal: 40),
                child: filteredLanguages.isEmpty
                    ? _buildEmptyState()
                    : ListView.builder(
                        padding: const EdgeInsets.only(
                          top: 8,
                          bottom: 100,
                        ),
                        itemCount: filteredLanguages.length,
                        itemBuilder: (context, index) {
                          final language = filteredLanguages[index];
                          final isSelected = selectedLanguage == language.code;

                          return _buildLanguageItem(
                            language: language,
                            isSelected: isSelected,
                            onTap: () => _selectLanguage(language.code),
                          );
                        },
                      ),
              ),
            ),
          ),

          Container(
            padding: const EdgeInsets.all(40),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    OmiButton(
                      label: selectedLanguage != null ? 'Continue' : 'Select a language',
                      onPressed: selectedLanguage != null ? _continueWithLanguage : null,
                      enabled: selectedLanguage != null,
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

  Widget _buildEmptyState() {
    return const Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.search_off_rounded,
            size: 48,
            color: Color(0xFF4B5563),
          ),
          SizedBox(height: 16),
          Text(
            'No languages found',
            style: TextStyle(
              color: Color(0xFF9CA3AF),
              fontSize: 16,
              fontWeight: FontWeight.w500,
            ),
          ),
          SizedBox(height: 4),
          Text(
            'Try a different search term',
            style: TextStyle(
              color: Color(0xFF6B7280),
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLanguageItem({
    required LanguageOption language,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 2),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(8),
          child: Container(
            padding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 12,
            ),
            decoration: BoxDecoration(
              color: isSelected ? const Color(0xFF1A1A1A) : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
              border: isSelected
                  ? Border.all(
                      color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                      width: 1,
                    )
                  : null,
            ),
            child: Row(
              children: [
                // Flag
                SizedBox(
                  width: 24,
                  height: 24,
                  child: Center(
                    child: Text(
                      language.flag,
                      style: const TextStyle(fontSize: 16),
                    ),
                  ),
                ),

                const SizedBox(width: 12),

                // Language name
                Expanded(
                  child: Text(
                    language.name,
                    style: TextStyle(
                      color: isSelected ? Colors.white : const Color(0xFFE5E7EB),
                      fontSize: 15,
                      fontWeight: isSelected ? FontWeight.w500 : FontWeight.w400,
                    ),
                  ),
                ),

                if (isSelected)
                  const Icon(
                    Icons.check_rounded,
                    color: ResponsiveHelper.purplePrimary,
                    size: 18,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class LanguageOption {
  final String code;
  final String name;
  final String flag;

  LanguageOption({
    required this.code,
    required this.name,
    required this.flag,
  });
}
