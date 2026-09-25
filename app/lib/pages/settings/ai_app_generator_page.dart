import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/settings/ai_app_generator_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/app_localizations_helper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/ui/ui.dart';

class AiAppGeneratorPage extends StatelessWidget {
  const AiAppGeneratorPage({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(create: (_) => AiAppGeneratorProvider(), child: const _AiAppGeneratorPageView());
  }
}

class _AiAppGeneratorPageView extends StatefulWidget {
  const _AiAppGeneratorPageView();

  @override
  State<_AiAppGeneratorPageView> createState() => _AiAppGeneratorPageState();
}

class _AiAppGeneratorPageState extends State<_AiAppGeneratorPageView> {
  final TextEditingController _promptController = TextEditingController();
  final FocusNode _promptFocusNode = FocusNode();
  bool _isDescriptionExpanded = false;

  @override
  void initState() {
    super.initState();
    PlatformManager.instance.analytics.aiAppGeneratorPageOpened();
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
        // One way back, the same on screen and from the system: the generated app steps back to the
        // prompt (it has not been created yet, so leaving would lose it); the prompt leaves the page.
        return PopScope(
          canPop: !provider.hasGeneratedApp,
          onPopInvokedWithResult: (didPop, _) {
            if (!didPop) provider.clear();
          },
          child: provider.hasGeneratedApp ? _buildGeneratedAppView(provider) : _buildInputView(provider),
        );
      },
    );
  }

  Widget _buildInputView(AiAppGeneratorProvider provider) {
    final isGenerating = provider.isGenerating;

    return GestureDetector(
      onTap: () => FocusScope.of(context).unfocus(),
      child: Scaffold(
        backgroundColor: OmiColors.surface0,
        // Pushed page: one leading back.
        appBar: AppBar(
          leading: OmiBackButton(
            onPressed: () {
              provider.clear();
              Navigator.pop(context);
            },
          ),
        ),
        body: SafeArea(
          top: false,
          child: Column(
            children: [
              Expanded(
                child: isGenerating
                    ? _buildGenerationProgressView(provider)
                    : Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(
                            context.l10n.trySomethingLike,
                            style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                          ),
                          const SizedBox(height: OmiSpacing.lg),

                          // Suggestion cards (shimmer while they load)
                          SizedBox(
                            height: 160,
                            child: ListView.builder(
                              scrollDirection: Axis.horizontal,
                              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg),
                              itemCount: provider.isLoadingPrompts ? 3 : provider.samplePrompts.length,
                              itemBuilder: (context, index) => provider.isLoadingPrompts
                                  ? const _SuggestionCardShimmer()
                                  : _buildSuggestionCard(provider.samplePrompts[index]),
                            ),
                          ),

                          if (provider.errorMessage != null) ...[
                            const SizedBox(height: OmiSpacing.xl),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxl),
                              child: Text(
                                provider.errorMessage!,
                                textAlign: TextAlign.center,
                                style: OmiType.footnote.copyWith(color: OmiColors.danger),
                              ),
                            ),
                          ],
                        ],
                      ),
              ),
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
    final progress = (provider.currentStepIndex + 1) / provider.totalSteps;

    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
      child: Column(
        children: [
          const SizedBox(height: OmiSpacing.lg),

          // App preview card (building up)
          _Card(
            padding: const EdgeInsets.all(OmiSpacing.xl),
            child: Column(
              children: [
                Stack(
                  alignment: Alignment.center,
                  clipBehavior: Clip.none,
                  children: [
                    _AppIconTile(
                      iconBytes: provider.generatedIconBytes,
                      placeholder: provider.currentStep.index >= GenerationStep.generatingIcon.index
                          ? const OmiSpinner()
                          : const FaIcon(FontAwesomeIcons.wandMagicSparkles, color: OmiColors.textTertiary, size: 28),
                    ),
                    if (provider.generatedIconBytes == null)
                      Positioned(
                        bottom: -8,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: OmiSpacing.xxs),
                          decoration: BoxDecoration(
                            color: OmiColors.surface1,
                            borderRadius: OmiRadius.mdAll,
                            border: Border.all(color: OmiColors.border),
                          ),
                          child: Text(
                            '${(progress * 100).round()}%',
                            style:
                                OmiType.caption.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: OmiSpacing.xl),

                // App name (shimmer until it is ready)
                provider.generatedName != null
                    ? Text(
                        provider.generatedName!,
                        style: OmiType.title3,
                        textAlign: TextAlign.center,
                      )
                    : const _ShimmerBlock(width: 160, height: 24),
                const SizedBox(height: OmiSpacing.sm),

                // Category badge (shimmer until it is ready)
                provider.generatedCategory != null
                    ? _Badge(label: _categoryName(provider))
                    : const _ShimmerBlock(width: 100, height: 28, radius: OmiRadius.mdAll),
              ],
            ),
          ),

          const SizedBox(height: OmiSpacing.xl),

          // Progress stepper
          _Card(
            child: Column(
              children: [
                for (final (index, (stepName, step)) in steps.indexed)
                  _buildStepRow(
                    name: stepName,
                    isActive: provider.currentStep == step,
                    isCompleted: provider.currentStep.index > step.index,
                    isLast: index == steps.length - 1,
                  ),
              ],
            ),
          ),

          const SizedBox(height: OmiSpacing.xl),

          // Capabilities preview (after the designing step)
          if (provider.generatedCapabilities != null && provider.generatedCapabilities!.isNotEmpty)
            _Card(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    context.l10n.features,
                    style: OmiType.footnote.copyWith(
                      color: OmiColors.textTertiary,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0.5,
                    ),
                  ),
                  const SizedBox(height: OmiSpacing.sm),
                  Wrap(
                    spacing: OmiSpacing.xs,
                    runSpacing: OmiSpacing.xs,
                    children: [
                      for (final capability in _capabilityNames(provider))
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: OmiSpacing.xs),
                          decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.pillAll),
                          child: Text(capability, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                        ),
                    ],
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildStepRow({
    required String name,
    required bool isActive,
    required bool isCompleted,
    required bool isLast,
  }) {
    return Column(
      children: [
        Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: isCompleted ? OmiColors.accent : OmiColors.surface2,
                border: isActive ? Border.all(color: OmiColors.accent, width: 2) : null,
              ),
              child: Center(
                child: isCompleted
                    ? const FaIcon(FontAwesomeIcons.check, color: OmiColors.onAccent, size: 12)
                    : isActive
                        ? const OmiSpinner(size: OmiSpinnerSize.small)
                        : Container(
                            width: 8,
                            height: 8,
                            decoration: const BoxDecoration(shape: BoxShape.circle, color: OmiColors.textTertiary),
                          ),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    style: OmiType.subhead.copyWith(
                      color: isActive || isCompleted ? OmiColors.textPrimary : OmiColors.textTertiary,
                      fontWeight: isActive ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                  if (isActive) ...[
                    const SizedBox(height: 2),
                    ShimmerWithTimeout(
                      baseColor: OmiColors.textTertiary,
                      highlightColor: OmiColors.textSecondary,
                      child: Text(context.l10n.processing, style: OmiType.footnote),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
        if (!isLast)
          Padding(
            padding: const EdgeInsets.only(left: 15),
            child: Row(
              children: [
                Container(
                  width: 2,
                  height: OmiSpacing.xl,
                  color: isCompleted ? OmiColors.accent : OmiColors.surface2,
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _buildSuggestionCard(String title) {
    return Container(
      width: 260,
      margin: const EdgeInsets.only(right: OmiSpacing.sm),
      padding: const EdgeInsets.all(OmiSpacing.lg),
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: OmiType.callout.copyWith(fontWeight: FontWeight.w500, height: 1.4),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
          const Spacer(),
          OmiButton.secondary(
            label: context.l10n.tryIt,
            size: OmiButtonSize.compact,
            onPressed: () {
              OmiHaptics.light();
              _promptController.text = title;
              _promptFocusNode.requestFocus();
              setState(() {});
            },
          ),
        ],
      ),
    );
  }

  Widget _buildBottomInputBar(AiAppGeneratorProvider provider) {
    final hasText = _promptController.text.trim().isNotEmpty;
    final isGenerating = provider.isGenerating;

    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, OmiSpacing.md),
      child: Container(
        padding: EdgeInsets.only(
          left: OmiSpacing.lg,
          right: (hasText || isGenerating) ? OmiSpacing.xxs : OmiSpacing.lg,
          top: 6,
          bottom: 6,
        ),
        decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.pillAll),
        child: Row(
          children: [
            Expanded(
              child: isGenerating
                  ? Padding(
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      child: ShimmerWithTimeout(
                        baseColor: OmiColors.textTertiary,
                        highlightColor: OmiColors.textSecondary,
                        child: Text(
                          provider.state == GenerationState.generatingApp
                              ? context.l10n.creatingYourApp
                              : context.l10n.generatingIcon,
                          style: OmiType.callout.copyWith(fontWeight: FontWeight.w500),
                        ),
                      ),
                    )
                  : TextField(
                      controller: _promptController,
                      focusNode: _promptFocusNode,
                      maxLines: 3,
                      minLines: 1,
                      textInputAction: TextInputAction.newline,
                      style: OmiType.callout.copyWith(height: 1.6),
                      decoration: InputDecoration(
                        hintText: context.l10n.whatShouldWeMake,
                        hintStyle: OmiType.callout.copyWith(color: OmiColors.textTertiary),
                        border: InputBorder.none,
                        contentPadding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
                      ),
                      onChanged: (_) => setState(() {}),
                    ),
            ),
            if (hasText || isGenerating) ...[
              const SizedBox(width: OmiSpacing.xs),
              isGenerating
                  ? const SizedBox.square(dimension: kOmiMinTapTarget, child: Center(child: OmiSpinner()))
                  : OmiIconButton.filled(
                      icon: const FaIcon(FontAwesomeIcons.arrowUp, size: 18),
                      label: context.l10n.send,
                      color: OmiColors.onAccent,
                      fillColor: OmiColors.accent,
                      onPressed: () => _generateApp(provider),
                    ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildGeneratedAppView(AiAppGeneratorProvider provider) {
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        // Back steps to the prompt (the page's PopScope clears the generated app).
        leading: const OmiBackButton(),
        actions: [
          Container(
            margin: const EdgeInsetsDirectional.only(end: OmiSpacing.md),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
            child: Text(
              context.l10n.beta,
              style: OmiType.caption.copyWith(fontWeight: FontWeight.w700, color: OmiColors.textSecondary),
            ),
          ),
        ],
      ),
      body: SafeArea(
        top: false,
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(OmiSpacing.lg),
                child: Column(
                  children: [
                    _buildAppPreviewCard(provider),
                    const SizedBox(height: OmiSpacing.lg),
                    _buildAppSettings(provider),
                  ],
                ),
              ),
            ),
            _buildCreateButton(provider),
          ],
        ),
      ),
    );
  }

  Widget _buildAppPreviewCard(AiAppGeneratorProvider provider) {
    final l10n = context.l10n;
    final capabilities = provider.generatedCapabilities ?? [];
    final hasChat = capabilities.contains('chat');
    final hasMemories = capabilities.contains('memories');

    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Icon + name, category and badges
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Stack(
                clipBehavior: Clip.none,
                children: [
                  _AppIconTile(
                    iconBytes: provider.generatedIconBytes,
                    placeholder: const FaIcon(FontAwesomeIcons.cube, color: OmiColors.textTertiary, size: 32),
                  ),
                  Positioned(
                    right: -14,
                    bottom: -14,
                    child: OmiIconButton.filled(
                      icon: const FaIcon(FontAwesomeIcons.arrowsRotate, size: 14),
                      label: l10n.aiGenRegenerateIcon,
                      color: OmiColors.onAccent,
                      fillColor: OmiColors.accent,
                      diameter: 32,
                      onPressed: provider.isLoading ? null : () => provider.regenerateIcon(),
                    ),
                  ),
                ],
              ),
              const SizedBox(width: OmiSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(provider.generatedName ?? l10n.appName, style: OmiType.title3),
                    const SizedBox(height: OmiSpacing.xxs),
                    Text(
                      _categoryName(provider),
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(height: OmiSpacing.sm),
                    Wrap(
                      spacing: OmiSpacing.xs,
                      runSpacing: OmiSpacing.xs,
                      children: [
                        _Badge(
                          icon: provider.makePublic ? FontAwesomeIcons.globe : FontAwesomeIcons.lock,
                          label: provider.makePublic ? l10n.publicLabel : l10n.privateLabel,
                        ),
                        _Badge(
                          icon: provider.isPaid ? FontAwesomeIcons.dollarSign : null,
                          label: provider.isPaid ? '${provider.price.toStringAsFixed(0)} ${l10n.perMonth}' : l10n.free,
                          color: OmiColors.success,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),

          const SizedBox(height: OmiSpacing.xl),

          // Description (tap to expand)
          Text(l10n.description, style: OmiType.callout.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 10),
          Semantics(
            button: true,
            expanded: _isDescriptionExpanded,
            child: GestureDetector(
              onTap: () => setState(() => _isDescriptionExpanded = !_isDescriptionExpanded),
              child: Text(
                provider.generatedDescription ?? '',
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.6),
                maxLines: _isDescriptionExpanded ? null : 3,
                overflow: _isDescriptionExpanded ? TextOverflow.visible : TextOverflow.ellipsis,
              ),
            ),
          ),

          if (hasMemories || hasChat) ...[
            const SizedBox(height: OmiSpacing.xl),
            Text(l10n.features, style: OmiType.callout.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: OmiSpacing.sm),
            if (hasMemories)
              _buildFeatureRow(icon: FontAwesomeIcons.fileLines, description: l10n.tailoredConversationSummaries),
            if (hasChat) _buildFeatureRow(icon: FontAwesomeIcons.comments, description: l10n.customChatbotPersonality),
          ],
        ],
      ),
    );
  }

  Widget _buildFeatureRow({required FaIconData icon, required String description}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: const BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
            child: Center(child: FaIcon(icon, color: OmiColors.textPrimary, size: 16)),
          ),
          const SizedBox(width: 14),
          Expanded(child: Text(description, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600))),
        ],
      ),
    );
  }

  Widget _buildAppSettings(AiAppGeneratorProvider provider) {
    final l10n = context.l10n;
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildSettingRow(
            icon: FontAwesomeIcons.globe,
            title: l10n.makePublic,
            subtitle: provider.makePublic ? l10n.anyoneCanDiscover : l10n.onlyYouCanUse,
            value: provider.makePublic,
            onChanged: (v) => provider.setMakePublic(v),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(vertical: OmiSpacing.md),
            child: Divider(color: OmiColors.border, height: 1),
          ),
          _buildSettingRow(
            icon: FontAwesomeIcons.dollarSign,
            title: l10n.paidApp,
            subtitle: provider.isPaid ? l10n.usersPayToUse : l10n.freeForEveryone,
            value: provider.isPaid,
            onChanged: (v) => provider.setIsPaid(v),
          ),
          if (provider.isPaid) ...[
            const SizedBox(height: OmiSpacing.md),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
              decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
              child: Row(
                children: [
                  const Text('\$', style: OmiType.title3),
                  const SizedBox(width: OmiSpacing.xs),
                  Expanded(
                    child: TextField(
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      style: OmiType.title3,
                      decoration: InputDecoration(
                        hintText: l10n.pricePlaceholder,
                        hintStyle: OmiType.title3.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w400),
                        border: InputBorder.none,
                        isDense: true,
                        contentPadding: EdgeInsets.zero,
                      ),
                      onChanged: (value) => provider.setPrice(double.tryParse(value) ?? 0.0),
                    ),
                  ),
                  Text(l10n.perMonthLabel, style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildSettingRow({
    required FaIconData icon,
    required String title,
    required String subtitle,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    return MergeSemantics(
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
            child: Center(child: FaIcon(icon, color: OmiColors.textSecondary, size: 16)),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: OmiType.callout.copyWith(fontWeight: FontWeight.w500)),
                const SizedBox(height: 2),
                Text(subtitle, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
              ],
            ),
          ),
          OmiSwitch(value: value, onChanged: onChanged),
        ],
      ),
    );
  }

  Widget _buildCreateButton(AiAppGeneratorProvider provider) {
    final isDisabled = provider.isLoading || provider.generatedIconBytes == null;
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.sm, OmiSpacing.lg, OmiSpacing.lg),
      child: OmiButton(
        label: provider.state == GenerationState.submitting ? context.l10n.creating : context.l10n.createApp,
        expand: true,
        isLoading: provider.state == GenerationState.submitting,
        onPressed: isDisabled ? null : () => _submitApp(provider),
      ),
    );
  }

  String _categoryName(AiAppGeneratorProvider provider) {
    final id = provider.generatedCategory ?? 'other';
    return Category(id: id, title: provider.getCategoryDisplayName()).getLocalizedTitle(context);
  }

  List<String> _capabilityNames(AiAppGeneratorProvider provider) {
    final ids = provider.generatedCapabilities ?? const <String>[];
    final fallback = provider.getCapabilityDisplayNames();
    return [
      for (final (index, id) in ids.indexed)
        AppCapability(id: id, title: index < fallback.length ? fallback[index] : id).getLocalizedTitle(context),
    ];
  }

  Future<void> _generateApp(AiAppGeneratorProvider provider) async {
    FocusScope.of(context).unfocus();
    PlatformManager.instance.analytics.aiAppGeneratorPromptSubmitted(promptLength: _promptController.text.length);
    await provider.generateApp(_promptController.text);
    PlatformManager.instance.analytics.aiAppGeneratorAppGenerated(success: provider.hasGeneratedApp);
  }

  Future<void> _submitApp(AiAppGeneratorProvider provider) async {
    final appId = await provider.submitGeneratedApp();
    // The error text lives on the prompt view; the reader is on the generated view here.
    if (appId == null && mounted && provider.errorMessage != null) {
      OmiFeedback.error(context, provider.errorMessage!);
      return;
    }
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

/// A rounded [OmiColors.surface1] section of the generator page.
class _Card extends StatelessWidget {
  const _Card({required this.child, this.padding = const EdgeInsets.all(OmiSpacing.lg)});

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.xlAll,
        border: Border.all(color: OmiColors.border.withValues(alpha: 0.5)),
      ),
      child: child,
    );
  }
}

/// The generated app's 100pt icon, or [placeholder] until the icon exists.
class _AppIconTile extends StatelessWidget {
  const _AppIconTile({required this.iconBytes, required this.placeholder});

  final Uint8List? iconBytes;
  final Widget placeholder;

  @override
  Widget build(BuildContext context) {
    final bytes = iconBytes;
    return Container(
      width: 100,
      height: 100,
      decoration: BoxDecoration(
        color: OmiColors.surface2,
        borderRadius: OmiRadius.xlAll,
        image: bytes != null ? DecorationImage(image: MemoryImage(bytes), fit: BoxFit.cover) : null,
      ),
      child: bytes == null ? Center(child: placeholder) : null,
    );
  }
}

/// A small pill: category, visibility or price.
class _Badge extends StatelessWidget {
  const _Badge({required this.label, this.icon, this.color = OmiColors.textSecondary});

  final String label;
  final FaIconData? icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final icon = this.icon;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 6),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.15), borderRadius: OmiRadius.pillAll),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[FaIcon(icon, color: color, size: 12), const SizedBox(width: 6)],
          Text(label, style: OmiType.footnote.copyWith(color: color, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

/// A shimmering placeholder block for text that is still being generated.
class _ShimmerBlock extends StatelessWidget {
  const _ShimmerBlock({required this.width, required this.height, this.radius = OmiRadius.smAll});

  final double width;
  final double height;
  final BorderRadius radius;

  @override
  Widget build(BuildContext context) {
    return ShimmerWithTimeout(
      baseColor: OmiColors.surface2,
      highlightColor: OmiColors.surface3,
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(color: OmiColors.textPrimary, borderRadius: radius),
      ),
    );
  }
}

/// A suggestion card while the sample prompts load.
class _SuggestionCardShimmer extends StatelessWidget {
  const _SuggestionCardShimmer();

  @override
  Widget build(BuildContext context) {
    Widget line(double width) => Container(
          height: 16,
          width: width,
          decoration:
              BoxDecoration(color: OmiColors.textPrimary, borderRadius: BorderRadius.circular(OmiRadius.sm / 2)),
        );
    return ShimmerWithTimeout(
      baseColor: OmiColors.surface1,
      highlightColor: OmiColors.surface2,
      child: Container(
        width: 260,
        margin: const EdgeInsets.only(right: OmiSpacing.sm),
        padding: const EdgeInsets.all(OmiSpacing.lg),
        decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            line(200),
            const SizedBox(height: 10),
            line(160),
            const SizedBox(height: 10),
            line(120),
            const Spacer(),
            Container(
              height: 36,
              width: 80,
              decoration: const BoxDecoration(color: OmiColors.textPrimary, borderRadius: OmiRadius.pillAll),
            ),
          ],
        ),
      ),
    );
  }
}
