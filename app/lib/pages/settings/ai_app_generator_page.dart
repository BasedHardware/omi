import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/settings/ai_app_generator_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

class AiAppGeneratorPage extends StatefulWidget {
  const AiAppGeneratorPage({super.key});

  @override
  State<AiAppGeneratorPage> createState() => _AiAppGeneratorPageState();
}

class _AiAppGeneratorPageState extends State<AiAppGeneratorPage> {
  final TextEditingController _promptController = TextEditingController();
  final FocusNode _promptFocusNode = FocusNode();
  bool _isDescriptionExpanded = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = context.read<AiAppGeneratorProvider>();
      provider.setAppProvider(context.read<AppProvider>());
      provider.fetchSamplePrompts();
    });
  }

  @override
  void dispose() {
    _promptController.dispose();
    _promptFocusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AiAppGeneratorProvider>(
      builder: (context, provider, _) {
        // Show generated app view if we have generated content
        if (provider.hasGeneratedApp) {
          return _buildGeneratedAppView(provider);
        }

        // Show main input view
        return _buildInputView(provider);
      },
    );
  }

  Widget _buildInputView(AiAppGeneratorProvider provider) {
    final isGenerating = provider.isGenerating;

    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Scaffold(
        backgroundColor: const Color(0xFF0D0D0D),
        body: SafeArea(
          child: Column(
            children: [
              // Header with close button
              Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    GestureDetector(
                      onTap: () {
                        provider.clear();
                        Navigator.pop(context);
                      },
                      child: Container(
                        width: 36,
                        height: 36,
                        decoration: BoxDecoration(
                          color: const Color(0xFF1C1C1E),
                          borderRadius: BorderRadius.circular(18),
                        ),
                        child: const Center(
                          child: FaIcon(
                            FontAwesomeIcons.xmark,
                            color: Colors.white,
                            size: 16,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              // Center content
              Expanded(
                child: isGenerating
                    ? _buildGenerationProgressView(provider)
                    : Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          // "Try something like..." text
                          Text(
                            context.l10n.trySomethingLike,
                            style: TextStyle(
                              color: Colors.grey.shade500,
                              fontSize: 15,
                            ),
                          ),
                          const SizedBox(height: 20),

                          // Suggestion cards (with shimmer when loading)
                          SizedBox(
                            height: 160,
                            child: provider.isLoadingPrompts
                                ? ListView.builder(
                                    scrollDirection: Axis.horizontal,
                                    padding: const EdgeInsets.symmetric(horizontal: 20),
                                    itemCount: 3,
                                    itemBuilder: (context, index) {
                                      return _buildShimmerCard();
                                    },
                                  )
                                : ListView.builder(
                                    scrollDirection: Axis.horizontal,
                                    padding: const EdgeInsets.symmetric(horizontal: 20),
                                    itemCount: provider.samplePrompts.length,
                                    itemBuilder: (context, index) {
                                      return _buildSuggestionCard(
                                        provider.samplePrompts[index],
                                        provider,
                                      );
                                    },
                                  ),
                          ),

                          // Error message
                          if (provider.errorMessage != null) ...[
                            const SizedBox(height: 24),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 32),
                              child: Text(
                                provider.errorMessage!,
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                  color: Color(0xFFDC2626),
                                  fontSize: 14,
                                ),
                              ),
                            ),
                          ],
                        ],
                      ),
              ),

              // Bottom input bar
              _buildBottomInputBar(provider),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildGenerationProgressView(AiAppGeneratorProvider provider) {
    final steps = [
      (context.l10n.creatingPlan, GenerationStep.creatingPlan),
      (context.l10n.developingLogic, GenerationStep.developingLogic),
      (context.l10n.designingApp, GenerationStep.designingApp),
      (context.l10n.generatingIconStep, GenerationStep.generatingIcon),
      (context.l10n.finalTouches, GenerationStep.finalTouches),
    ];

    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        children: [
          const SizedBox(height: 20),

          // App preview card (building up)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: const Color(0xFF1C1C1E),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: const Color(0xFF2A2A2E), width: 1),
            ),
            child: Column(
              children: [
                // Icon with progress
                Stack(
                  alignment: Alignment.center,
                  children: [
                    Container(
                      width: 100,
                      height: 100,
                      decoration: BoxDecoration(
                        color: const Color(0xFF2A2A2E),
                        borderRadius: BorderRadius.circular(24),
                        image: provider.generatedIconBytes != null
                            ? DecorationImage(
                                image: MemoryImage(provider.generatedIconBytes!),
                                fit: BoxFit.cover,
                              )
                            : null,
                      ),
                      child: provider.generatedIconBytes == null
                          ? Center(
                              child: provider.currentStep.index >= GenerationStep.generatingIcon.index
                                  ? const SizedBox(
                                      width: 28,
                                      height: 28,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2.5,
                                        valueColor: AlwaysStoppedAnimation(Color(0xFF6366F1)),
                                      ),
                                    )
                                  : FaIcon(FontAwesomeIcons.wandMagicSparkles, color: Colors.grey.shade600, size: 28),
                            )
                          : null,
                    ),
                    // Progress indicator overlay
                    if (provider.generatedIconBytes == null)
                      Positioned(
                        bottom: -8,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: const Color(0xFF1C1C1E),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: const Color(0xFF2A2A2E)),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              SizedBox(
                                width: 12,
                                height: 12,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  value: (provider.currentStepIndex + 1) / provider.totalSteps,
                                  backgroundColor: Colors.grey.shade800,
                                  valueColor: const AlwaysStoppedAnimation(Color(0xFF6366F1)),
                                ),
                              ),
                              const SizedBox(width: 6),
                              Text(
                                '${((provider.currentStepIndex + 1) / provider.totalSteps * 100).round()}%',
                                style: const TextStyle(
                                  color: Colors.white70,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 24),

                // App name (shimmer if not ready)
                provider.generatedName != null
                    ? Text(
                        provider.generatedName!,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 22,
                          fontWeight: FontWeight.w600,
                        ),
                        textAlign: TextAlign.center,
                      )
                    : Shimmer.fromColors(
                        baseColor: const Color(0xFF2A2A2E),
                        highlightColor: const Color(0xFF3A3A3E),
                        child: Container(
                          height: 24,
                          width: 160,
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(6),
                          ),
                        ),
                      ),
                const SizedBox(height: 12),

                // Category badge (shimmer if not ready)
                provider.generatedCategory != null
                    ? Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: const Color(0xFF6366F1).withOpacity(0.2),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          provider.getCategoryDisplayName(),
                          style: const TextStyle(
                            color: Color(0xFF8B5CF6),
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      )
                    : Shimmer.fromColors(
                        baseColor: const Color(0xFF2A2A2E),
                        highlightColor: const Color(0xFF3A3A3E),
                        child: Container(
                          height: 28,
                          width: 100,
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                      ),
              ],
            ),
          ),

          const SizedBox(height: 24),

          // Progress stepper
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: const Color(0xFF1C1C1E),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: const Color(0xFF2A2A2E), width: 1),
            ),
            child: Column(
              children: steps.asMap().entries.map((entry) {
                final index = entry.key;
                final stepName = entry.value.$1;
                final step = entry.value.$2;
                final isActive = provider.currentStep == step;
                final isCompleted = provider.currentStep.index > step.index;
                final isLast = index == steps.length - 1;

                return Column(
                  children: [
                    Row(
                      children: [
                        // Step indicator
                        Container(
                          width: 32,
                          height: 32,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: isCompleted
                                ? const Color(0xFF6366F1)
                                : isActive
                                    ? const Color(0xFF6366F1).withOpacity(0.2)
                                    : const Color(0xFF2A2A2E),
                            border: isActive ? Border.all(color: const Color(0xFF6366F1), width: 2) : null,
                          ),
                          child: Center(
                            child: isCompleted
                                ? const FaIcon(FontAwesomeIcons.check, color: Colors.white, size: 12)
                                : isActive
                                    ? const SizedBox(
                                        width: 14,
                                        height: 14,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          valueColor: AlwaysStoppedAnimation(Color(0xFF6366F1)),
                                        ),
                                      )
                                    : Container(
                                        width: 8,
                                        height: 8,
                                        decoration: BoxDecoration(
                                          shape: BoxShape.circle,
                                          color: Colors.grey.shade600,
                                        ),
                                      ),
                          ),
                        ),
                        const SizedBox(width: 14),

                        // Step text
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                stepName,
                                style: TextStyle(
                                  color: isActive || isCompleted ? Colors.white : Colors.grey.shade600,
                                  fontSize: 15,
                                  fontWeight: isActive ? FontWeight.w600 : FontWeight.w400,
                                ),
                              ),
                              if (isActive) ...[
                                const SizedBox(height: 2),
                                Shimmer.fromColors(
                                  baseColor: Colors.grey.shade600,
                                  highlightColor: Colors.grey.shade400,
                                  child: Text(
                                    context.l10n.processing,
                                    style: TextStyle(
                                      color: Colors.grey.shade500,
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

                    // Connector line
                    if (!isLast)
                      Padding(
                        padding: const EdgeInsets.only(left: 15),
                        child: Row(
                          children: [
                            Container(
                              width: 2,
                              height: 24,
                              decoration: BoxDecoration(
                                color: isCompleted ? const Color(0xFF6366F1) : const Color(0xFF2A2A2E),
                                borderRadius: BorderRadius.circular(1),
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                );
              }).toList(),
            ),
          ),

          const SizedBox(height: 24),

          // Capabilities preview (show after designing step)
          if (provider.generatedCapabilities != null && provider.generatedCapabilities!.isNotEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF1C1C1E),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: const Color(0xFF2A2A2E), width: 1),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    context.l10n.features,
                    style: TextStyle(
                      color: Colors.grey.shade500,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.5,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: provider.getCapabilityDisplayNames().map((cap) {
                      return Container(
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                        decoration: BoxDecoration(
                          color: const Color(0xFF2A2A2E),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Text(
                          cap,
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 13,
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildSuggestionCard(String title, AiAppGeneratorProvider provider) {
    return Container(
      width: 260,
      margin: const EdgeInsets.only(right: 12),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w500,
              height: 1.4,
            ),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
          const Spacer(),
          GestureDetector(
            onTap: () {
              HapticFeedback.lightImpact();
              _promptController.text = title;
              _promptFocusNode.requestFocus();
              setState(() {});
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: BoxDecoration(
                color: const Color(0xFF2A2A2E),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    context.l10n.tryIt,
                    style: TextStyle(
                      color: Colors.grey.shade400,
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(width: 4),
                  FaIcon(
                    FontAwesomeIcons.chevronRight,
                    color: Colors.grey.shade400,
                    size: 12,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildShimmerCard() {
    return Shimmer.fromColors(
      baseColor: const Color(0xFF1C1C1E),
      highlightColor: const Color(0xFF2A2A2E),
      child: Container(
        width: 260,
        margin: const EdgeInsets.only(right: 12),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              height: 16,
              width: 200,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(4),
              ),
            ),
            const SizedBox(height: 10),
            Container(
              height: 16,
              width: 160,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(4),
              ),
            ),
            const SizedBox(height: 10),
            Container(
              height: 16,
              width: 120,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(4),
              ),
            ),
            const Spacer(),
            Container(
              height: 36,
              width: 80,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(20),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBottomInputBar(AiAppGeneratorProvider provider) {
    final hasText = _promptController.text.trim().isNotEmpty;
    final isGenerating = provider.isGenerating;

    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      child: Container(
        padding: EdgeInsets.only(left: 20, right: (hasText || isGenerating) ? 12 : 20, top: 6, bottom: 6),
        decoration: BoxDecoration(
          color: const Color(0xFF1C1C1E),
          borderRadius: BorderRadius.circular(28),
        ),
        child: Row(
          children: [
            // Text input
            Expanded(
              child: isGenerating
                  ? Padding(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      child: Shimmer.fromColors(
                        baseColor: Colors.grey.shade600,
                        highlightColor: Colors.grey.shade400,
                        child: Text(
                          provider.state == GenerationState.generatingApp
                              ? context.l10n.creatingYourApp
                              : context.l10n.generatingIcon,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                    )
                  : TextField(
                      controller: _promptController,
                      focusNode: _promptFocusNode,
                      maxLines: 3,
                      minLines: 1,
                      textInputAction: TextInputAction.newline,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        height: 1.6,
                      ),
                      decoration: InputDecoration(
                        hintText: context.l10n.whatShouldWeMake,
                        hintStyle: TextStyle(
                          color: Colors.grey.shade600,
                          fontSize: 16,
                        ),
                        border: InputBorder.none,
                        contentPadding: const EdgeInsets.symmetric(vertical: 8),
                      ),
                      onChanged: (_) => setState(() {}),
                    ),
            ),

            // Send button or loading indicator
            if (hasText || isGenerating) ...[
              const SizedBox(width: 12),
              isGenerating
                  ? const SizedBox(
                      width: 44,
                      height: 44,
                      child: Padding(
                        padding: EdgeInsets.all(10),
                        child: CircularProgressIndicator(
                          strokeWidth: 2.5,
                          valueColor: AlwaysStoppedAnimation(Color(0xFF6366F1)),
                        ),
                      ),
                    )
                  : GestureDetector(
                      onTap: () => _generateApp(provider),
                      child: Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: const Color(0xFF6366F1),
                          borderRadius: BorderRadius.circular(22),
                        ),
                        child: const Center(
                          child: FaIcon(
                            FontAwesomeIcons.arrowUp,
                            color: Colors.white,
                            size: 18,
                          ),
                        ),
                      ),
                    ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildGeneratedAppView(AiAppGeneratorProvider provider) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D0D0D),
      body: SafeArea(
        child: Column(
          children: [
            // Header
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  GestureDetector(
                    onTap: () => provider.clear(),
                    child: Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: const Color(0xFF1C1C1E),
                        borderRadius: BorderRadius.circular(18),
                      ),
                      child: const Center(
                        child: FaIcon(
                          FontAwesomeIcons.arrowLeft,
                          color: Colors.white,
                          size: 16,
                        ),
                      ),
                    ),
                  ),
                  const Spacer(),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                        colors: [Color(0xFFFF6B35), Color(0xFFFF8C42)],
                      ),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Text(
                      'BETA',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  GestureDetector(
                    onTap: () {
                      provider.clear();
                      Navigator.pop(context);
                    },
                    child: Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: const Color(0xFF1C1C1E),
                        borderRadius: BorderRadius.circular(18),
                      ),
                      child: const Center(
                        child: FaIcon(
                          FontAwesomeIcons.xmark,
                          color: Colors.white,
                          size: 16,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),

            // Content
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: Column(
                  children: [
                    // App preview card
                    _buildAppPreviewCard(provider),
                    const SizedBox(height: 20),

                    // App settings
                    _buildAppSettings(provider),
                  ],
                ),
              ),
            ),

            // Bottom action
            _buildCreateButton(provider),
          ],
        ),
      ),
    );
  }

  Widget _buildAppPreviewCard(AiAppGeneratorProvider provider) {
    final capabilities = provider.generatedCapabilities ?? [];
    final hasChat = capabilities.contains('chat');
    final hasMemories = capabilities.contains('memories');

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Top row: Icon + Info
          SizedBox(
            height: 100,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Icon with refresh button
                Stack(
                  clipBehavior: Clip.none,
                  children: [
                    Container(
                      width: 100,
                      height: 100,
                      decoration: BoxDecoration(
                        color: const Color(0xFF2A2A2E),
                        borderRadius: BorderRadius.circular(24),
                        image: provider.generatedIconBytes != null
                            ? DecorationImage(
                                image: MemoryImage(provider.generatedIconBytes!),
                                fit: BoxFit.cover,
                              )
                            : null,
                      ),
                      child: provider.generatedIconBytes == null
                          ? const Center(
                              child: FaIcon(FontAwesomeIcons.cube, color: Colors.grey, size: 32),
                            )
                          : null,
                    ),
                    Positioned(
                      right: -6,
                      bottom: -6,
                      child: GestureDetector(
                        onTap: provider.isLoading ? null : () => provider.regenerateIcon(),
                        child: Container(
                          padding: const EdgeInsets.all(8),
                          decoration: BoxDecoration(
                            color: const Color(0xFF6366F1),
                            borderRadius: BorderRadius.circular(12),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withOpacity(0.3),
                                blurRadius: 8,
                                offset: const Offset(0, 2),
                              ),
                            ],
                          ),
                          child: const FaIcon(
                            FontAwesomeIcons.arrowsRotate,
                            color: Colors.white,
                            size: 14,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(width: 16),

                // App info
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      // Name & Category
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            provider.generatedName ?? context.l10n.appName,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 20,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            provider.getCategoryDisplayName(),
                            style: TextStyle(
                              color: Colors.grey.shade400,
                              fontSize: 14,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),

                      // Badges row
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          // Public/Private badge
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: const Color(0xFF6366F1).withOpacity(0.15),
                              borderRadius: BorderRadius.circular(16),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                FaIcon(
                                  provider.makePublic ? FontAwesomeIcons.globe : FontAwesomeIcons.lock,
                                  color: const Color(0xFF8B5CF6),
                                  size: 12,
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  provider.makePublic ? context.l10n.publicLabel : context.l10n.privateLabel,
                                  style: const TextStyle(
                                    color: Color(0xFF8B5CF6),
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ],
                            ),
                          ),

                          // Price badge
                          if (provider.isPaid)
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                              decoration: BoxDecoration(
                                color: const Color(0xFF22C55E).withOpacity(0.15),
                                borderRadius: BorderRadius.circular(16),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const FaIcon(
                                    FontAwesomeIcons.dollarSign,
                                    color: Color(0xFF22C55E),
                                    size: 12,
                                  ),
                                  Text(
                                    '\$${provider.price.toStringAsFixed(0)} / Month',
                                    style: const TextStyle(
                                      color: Color(0xFF22C55E),
                                      fontSize: 12,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ],
                              ),
                            )
                          else
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                              decoration: BoxDecoration(
                                color: const Color(0xFF22C55E).withOpacity(0.15),
                                borderRadius: BorderRadius.circular(16),
                              ),
                              child: Text(
                                context.l10n.free,
                                style: const TextStyle(
                                  color: Color(0xFF22C55E),
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
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

          const SizedBox(height: 24),

          // Description section
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Description',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 10),
              GestureDetector(
                onTap: () {
                  setState(() {
                    _isDescriptionExpanded = !_isDescriptionExpanded;
                  });
                },
                child: Text(
                  provider.generatedDescription ?? '',
                  style: TextStyle(
                    color: Colors.grey.shade400,
                    fontSize: 14,
                    height: 1.6,
                  ),
                  maxLines: _isDescriptionExpanded ? null : 3,
                  overflow: _isDescriptionExpanded ? TextOverflow.visible : TextOverflow.ellipsis,
                ),
              ),
            ],
          ),

          const SizedBox(height: 24),

          // Features section
          if (hasMemories || hasChat) ...[
            const Text(
              'Features',
              style: TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 12),

            // Memories feature
            if (hasMemories)
              _buildFeatureRow(
                icon: FontAwesomeIcons.fileLines,
                description: context.l10n.tailoredConversationSummaries,
              ),

            // Chat feature
            if (hasChat)
              _buildFeatureRow(
                icon: FontAwesomeIcons.comments,
                description: context.l10n.customChatbotPersonality,
              ),
          ],
        ],
      ),
    );
  }

  Widget _buildFeatureRow({
    required IconData icon,
    required String description,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: const BoxDecoration(
              color: Color(0xFF2A2A2E),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: FaIcon(
                icon,
                color: Colors.white,
                size: 16,
              ),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              description,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAppSettings(AiAppGeneratorProvider provider) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF1C1C1E),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Public toggle
          _buildSettingRow(
            icon: FontAwesomeIcons.globe,
            title: context.l10n.makePublic,
            subtitle: provider.makePublic ? context.l10n.anyoneCanDiscover : context.l10n.onlyYouCanUse,
            value: provider.makePublic,
            onChanged: (v) => provider.setMakePublic(v),
            activeColor: const Color(0xFF6366F1),
          ),

          Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Divider(color: Colors.grey.shade800, height: 1),
          ),

          // Paid toggle
          _buildSettingRow(
            icon: FontAwesomeIcons.dollarSign,
            title: context.l10n.paidApp,
            subtitle: provider.isPaid ? context.l10n.usersPayToUse : context.l10n.freeForEveryone,
            value: provider.isPaid,
            onChanged: (v) => provider.setIsPaid(v),
            activeColor: const Color(0xFF22C55E),
          ),

          // Price input
          if (provider.isPaid) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              decoration: BoxDecoration(
                color: const Color(0xFF2A2A2E),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Row(
                children: [
                  const Text(
                    '\$',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 20,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 20,
                        fontWeight: FontWeight.w600,
                      ),
                      decoration: InputDecoration(
                        hintText: '0.00',
                        hintStyle: TextStyle(
                          color: Colors.grey.shade600,
                          fontSize: 20,
                        ),
                        border: InputBorder.none,
                        isDense: true,
                        contentPadding: EdgeInsets.zero,
                      ),
                      onChanged: (value) {
                        final price = double.tryParse(value) ?? 0.0;
                        provider.setPrice(price);
                      },
                    ),
                  ),
                  Text(
                    context.l10n.perMonthLabel,
                    style: TextStyle(
                      color: Colors.grey.shade500,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildSettingRow({
    required IconData icon,
    required String title,
    required String subtitle,
    required bool value,
    required ValueChanged<bool> onChanged,
    required Color activeColor,
  }) {
    return Row(
      children: [
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: const Color(0xFF2A2A2E),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Center(child: FaIcon(icon, color: Colors.grey.shade400, size: 16)),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                subtitle,
                style: TextStyle(
                  color: Colors.grey.shade500,
                  fontSize: 13,
                ),
              ),
            ],
          ),
        ),
        Switch(
          value: value,
          onChanged: onChanged,
          activeColor: activeColor,
        ),
      ],
    );
  }

  Widget _buildCreateButton(AiAppGeneratorProvider provider) {
    final isDisabled = provider.isLoading || provider.generatedIconBytes == null;

    return Container(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
      child: GestureDetector(
        onTap: isDisabled ? null : () => _submitApp(provider),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 16),
          decoration: BoxDecoration(
            color: isDisabled ? const Color(0xFF2A2A2E) : const Color(0xFF6366F1),
            borderRadius: BorderRadius.circular(16),
          ),
          child: provider.state == GenerationState.submitting
              ? Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor: AlwaysStoppedAnimation(Colors.white),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Text(
                      context.l10n.creating,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                )
              : Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const FaIcon(FontAwesomeIcons.circleCheck, color: Colors.white, size: 18),
                    const SizedBox(width: 10),
                    Text(
                      context.l10n.createApp,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }

  Future<void> _generateApp(AiAppGeneratorProvider provider) async {
    FocusScope.of(context).unfocus();
    await provider.generateApp(_promptController.text);
  }

  Future<void> _submitApp(AiAppGeneratorProvider provider) async {
    final appId = await provider.submitGeneratedApp();
    if (appId != null && mounted) {
      // Get the app and navigate to detail page (same as normal app creation flow)
      App? app = await context.read<AppProvider>().getAppFromId(appId);
      if (app != null && mounted && context.mounted) {
        Navigator.pop(context); // Close AI generator page
        routeToPage(context, AppDetailPage(app: app));
      }
    }
  }
}
