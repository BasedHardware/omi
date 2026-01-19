import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/logger.dart';

/// State enum for the AI app generation process
enum GenerationState {
  idle,
  generatingApp,
  generatingIcon,
  submitting,
  completed,
  error,
}

/// Enum for generation steps (for UI progress)
enum GenerationStep {
  creatingPlan,
  developingLogic,
  designingApp,
  generatingIcon,
  finalTouches,
}

/// Provider for the AI App Generator feature
class AiAppGeneratorProvider extends ChangeNotifier {
  AppProvider? appProvider;

  // State
  GenerationState _state = GenerationState.idle;
  String? _errorMessage;
  GenerationStep _currentStep = GenerationStep.creatingPlan;
  String _currentStepMessage = '';

  // Sample prompts
  List<String> _samplePrompts = [];
  bool _isLoadingPrompts = false;

  // Generated app data
  String? _generatedName;
  String? _generatedDescription;
  String? _generatedCategory;
  List<String>? _generatedCapabilities;
  String? _generatedChatPrompt;
  String? _generatedMemoryPrompt;
  Uint8List? _generatedIconBytes;
  String? _createdAppId;

  // User options
  bool _makePublic = false;
  bool _isPaid = false;
  double _price = 0.0;

  // Getters
  GenerationState get state => _state;
  String? get errorMessage => _errorMessage;
  GenerationStep get currentStep => _currentStep;
  String get currentStepMessage => _currentStepMessage;
  String? get generatedName => _generatedName;
  String? get generatedDescription => _generatedDescription;
  String? get generatedCategory => _generatedCategory;
  List<String>? get generatedCapabilities => _generatedCapabilities;
  String? get generatedChatPrompt => _generatedChatPrompt;
  String? get generatedMemoryPrompt => _generatedMemoryPrompt;
  Uint8List? get generatedIconBytes => _generatedIconBytes;
  String? get createdAppId => _createdAppId;
  bool get makePublic => _makePublic;
  bool get isPaid => _isPaid;
  double get price => _price;
  List<String> get samplePrompts => _samplePrompts;
  bool get isLoadingPrompts => _isLoadingPrompts;

  bool get isLoading =>
      _state == GenerationState.generatingApp ||
      _state == GenerationState.generatingIcon ||
      _state == GenerationState.submitting;

  /// Returns true when generating app/icon (but not when submitting)
  bool get isGenerating => _state == GenerationState.generatingApp || _state == GenerationState.generatingIcon;

  bool get isSubmitting => _state == GenerationState.submitting;

  bool get hasGeneratedApp =>
      _generatedName != null && _generatedDescription != null && _generatedIconBytes != null && !isGenerating;

  /// Get current step index (0-4)
  int get currentStepIndex => _currentStep.index;

  /// Get total steps count
  int get totalSteps => GenerationStep.values.length;

  void setAppProvider(AppProvider provider) {
    appProvider = provider;
  }

  /// Fetch AI-generated sample prompts
  Future<void> fetchSamplePrompts() async {
    if (_isLoadingPrompts) return;

    _isLoadingPrompts = true;
    notifyListeners();

    try {
      final prompts = await getGeneratedAppPrompts();
      if (prompts.isNotEmpty) {
        _samplePrompts = prompts;
      } else {
        // Fallback prompts
        _samplePrompts = [
          'A playful gratitude spinner for daily positivity',
          'Mind map organizer for my conversations',
          'Clone of Elon Musk for startup advice',
          'Fitness coach tracking workout discussions',
          'Language learning from daily conversations',
        ];
      }
    } catch (e) {
      Logger.debug('Error fetching sample prompts: $e');
      _samplePrompts = [
        'A playful gratitude spinner for daily positivity',
        'Mind map organizer for my conversations',
        'Clone of Elon Musk for startup advice',
        'Fitness coach tracking workout discussions',
        'Language learning from daily conversations',
      ];
    }

    _isLoadingPrompts = false;
    notifyListeners();
  }

  /// Helper to update step progress
  void _updateStep(GenerationStep step, String message) {
    _currentStep = step;
    _currentStepMessage = message;
    notifyListeners();
  }

  /// Generate app configuration from a prompt
  Future<bool> generateApp(String prompt) async {
    if (prompt.trim().isEmpty) {
      _errorMessage = 'Please enter a description for your app';
      notifyListeners();
      return false;
    }

    _state = GenerationState.generatingApp;
    _errorMessage = null;

    // Step 1: Creating plan
    _updateStep(GenerationStep.creatingPlan, 'Analyzing your idea...');

    try {
      // Small delay for UX
      await Future.delayed(const Duration(milliseconds: 500));

      // Step 2: Developing logic
      _updateStep(GenerationStep.developingLogic, 'Crafting app logic...');

      // Generate app configuration
      final appData = await generateAppFromPrompt(prompt);

      if (appData == null) {
        _state = GenerationState.error;
        _errorMessage = 'Failed to generate app. Please try again.';
        notifyListeners();
        return false;
      }

      // Step 3: Designing app
      _updateStep(GenerationStep.designingApp, 'Designing your app...');
      await Future.delayed(const Duration(milliseconds: 300));

      _generatedName = appData['name'] as String?;
      _generatedDescription = appData['description'] as String?;
      _generatedCategory = appData['category'] as String?;
      _generatedCapabilities = (appData['capabilities'] as List<dynamic>?)?.cast<String>();
      _generatedChatPrompt = appData['chat_prompt'] as String?;
      _generatedMemoryPrompt = appData['memory_prompt'] as String?;

      // Step 4: Generating icon
      _state = GenerationState.generatingIcon;
      _updateStep(GenerationStep.generatingIcon, 'Creating app icon...');

      final iconBase64 = await generateAppIcon(
        _generatedName ?? 'App',
        _generatedDescription ?? '',
        _generatedCategory ?? 'other',
      );

      if (iconBase64 != null) {
        _generatedIconBytes = base64Decode(iconBase64);
      }

      // Step 5: Final touches
      _updateStep(GenerationStep.finalTouches, 'Final touches...');
      await Future.delayed(const Duration(milliseconds: 300));

      _state = GenerationState.idle;
      notifyListeners();
      return true;
    } catch (e) {
      Logger.debug('Error generating app: $e');
      _state = GenerationState.error;
      _errorMessage = 'An error occurred: ${e.toString()}';
      notifyListeners();
      return false;
    }
  }

  /// Regenerate just the icon
  Future<bool> regenerateIcon() async {
    if (_generatedName == null || _generatedDescription == null) {
      return false;
    }

    _state = GenerationState.generatingIcon;
    _errorMessage = null;
    notifyListeners();

    try {
      final iconBase64 = await generateAppIcon(
        _generatedName!,
        _generatedDescription!,
        _generatedCategory ?? 'other',
      );

      if (iconBase64 != null) {
        _generatedIconBytes = base64Decode(iconBase64);
      }

      _state = GenerationState.idle;
      notifyListeners();
      return iconBase64 != null;
    } catch (e) {
      Logger.debug('Error regenerating icon: $e');
      _state = GenerationState.error;
      _errorMessage = 'Failed to regenerate icon';
      notifyListeners();
      return false;
    }
  }

  /// Submit the generated app to create it
  /// Returns the appId if successful, null otherwise
  Future<String?> submitGeneratedApp() async {
    if (!hasGeneratedApp || _generatedIconBytes == null) {
      _errorMessage = 'Please generate an app first';
      notifyListeners();
      return null;
    }

    _state = GenerationState.submitting;
    _errorMessage = null;
    notifyListeners();

    try {
      // Save icon bytes to a temporary file
      final tempDir = await getTemporaryDirectory();
      final iconFile = File('${tempDir.path}/generated_icon_${DateTime.now().millisecondsSinceEpoch}.png');
      await iconFile.writeAsBytes(_generatedIconBytes!);

      // Prepare app data
      Map<String, dynamic> appData = {
        'name': _generatedName,
        'description': _generatedDescription,
        'capabilities': _generatedCapabilities ?? ['chat'],
        'deleted': false,
        'uid': SharedPreferencesUtil().uid,
        'category': _generatedCategory ?? 'other',
        'private': !_makePublic,
        'is_paid': _isPaid,
        'price': _isPaid ? _price : 0.0,
        'payment_plan': _isPaid ? 'monthly_recurring' : null,
        'thumbnails': [],
      };

      // Add prompts based on capabilities
      if (_generatedCapabilities?.contains('chat') == true && _generatedChatPrompt != null) {
        appData['chat_prompt'] = _generatedChatPrompt;
      }
      if (_generatedCapabilities?.contains('memories') == true && _generatedMemoryPrompt != null) {
        appData['memory_prompt'] = _generatedMemoryPrompt;
      }

      // Submit the app
      final result = await submitAppServer(iconFile, appData);

      // Clean up temp file
      if (await iconFile.exists()) {
        await iconFile.delete();
      }

      if (result.$1) {
        _createdAppId = result.$3;
        _state = GenerationState.completed;
        AppSnackbar.showSnackbarSuccess('App created successfully! 🎉');

        // Refresh apps list
        await appProvider?.getApps();

        notifyListeners();
        return _createdAppId;
      } else {
        _state = GenerationState.error;
        _errorMessage = result.$2.isNotEmpty ? result.$2 : 'Failed to create app';
        notifyListeners();
        return null;
      }
    } catch (e) {
      Logger.debug('Error submitting app: $e');
      _state = GenerationState.error;
      _errorMessage = 'An error occurred while creating the app';
      notifyListeners();
      return null;
    }
  }

  /// Update generated field
  void updateName(String name) {
    _generatedName = name;
    notifyListeners();
  }

  void updateDescription(String description) {
    _generatedDescription = description;
    notifyListeners();
  }

  void updateCategory(String category) {
    _generatedCategory = category;
    notifyListeners();
  }

  void updateChatPrompt(String prompt) {
    _generatedChatPrompt = prompt;
    notifyListeners();
  }

  void updateMemoryPrompt(String prompt) {
    _generatedMemoryPrompt = prompt;
    notifyListeners();
  }

  void setMakePublic(bool value) {
    _makePublic = value;
    notifyListeners();
  }

  void setIsPaid(bool value) {
    _isPaid = value;
    if (!value) {
      _price = 0.0;
    }
    notifyListeners();
  }

  void setPrice(double value) {
    _price = value;
    notifyListeners();
  }

  /// Clear all generated data
  void clear() {
    _state = GenerationState.idle;
    _errorMessage = null;
    _generatedName = null;
    _generatedDescription = null;
    _generatedCategory = null;
    _generatedCapabilities = null;
    _generatedChatPrompt = null;
    _generatedMemoryPrompt = null;
    _generatedIconBytes = null;
    _createdAppId = null;
    _makePublic = false;
    _isPaid = false;
    _price = 0.0;
    notifyListeners();
  }

  /// Get category display name
  String getCategoryDisplayName() {
    final categories = {
      'conversation-analysis': 'Conversation Analysis',
      'personality-emulation': 'Personality Clone',
      'health-and-wellness': 'Health',
      'education-and-learning': 'Education',
      'communication-improvement': 'Communication',
      'emotional-and-mental-support': 'Emotional Support',
      'productivity-and-organization': 'Productivity',
      'entertainment-and-fun': 'Entertainment',
      'financial': 'Financial',
      'travel-and-exploration': 'Travel',
      'safety-and-security': 'Safety',
      'shopping-and-commerce': 'Shopping',
      'social-and-relationships': 'Social',
      'news-and-information': 'News',
      'utilities-and-tools': 'Utilities',
      'other': 'Other',
    };
    return categories[_generatedCategory] ?? _generatedCategory ?? 'Other';
  }

  /// Get capability display names
  List<String> getCapabilityDisplayNames() {
    if (_generatedCapabilities == null) return [];
    final capabilityNames = {
      'chat': 'Chat',
      'memories': 'Conversations',
      'external_integration': 'External Integration',
      'proactive_notification': 'Notifications',
    };
    return _generatedCapabilities!.map((c) => capabilityNames[c] ?? c).toList();
  }
}
