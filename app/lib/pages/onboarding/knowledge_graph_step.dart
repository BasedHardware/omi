import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_graph.dart';
import 'package:omi/mobile/native_ui/native_navigation_chrome.dart';
import 'package:omi/pages/memories/widgets/memory_graph_controller.dart';
import 'package:omi/pages/memories/widgets/memory_graph_native.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class OnboardingKnowledgeGraphStep extends StatefulWidget {
  final VoidCallback onContinue;

  /// Where the native step loads its graph from; harnesses pass a fixture.
  @visibleForTesting
  final Future<Map<String, dynamic>> Function() loadGraph;

  const OnboardingKnowledgeGraphStep(
      {super.key, required this.onContinue, this.loadGraph = KnowledgeGraphApi.getKnowledgeGraph});

  @override
  State<OnboardingKnowledgeGraphStep> createState() => _OnboardingKnowledgeGraphStepState();
}

class _OnboardingKnowledgeGraphStepState extends State<OnboardingKnowledgeGraphStep> with WidgetsBindingObserver {
  /// The native step's graph, created once the native renderer is confirmed. The classic step's
  /// embedded graph page owns its own, so the default build and unsupported systems never create
  /// this one.
  MemoryGraphController? _graph;

  /// Whether the renderer check has answered; the default build answers at once.
  bool _supportKnown = !nativePresentationEnabled;

  @override
  void initState() {
    super.initState();
    if (!nativePresentationEnabled) return;
    supportsNativePresentation().then((supported) {
      if (!mounted) return;
      setState(() {
        _supportKnown = true;
        if (!supported) return;
        WidgetsBinding.instance.addObserver(this);
        _graph = MemoryGraphController(loadGraph: widget.loadGraph, localizations: () => context.l10n)
          ..addListener(_onGraphChanged);
      });
      _graph?.load();
    }, onError: (_) {
      if (mounted) setState(() => _supportKnown = true);
    });
  }

  void _onGraphChanged() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Reloads quietly on resume, as the classic embedded graph does.
    if (state == AppLifecycleState.resumed) _graph?.load(silent: true);
  }

  @override
  void dispose() {
    if (_graph != null) WidgetsBinding.instance.removeObserver(this);
    _graph
      ?..removeListener(_onGraphChanged)
      ..dispose();
    super.dispose();
  }

  void _continue() {
    OmiHaptics.selection();
    widget.onContinue();
  }

  @override
  Widget build(BuildContext context) {
    if (!_supportKnown) return const OmiLoadingState();
    final classic = _buildClassic(context);
    final graph = _graph;
    if (graph == null) return classic;
    final rows = _graphRows(context, graph);
    // A graph the native renderer cannot take keeps the complete classic step and its navigation.
    if (rows == null) return NativeNavigationChrome.of(context)?.wrapFallback?.call(classic) ?? classic;
    final l10n = context.l10n;
    // Never the surface's loading or failed state: Continue stays reachable whatever the graph does.
    return IosNativeSurface(
      title: l10n.onboardingWhatIKnowAboutYouTitle,
      // The placeholder shows this copy over the graph while it loads, without the loading state.
      empty: graph.isLoading ? l10n.loadingKnowledgeGraph : '',
      fallback: classic,
      sections: [
        NativeSection('onboarding_knowledge_graph', [
          NativeRow('onboarding_kg_description', l10n.onboardingWhatIKnowAboutYouDescription, kind: 'label'),
          ...rows,
          NativeRow('onboarding_knowledge_graph_continue', l10n.continueButton, action: (_) => _continue()),
        ]),
      ],
    );
  }

  /// The graph by state, or null when the loaded graph cannot be projected.
  List<NativeRow>? _graphRows(BuildContext context, MemoryGraphController graph) {
    final l10n = context.l10n;
    final title = l10n.onboardingWhatIKnowAboutYouTitle;
    if (graph.isLoading) {
      return [
        NativeRow('onboarding_kg_graph', title,
            kind: 'graph', graph: NativeGraph.placeholder(accent: memoryGraphAccentHex())),
      ];
    }
    final error = graph.error;
    if (error != null) {
      return [
        NativeRow('onboarding_kg_error', error, kind: 'label'),
        NativeRow('onboarding_kg_retry', l10n.tryAgain, symbol: 'arrow.clockwise', action: (_) => graph.load()),
      ];
    }
    if (graph.isEmpty) {
      return [
        NativeRow('onboarding_kg_empty_title', l10n.noKnowledgeGraphYet, kind: 'label'),
        NativeRow('onboarding_kg_empty_message', l10n.knowledgeGraphWillBuildAutomatically, kind: 'label'),
      ];
    }
    final projection = projectNativeGraph(graph, zoom: 0.72);
    if (projection == null) return null;
    return [
      NativeRow('onboarding_kg_graph', title,
          kind: 'graph',
          value: nativeGraphSelection(graph, projection),
          graph: projection,
          action: (value) => graph.select(value == '' ? null : value as String)),
    ];
  }

  Widget _buildClassic(BuildContext context) {
    return Container(
      color: OmiColors.surface0,
      width: double.infinity,
      height: double.infinity,
      child: SafeArea(
        child: Padding(
          // The SafeArea already clears the progress dots and back button (OnboardingStepLayout).
          padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.md, OmiSpacing.xl, OmiSpacing.xl),
          child: Column(
            children: [
              Semantics(
                header: true,
                child: Text(
                  context.l10n.onboardingWhatIKnowAboutYouTitle,
                  textAlign: TextAlign.center,
                  style: OmiType.title1.copyWith(height: 1.2),
                ),
              ),
              const SizedBox(height: 10),
              Text(
                context.l10n.onboardingWhatIKnowAboutYouDescription,
                textAlign: TextAlign.center,
                style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.4),
              ),
              const SizedBox(height: OmiSpacing.lg),
              Expanded(
                child: ClipRRect(
                  borderRadius: OmiRadius.xlAll,
                  child: MemoryGraphPage(
                    embedded: true,
                    trackOpenEvent: false,
                    showAppBar: false,
                    showShareButton: false,
                    initialZoom: 0.72,
                    loadGraph: widget.loadGraph,
                  ),
                ),
              ),
              const SizedBox(height: OmiSpacing.lg),
              OmiButton(
                key: const Key('onboarding_knowledge_graph_continue'),
                label: context.l10n.continueButton,
                expand: true,
                onPressed: _continue,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
