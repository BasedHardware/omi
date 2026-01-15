import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';

import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/wrapped.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/wrapped_2025_share_templates.dart' as templates;
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/logger.dart';

// Bold color palette inspired by LinkedIn Wrapped
class WrappedColors {
  static const Color blue = Color(0xFF0077B5);
  static const Color lightBlue = Color(0xFFE8F4F8);
  static const Color coral = Color(0xFFFF6B6B);
  static const Color mint = Color(0xFF4ECDC4);
  static const Color purple = Color(0xFF9B59B6);
  static const Color yellow = Color(0xFFF39C12);
  static const Color pink = Color(0xFFE91E63);
  static const Color teal = Color(0xFF00897B);
  static const Color orange = Color(0xFFFF5722);
  static const Color indigo = Color(0xFF3F51B5);
}

class Wrapped2025Page extends StatefulWidget {
  const Wrapped2025Page({super.key});

  @override
  State<Wrapped2025Page> createState() => _Wrapped2025PageState();
}

class _Wrapped2025PageState extends State<Wrapped2025Page> {
  WrappedStatus _status = WrappedStatus.notGenerated;
  Map<String, dynamic>? _result;
  String? _error;
  Map<String, dynamic>? _progress;
  bool _isLoading = true;
  Timer? _pollTimer;
  final PageController _pageController = PageController();
  int _currentPage = 0;

  // Key for share template rendering
  final GlobalKey _shareTemplateKey = GlobalKey();
  Widget? _currentShareTemplate;

  // Total number of cards
  int get _totalCards => 13;

  @override
  void initState() {
    super.initState();
    MixpanelManager().wrappedPageOpened();
    SharedPreferencesUtil().hasViewedWrapped2025 = true;
    _loadWrappedStatus();
    _pageController.addListener(_onPageChanged);
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _pageController.removeListener(_onPageChanged);
    _pageController.dispose();
    super.dispose();
  }

  void _onPageChanged() {
    if (_pageController.page != null) {
      final page = _pageController.page!.round();
      if (page != _currentPage) {
        setState(() => _currentPage = page);
        _trackCardView(page);
      }
    }
  }

  void _trackCardView(int page) {
    final cardNames = [
      'Intro',
      'Year in Numbers',
      'Top Categories',
      'Actions',
      'Memorable Days',
      'Best Moments',
      'My Buddies',
      'Obsessions',
      'Movie Recommendations',
      'Biggest Struggle',
      'Biggest Win',
      'Top Phrases',
      'Summary Collage',
    ];
    if (page >= 0 && page < cardNames.length) {
      MixpanelManager().wrappedCardViewed(
        cardName: cardNames[page],
        cardIndex: page,
      );
    }
  }

  Future<void> _loadWrappedStatus() async {
    setState(() => _isLoading = true);

    final response = await getWrapped2025();

    if (response != null) {
      setState(() {
        _status = response.status;
        _result = response.result;
        _error = response.error;
        _progress = response.progress;
        _isLoading = false;
      });

      if (_status == WrappedStatus.processing) {
        _startPolling();
      }
    } else {
      setState(() {
        _isLoading = false;
        _status = WrappedStatus.notGenerated;
      });
    }
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(seconds: 3), (timer) async {
      final response = await getWrapped2025();
      if (response != null) {
        setState(() {
          _status = response.status;
          _result = response.result;
          _error = response.error;
          _progress = response.progress;
        });

        if (_status != WrappedStatus.processing) {
          timer.cancel();
          if (_status == WrappedStatus.done && _result != null) {
            final totalHours = (_result?['total_time_hours'] ?? 0.0) as num;
            final totalMinutes = (totalHours * 60).toInt();
            final totalConvs = _result?['total_conversations'] ?? 0;
            final daysActive = _result?['days_active'] ?? 0;
            MixpanelManager().wrappedGenerationCompleted(
              totalConversations: totalConvs,
              totalMinutes: totalMinutes,
              daysActive: daysActive,
            );
          } else if (_status == WrappedStatus.error) {
            MixpanelManager().wrappedGenerationFailed(error: _error);
          }
        }
      }
    });
  }

  Future<void> _generateWrapped() async {
    MixpanelManager().wrappedGenerationStarted();

    setState(() {
      _status = WrappedStatus.processing;
      _progress = {'step': 'Starting...', 'pct': 0.0};
    });

    final response = await generateWrapped2025();

    if (response != null) {
      setState(() {
        _status = response.status;
      });

      if (_status == WrappedStatus.processing) {
        _startPolling();
      }
    } else {
      MixpanelManager().wrappedGenerationFailed(error: 'Failed to start generation');
      setState(() {
        _status = WrappedStatus.error;
        _error = 'Failed to start generation. Please try again.';
      });
    }
  }

  /// Share a template by rendering it offstage, capturing, and sharing
  Future<void> _shareTemplate(Widget template, String filename) async {
    // Map filename to card name and index
    final Map<String, Map<String, dynamic>> filenameToCard = {
      'omi_wrapped_stats': {'name': 'Year in Numbers', 'index': 1},
      'omi_wrapped_categories': {'name': 'Top Categories', 'index': 2},
      'omi_wrapped_actions': {'name': 'Actions', 'index': 3},
      'omi_wrapped_days': {'name': 'Memorable Days', 'index': 4},
      'omi_wrapped_moments': {'name': 'Best Moments', 'index': 5},
      'omi_wrapped_buddies': {'name': 'My Buddies', 'index': 6},
      'omi_wrapped_obsessions': {'name': 'Obsessions', 'index': 7},
      'omi_wrapped_movies': {'name': 'Movie Recommendations', 'index': 8},
      'omi_wrapped_struggle': {'name': 'Biggest Struggle', 'index': 9},
      'omi_wrapped_win': {'name': 'Biggest Win', 'index': 10},
      'omi_wrapped_phrases': {'name': 'Top Phrases', 'index': 11},
      'omi_wrapped_2025': {'name': 'Summary Collage', 'index': 12},
    };

    final cardInfo = filenameToCard[filename];
    final cardName = cardInfo?['name'] ?? filename;
    final cardIndex = cardInfo?['index'] ?? -1;

    MixpanelManager().wrappedShareButtonClicked(
      cardName: cardName,
      cardIndex: cardIndex,
    );

    try {
      HapticFeedback.mediumImpact();

      // Set the template and trigger rebuild
      setState(() {
        _currentShareTemplate = template;
      });

      // Wait for the widget to be rendered
      await Future.delayed(const Duration(milliseconds: 300));

      final boundary = _shareTemplateKey.currentContext?.findRenderObject() as RenderRepaintBoundary?;
      if (boundary == null) {
        Logger.debug('Share template boundary is null for $filename');
        MixpanelManager().wrappedShareFailed(
          cardName: cardName,
          cardIndex: cardIndex,
          error: 'Boundary is null',
        );
        return;
      }

      await Future.delayed(const Duration(milliseconds: 200));

      final image = await boundary.toImage(pixelRatio: 1.5);
      final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
      if (byteData == null) {
        MixpanelManager().wrappedShareFailed(
          cardName: cardName,
          cardIndex: cardIndex,
          error: 'Byte data is null',
        );
        return;
      }

      final bytes = byteData.buffer.asUint8List();

      final directory = await getTemporaryDirectory();
      final file = File('${directory.path}/$filename.png');
      await file.writeAsBytes(bytes);

      final box = context.findRenderObject() as RenderBox?;
      final sharePositionOrigin = box != null ? Rect.fromLTWH(0, 0, box.size.width, box.size.height / 2) : null;

      await Share.shareXFiles(
        [XFile(file.path)],
        text: 'My 2025, remembered by Omi ✨ omi.me/wrapped',
        sharePositionOrigin: sharePositionOrigin,
      );

      MixpanelManager().wrappedSharedSuccessfully(
        cardName: cardName,
        cardIndex: cardIndex,
        fileSizeBytes: bytes.length,
      );

      // Clear the template after sharing
      if (mounted) {
        setState(() {
          _currentShareTemplate = null;
        });
      }
    } catch (e) {
      Logger.debug('Error sharing $filename: $e');
      MixpanelManager().wrappedShareFailed(
        cardName: cardName,
        cardIndex: cardIndex,
        error: e.toString(),
      );
      if (mounted) {
        setState(() {
          _currentShareTemplate = null;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to share. Please try again.')),
        );
      }
    }
  }

  // ============================================================
  // SHARE TEMPLATE BUILDERS
  // ============================================================

  void _shareYearInNumbers() {
    final totalHours = (_result?['total_time_hours'] ?? 0.0) as num;
    final totalMinutes = (totalHours * 60).toInt();
    final totalConvs = _result?['total_conversations'] ?? 0;
    final daysActive = _result?['days_active'] ?? (totalConvs / 3).ceil();
    final percentile = _calculatePercentile(totalConvs);

    _shareTemplate(
      templates.YearInNumbersShareTemplate(
        totalMinutes: totalMinutes,
        totalConvs: totalConvs,
        daysActive: daysActive,
        percentile: percentile,
      ),
      'omi_wrapped_stats',
    );
  }

  void _shareCategoryChart() {
    final categoryBreakdownList = _result?['category_breakdown'] as List? ?? [];
    final topCategories = (_result?['top_categories'] as List?)?.take(5).toList() ?? [];
    final Map<String, int> categoryBreakdown = {};
    for (final item in categoryBreakdownList) {
      if (item is Map) {
        final cat = item['category'] as String? ?? '';
        final count = item['count'] as int? ?? 0;
        categoryBreakdown[cat] = count;
      }
    }
    final total = categoryBreakdown.values.fold<int>(0, (sum, val) => sum + val);
    final colors = [
      const Color(0xFF2E7D32),
      const Color(0xFFFF9800),
      const Color(0xFFF4D03F),
      const Color(0xFF1565C0),
      const Color(0xFF7B1FA2),
    ];

    List<Map<String, dynamic>> categories = [];
    for (int i = 0; i < topCategories.length && i < 5; i++) {
      final cat = topCategories[i] as String;
      final count = categoryBreakdown[cat] ?? 0;
      final pct = total > 0 ? (count / total * 100).round() : 0;
      categories.add({
        'name': _formatCategory(cat),
        'percentage': pct,
        'color': colors[i % colors.length],
      });
    }

    _shareTemplate(
      templates.TopCategoryShareTemplate(categories: categories),
      'omi_wrapped_categories',
    );
  }

  void _shareActions() {
    final total = _result?['total_action_items'] ?? 0;
    final completed = _result?['completed_action_items'] ?? 0;
    final rate = ((_result?['action_items_completion_rate'] ?? 0.0) * 100).toInt();

    _shareTemplate(
      templates.ActionsShareTemplate(
        totalTasks: total,
        completedTasks: completed,
        completionRate: rate,
      ),
      'omi_wrapped_actions',
    );
  }

  void _shareMemorableDays() {
    final days = _result?['memorable_days'] as Map<String, dynamic>?;
    final funDay = days?['most_fun_day'] as Map<String, dynamic>?;
    final productiveDay = days?['most_productive_day'] as Map<String, dynamic>?;
    final stressfulDay = days?['most_stressful_day'] as Map<String, dynamic>?;

    List<Map<String, dynamic>> memorableDays = [];
    if (funDay != null) {
      memorableDays.add({
        'emoji': funDay['emoji'] ?? '🎉',
        'label': 'Most Fun',
        'title': funDay['title'] ?? 'A Great Day',
        'description': funDay['description'] ?? '',
        'dateStr': funDay['date'] ?? 'January 1',
      });
    }
    if (productiveDay != null) {
      memorableDays.add({
        'emoji': productiveDay['emoji'] ?? '💪',
        'label': 'Most Productive',
        'title': productiveDay['title'] ?? 'Getting It Done',
        'description': productiveDay['description'] ?? '',
        'dateStr': productiveDay['date'] ?? 'June 15',
      });
    }
    if (stressfulDay != null) {
      memorableDays.add({
        'emoji': stressfulDay['emoji'] ?? '😤',
        'label': 'Most Intense',
        'title': stressfulDay['title'] ?? 'A Challenge',
        'description': stressfulDay['description'] ?? '',
        'dateStr': stressfulDay['date'] ?? 'December 1',
      });
    }

    _shareTemplate(
      templates.MemorableDaysShareTemplate(days: memorableDays),
      'omi_wrapped_days',
    );
  }

  void _shareBestMoments() {
    final funniestEvent = _result?['funniest_event'] as Map<String, dynamic>?;
    final cringeEvent = _result?['most_embarrassing_event'] as Map<String, dynamic>?;

    List<Map<String, dynamic>> moments = [
      {
        'emoji': '😂',
        'label': 'Funniest',
        'title': funniestEvent?['title'] ?? 'A Hilarious Moment',
        'description': funniestEvent?['story'] ?? '',
        'dateStr': funniestEvent?['date'] ?? 'January 1',
      },
      {
        'emoji': '😅',
        'label': 'Most Cringe',
        'title': cringeEvent?['title'] ?? 'That Awkward Moment',
        'description': cringeEvent?['story'] ?? '',
        'dateStr': cringeEvent?['date'] ?? 'January 1',
      },
    ];

    _shareTemplate(
      templates.BestMomentsShareTemplate(moments: moments),
      'omi_wrapped_moments',
    );
  }

  void _shareMyBuddies() {
    final buddies = (_result?['top_buddies'] as List<dynamic>?) ?? [];
    List<Map<String, dynamic>> buddyList = buddies.map((b) {
      final buddy = b as Map<String, dynamic>;
      return {
        'name': buddy['name'] ?? 'Friend',
        'relationship': buddy['relationship'] ?? 'Friend',
        'context': buddy['context'] ?? '',
        'emoji': buddy['emoji'] ?? '👋',
      };
    }).toList();

    _shareTemplate(
      templates.MyBuddiesShareTemplate(buddies: buddyList),
      'omi_wrapped_buddies',
    );
  }

  void _shareObsessions() {
    final obsessions = _result?['obsessions'] as Map<String, dynamic>?;
    _shareTemplate(
      templates.ObsessionsShareTemplate(
        show: _capitalizeWords(obsessions?['show'] ?? 'Not mentioned'),
        movie: _capitalizeWords(obsessions?['movie'] ?? 'Not mentioned'),
        book: _capitalizeWords(obsessions?['book'] ?? 'Not mentioned'),
        celebrity: _capitalizeWords(obsessions?['celebrity'] ?? 'Not mentioned'),
        food: _capitalizeWords(obsessions?['food'] ?? 'Not mentioned'),
      ),
      'omi_wrapped_obsessions',
    );
  }

  void _shareMovieRecs() {
    final movies = (_result?['movie_recommendations'] as List?)?.cast<String>() ?? [];
    _shareTemplate(
      templates.MovieRecsShareTemplate(
        movies: movies.map((m) => _capitalizeWords(m)).toList(),
      ),
      'omi_wrapped_movies',
    );
  }

  void _shareStruggle() {
    final struggle = _result?['struggle'] as Map<String, dynamic>?;
    _shareTemplate(
      templates.StruggleShareTemplate(
        title: struggle?['title'] ?? 'The Hard Part',
      ),
      'omi_wrapped_struggle',
    );
  }

  void _sharePersonalWin() {
    final win = _result?['personal_win'] as Map<String, dynamic>?;
    _shareTemplate(
      templates.BiggestWinShareTemplate(
        title: win?['title'] ?? 'Personal Growth',
      ),
      'omi_wrapped_win',
    );
  }

  void _shareTopPhrases() {
    final phrases = _result?['top_phrases'] as List<dynamic>? ?? [];
    List<String> phraseList = phrases.take(5).map((p) {
      final phrase = p is Map ? (p['phrase'] ?? '') : p.toString();
      return phrase.toString();
    }).toList();

    _shareTemplate(
      templates.TopPhrasesShareTemplate(phrases: phraseList),
      'omi_wrapped_phrases',
    );
  }

  void _shareFinalCollage() {
    final totalHours = (_result?['total_time_hours'] ?? 0.0) as num;
    final totalMinutes = (totalHours * 60).toInt();
    final totalConvs = _result?['total_conversations'] ?? 0;
    final daysActive = _result?['days_active'] ?? (totalConvs / 3).ceil();
    final percentile = _calculatePercentile(totalConvs);

    // Categories
    final categoryBreakdownList = _result?['category_breakdown'] as List? ?? [];
    final topCategoriesRaw = (_result?['top_categories'] as List?)?.take(3).toList() ?? [];
    final Map<String, int> categoryBreakdown = {};
    for (final item in categoryBreakdownList) {
      if (item is Map) {
        categoryBreakdown[item['category'] as String? ?? ''] = item['count'] as int? ?? 0;
      }
    }
    final total = categoryBreakdown.values.fold<int>(0, (sum, val) => sum + val);
    final colors = [const Color(0xFF2E7D32), const Color(0xFFFF9800), const Color(0xFFF4D03F)];
    List<Map<String, dynamic>> topCategories = [];
    for (int i = 0; i < topCategoriesRaw.length && i < 3; i++) {
      final cat = topCategoriesRaw[i] as String;
      final pct = total > 0 ? (categoryBreakdown[cat] ?? 0) / total * 100 : 0;
      topCategories.add({
        'name': _formatCategory(cat),
        'percentage': pct.round(),
        'color': colors[i],
      });
    }

    // Top Days
    final days = _result?['memorable_days'] as Map<String, dynamic>?;
    List<Map<String, dynamic>> topDays = [];
    if (days?['most_fun_day'] != null) {
      final d = days!['most_fun_day'] as Map<String, dynamic>;
      topDays.add({'emoji': d['emoji'] ?? '🎉', 'label': 'Fun', 'title': d['title'] ?? ''});
    }
    if (days?['most_productive_day'] != null) {
      final d = days!['most_productive_day'] as Map<String, dynamic>;
      topDays.add({'emoji': d['emoji'] ?? '💪', 'label': 'Productive', 'title': d['title'] ?? ''});
    }
    if (days?['most_stressful_day'] != null) {
      final d = days!['most_stressful_day'] as Map<String, dynamic>;
      topDays.add({'emoji': d['emoji'] ?? '😤', 'label': 'Intense', 'title': d['title'] ?? ''});
    }

    // Best Moments
    final funniestEvent = _result?['funniest_event'] as Map<String, dynamic>?;
    final cringeEvent = _result?['most_embarrassing_event'] as Map<String, dynamic>?;
    List<Map<String, dynamic>> bestMoments = [
      {'emoji': '😂', 'title': funniestEvent?['title'] ?? 'Funny Moment'},
      {'emoji': '😅', 'title': cringeEvent?['title'] ?? 'Cringe Moment'},
    ];

    // Buddies
    final buddiesRaw = (_result?['top_buddies'] as List<dynamic>?) ?? [];
    List<Map<String, dynamic>> buddies = buddiesRaw.take(4).map((b) {
      final buddy = b as Map<String, dynamic>;
      return {'name': buddy['name'] ?? '', 'emoji': buddy['emoji'] ?? '👋'};
    }).toList();

    // Obsessions
    final obsessions = _result?['obsessions'] as Map<String, dynamic>?;
    final show = _capitalizeWords(obsessions?['show'] ?? 'Not mentioned');
    final movie = _capitalizeWords(obsessions?['movie'] ?? 'Not mentioned');
    final food = _capitalizeWords(obsessions?['food'] ?? 'Not mentioned');
    final celebrity = _capitalizeWords(obsessions?['celebrity'] ?? 'Not mentioned');

    // Phrases
    final phrases = _result?['top_phrases'] as List<dynamic>? ?? [];
    List<String> topPhrases = phrases.take(3).map((p) {
      return (p is Map ? (p['phrase'] ?? '') : p).toString();
    }).toList();

    // Struggle + Win
    final struggle = (_result?['struggle'] as Map<String, dynamic>?)?['title'] ?? 'The Hard Part';
    final biggestWin = (_result?['personal_win'] as Map<String, dynamic>?)?['title'] ?? 'Personal Growth';

    _shareTemplate(
      templates.FinalCollageShareTemplate(
        totalMinutes: totalMinutes,
        totalConvs: totalConvs,
        daysActive: daysActive,
        percentile: percentile,
        topCategories: topCategories,
        topDays: topDays,
        bestMoments: bestMoments,
        buddies: buddies,
        show: show,
        movie: movie,
        food: food,
        celebrity: celebrity,
        topPhrases: topPhrases,
        struggle: struggle,
        biggestWin: biggestWin,
      ),
      'omi_wrapped_2025',
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: [
          _isLoading ? const Center(child: CircularProgressIndicator(color: Colors.white)) : _buildContent(),
          // Offstage share template renderer
          if (_currentShareTemplate != null)
            Positioned(
              left: -10000,
              top: -10000,
              child: RepaintBoundary(
                key: _shareTemplateKey,
                child: _currentShareTemplate!,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildContent() {
    switch (_status) {
      case WrappedStatus.notGenerated:
        return _buildGenerateScreen();
      case WrappedStatus.processing:
        return _buildProcessingScreen();
      case WrappedStatus.done:
        return _buildWrappedCards();
      case WrappedStatus.error:
        return _buildErrorScreen();
    }
  }

  Widget _buildGenerateScreen() {
    return Container(
      color: WrappedColors.blue,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(32.0),
          child: Column(
            children: [
              const Spacer(),
              const Text(
                "Let's hit rewind on your",
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.w400,
                ),
              ),
              const SizedBox(height: 16),
              const FittedBox(
                fit: BoxFit.scaleDown,
                child: Text(
                  '2025',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 120,
                    fontWeight: FontWeight.w900,
                    height: 0.9,
                  ),
                ),
              ),
              const Spacer(),
              GestureDetector(
                onTap: _generateWrapped,
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: 20),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(40),
                  ),
                  child: const Text(
                    'Generate My Wrapped',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: WrappedColors.blue,
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 40),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildProcessingScreen() {
    final step = _progress?['step'] ?? 'Processing...';
    final pct = (_progress?['pct'] ?? 0.0) as num;

    return Container(
      color: WrappedColors.purple,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(32.0),
          child: Column(
            children: [
              const Spacer(),
              const Text(
                '✨',
                style: TextStyle(fontSize: 80),
              ),
              const SizedBox(height: 32),
              const Text(
                'Creating your\n2025 story...',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 36,
                  fontWeight: FontWeight.w700,
                  height: 1.2,
                ),
              ),
              const SizedBox(height: 24),
              Text(
                step,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white.withOpacity(0.8),
                  fontSize: 18,
                ),
              ),
              const SizedBox(height: 40),
              if (pct > 0)
                Column(
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: LinearProgressIndicator(
                        value: pct.toDouble(),
                        minHeight: 8,
                        backgroundColor: Colors.white.withOpacity(0.3),
                        valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      '${(pct * 100).toInt()}%',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 24,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              const Spacer(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildErrorScreen() {
    return Container(
      color: WrappedColors.coral,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(32.0),
          child: Column(
            children: [
              const Spacer(),
              const Text(
                '😕',
                style: TextStyle(fontSize: 80),
              ),
              const SizedBox(height: 32),
              const Text(
                'Something\nwent wrong',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 36,
                  fontWeight: FontWeight.w700,
                  height: 1.2,
                ),
              ),
              const SizedBox(height: 16),
              Text(
                _error ?? 'An error occurred',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white.withOpacity(0.8),
                  fontSize: 16,
                ),
              ),
              const Spacer(),
              GestureDetector(
                onTap: _generateWrapped,
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: 20),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(40),
                  ),
                  child: const Text(
                    'Try Again',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: WrappedColors.coral,
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 40),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildWrappedCards() {
    if (_result == null) {
      return const Center(
        child: Text('No data available', style: TextStyle(color: Colors.white)),
      );
    }

    final cards = _buildCardsList();

    return Stack(
      children: [
        // Pages scroll beneath
        PageView.builder(
          controller: _pageController,
          scrollDirection: Axis.vertical,
          itemCount: cards.length,
          onPageChanged: (index) {
            setState(() => _currentPage = index);
            HapticFeedback.selectionClick();
          },
          itemBuilder: (context, index) => cards[index],
        ),
        // Static progress dots on the right (don't scroll) - hide on summary page
        if (_currentPage != 12)
          Positioned(
            right: 12,
            top: 0,
            bottom: 0,
            child: SafeArea(
              child: _buildProgressDots(
                Colors.white,
                Colors.white.withOpacity(0.3),
              ),
            ),
          ),
      ],
    );
  }

  // Progress dots widget (vertical, on the right) - static overlay
  Widget _buildProgressDots(Color activeColor, Color inactiveColor) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(_totalCards, (index) {
        final isActive = index == _currentPage;
        final isPast = index < _currentPage;
        return Container(
          width: isActive ? 10 : 6,
          height: isActive ? 10 : 6,
          margin: EdgeInsets.only(bottom: index < _totalCards - 1 ? 8 : 0),
          decoration: BoxDecoration(
            color: isActive ? activeColor : (isPast ? activeColor.withOpacity(0.7) : inactiveColor),
            shape: BoxShape.circle,
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.3),
                blurRadius: 4,
                offset: const Offset(0, 1),
              ),
            ],
          ),
        );
      }),
    );
  }

  Widget _buildCardBase({
    required Color backgroundColor,
    required Widget child,
    Color textColor = Colors.white,
    bool isDark = true,
    EdgeInsets? customPadding,
  }) {
    return Container(
      color: backgroundColor,
      child: SafeArea(
        child: Padding(
          padding: customPadding ?? const EdgeInsets.only(left: 24, right: 40, top: 16, bottom: 16),
          child: child,
        ),
      ),
    );
  }

  List<Widget> _buildCardsList() {
    return [
      _buildIntroCard(), // 0
      _buildYearInNumbersCard(), // 1
      _buildTopCategoryCard(), // 2
      _buildActionsCard(), // 3
      _buildMemorableDaysCard(), // 4
      _buildBestMomentsCard(), // 5 (combined funniest + cringe)
      _buildMyBuddiesCard(), // 6
      _buildObsessionsCard(), // 7
      _buildMovieRecsCard(), // 8
      _buildStruggleCard(), // 9
      _buildPersonalWinCard(), // 10
      _buildTopPhrasesCard(), // 11
      _buildSummaryCollageCard(), // 12 - Final collage summary
    ];
  }

  Widget _buildIntroCard() {
    return _buildCardBase(
      backgroundColor: WrappedColors.blue,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 48),
          const Text(
            '20',
            style: TextStyle(
              color: Colors.white,
              fontSize: 200,
              fontWeight: FontWeight.w900,
              height: 0.8,
              letterSpacing: -10,
            ),
          ),
          const Text(
            '25',
            style: TextStyle(
              color: Colors.white,
              fontSize: 200,
              fontWeight: FontWeight.w900,
              height: 0.8,
              letterSpacing: -10,
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 0, 0, 0),
            child: Text(
              'Omi Life Recap',
              style: TextStyle(
                color: Colors.white.withOpacity(0.8),
                fontSize: 24,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          const Spacer(),
          Row(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(8, 0, 0, 0),
                child: Text(
                  'Swipe up to begin',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.7),
                    fontSize: 16,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Icon(
                Icons.keyboard_arrow_up,
                color: Colors.white.withOpacity(0.7),
                size: 24,
              ),
            ],
          ),
          const SizedBox(height: 32),
        ],
      ),
    );
  }

  // Calculate percentile based on actual user distribution (9,701 total users)
  double _calculatePercentile(int convos) {
    if (convos >= 4000) return 0.2; // 18 users
    if (convos >= 3000) return 0.4; // 36 users
    if (convos >= 2000) return 0.7; // 68 users
    if (convos >= 1000) return 1.9; // 182 users
    if (convos >= 800) return 2.6; // 253 users
    if (convos >= 600) return 3.6; // 349 users
    if (convos >= 500) return 4.5; // 440 users
    if (convos >= 400) return 5.7; // 555 users
    if (convos >= 300) return 7.4; // 721 users
    if (convos >= 200) return 11.0; // 1064 users
    if (convos >= 100) return 19.2; // 1859 users
    return 50.0; // 7842 users
  }

  Widget _buildYearInNumbersCard() {
    final totalHours = (_result?['total_time_hours'] ?? 0.0) as num;
    final totalMinutes = (totalHours * 60).toInt();
    final totalConvs = _result?['total_conversations'] ?? 0;
    final daysActive = _result?['days_active'] ?? (totalConvs / 3).ceil();
    final percentile = _calculatePercentile(totalConvs);

    return _buildCardBase(
      backgroundColor: WrappedColors.mint,
      child: _YearInNumbersAnimated(
        totalMinutes: totalMinutes,
        totalConvs: totalConvs,
        daysActive: daysActive,
        percentile: percentile,
        isActive: _currentPage == 1,
        onShare: _shareYearInNumbers,
      ),
    );
  }

  Widget _buildTopCategoryCard() {
    final categoryBreakdownList = _result?['category_breakdown'] as List? ?? [];
    final topCategories = (_result?['top_categories'] as List?)?.take(5).toList() ?? [];

    // Convert breakdown list to map
    final Map<String, int> categoryBreakdown = {};
    for (final item in categoryBreakdownList) {
      if (item is Map) {
        final cat = item['category'] as String? ?? '';
        final count = item['count'] as int? ?? 0;
        categoryBreakdown[cat] = count;
      }
    }

    // Calculate percentages for top 5 categories
    final total = categoryBreakdown.values.fold<int>(0, (sum, val) => sum + val);

    List<_CategoryData> categories = [];
    final colors = [
      const Color(0xFF2E7D32), // Green
      const Color(0xFFFF9800), // Orange
      const Color(0xFFF4D03F), // Yellow
      const Color(0xFF1565C0), // Blue
      const Color(0xFF7B1FA2), // Purple
    ];

    for (int i = 0; i < topCategories.length && i < 5; i++) {
      final cat = topCategories[i] as String;
      final count = categoryBreakdown[cat] ?? 0;
      final pct = total > 0 ? (count / total * 100).round() : 0;
      categories.add(_CategoryData(
        name: _formatCategory(cat),
        percentage: pct,
        color: colors[i % colors.length],
      ));
    }

    // If we don't have breakdown data, create mock percentages
    if (categories.isEmpty && topCategories.isNotEmpty) {
      final mockPcts = [40, 25, 15, 12, 8];
      for (int i = 0; i < topCategories.length && i < 5; i++) {
        categories.add(_CategoryData(
          name: _formatCategory(topCategories[i] as String),
          percentage: mockPcts[i],
          color: colors[i % colors.length],
        ));
      }
    }

    return _buildCardBase(
      backgroundColor: WrappedColors.mint,
      child: _CategoryChartAnimated(
        categories: categories,
        isActive: _currentPage == 2,
        onShare: _shareCategoryChart,
      ),
    );
  }

  String _formatCategory(String category) {
    return category
        .replaceAll('_', ' ')
        .split(' ')
        .map((w) => w.isNotEmpty ? '${w[0].toUpperCase()}${w.substring(1)}' : '')
        .join(' ');
  }

  String _capitalizeWords(String text) {
    return text.split(' ').map((w) => w.isNotEmpty ? '${w[0].toUpperCase()}${w.substring(1)}' : '').join(' ');
  }

  Widget _buildActionsCard() {
    final total = _result?['total_action_items'] ?? 0;
    final completed = _result?['completed_action_items'] ?? 0;
    final rate = ((_result?['action_items_completion_rate'] ?? 0.0) * 100).toInt();

    return _buildCardBase(
      backgroundColor: WrappedColors.indigo,
      child: _ActionsAnimated(
        totalTasks: total,
        completedTasks: completed,
        completionRate: rate,
        isActive: _currentPage == 3,
        onShare: _shareActions,
      ),
    );
  }

  Widget _buildMemorableDaysCard() {
    final days = _result?['memorable_days'] as Map<String, dynamic>?;
    final funDay = days?['most_fun_day'] as Map<String, dynamic>?;
    final productiveDay = days?['most_productive_day'] as Map<String, dynamic>?;
    final stressfulDay = days?['most_stressful_day'] as Map<String, dynamic>?;

    // Parse memorable days into list
    final memorableDays = <_MemorableDayData>[];

    if (funDay != null) {
      memorableDays.add(_MemorableDayData(
        emoji: funDay['emoji'] ?? '🎉',
        label: 'Most Fun',
        title: funDay['title'] ?? 'A Great Day',
        description: funDay['description'] ?? '',
        dateStr: funDay['date'] ?? 'January 1',
      ));
    }

    if (productiveDay != null) {
      memorableDays.add(_MemorableDayData(
        emoji: productiveDay['emoji'] ?? '💪',
        label: 'Most Productive',
        title: productiveDay['title'] ?? 'Getting It Done',
        description: productiveDay['description'] ?? '',
        dateStr: productiveDay['date'] ?? 'June 15',
      ));
    }

    if (stressfulDay != null) {
      memorableDays.add(_MemorableDayData(
        emoji: stressfulDay['emoji'] ?? '😤',
        label: 'Most Intense',
        title: stressfulDay['title'] ?? 'A Challenge',
        description: stressfulDay['description'] ?? '',
        dateStr: stressfulDay['date'] ?? 'December 1',
      ));
    }

    return _buildCardBase(
      backgroundColor: WrappedColors.teal,
      child: _MemorableDaysAnimated(
        days: memorableDays,
        isActive: _currentPage == 4,
        onShare: _shareMemorableDays,
      ),
    );
  }

  Widget _buildBestMomentsCard() {
    // Funniest moment
    final funniestEvent = _result?['funniest_event'] as Map<String, dynamic>?;
    final funniestTitle = funniestEvent?['title'] ?? 'A Hilarious Moment';
    final funniestStory = funniestEvent?['story'] ?? 'You had some funny moments this year!';
    final funniestDateStr = funniestEvent?['date'] ?? 'January 1';

    // Cringe moment
    final cringeEvent = _result?['most_embarrassing_event'] as Map<String, dynamic>?;
    final cringeTitle = cringeEvent?['title'] ?? 'That Awkward Moment';
    final cringeStory = cringeEvent?['story'] ?? "We've all been there!";
    final cringeDateStr = cringeEvent?['date'] ?? 'January 1';

    final bestMoments = <_MemorableDayData>[
      _MemorableDayData(
        emoji: '😂',
        label: 'Funniest',
        title: funniestTitle,
        description: funniestStory,
        dateStr: funniestDateStr,
      ),
      _MemorableDayData(
        emoji: '😅',
        label: 'Most Cringe',
        title: cringeTitle,
        description: cringeStory,
        dateStr: cringeDateStr,
      ),
    ];

    return _buildCardBase(
      backgroundColor: WrappedColors.coral,
      child: _MemorableDaysAnimated(
        days: bestMoments,
        isActive: _currentPage == 5,
        headerLine1: 'Best',
        headerLine2: 'Moments',
        summaryBadgeText: 'Best Moments',
        badgeColor: WrappedColors.coral,
        onShare: _shareBestMoments,
      ),
    );
  }

  Widget _buildMyBuddiesCard() {
    final buddies = (_result?['top_buddies'] as List<dynamic>?) ?? [];

    return _buildCardBase(
      backgroundColor: const Color(0xFF6B5B95),
      child: _MyBuddiesAnimated(
        buddies: buddies.map((b) {
          final buddy = b as Map<String, dynamic>;
          return _BuddyData(
            name: buddy['name'] ?? 'Friend',
            relationship: buddy['relationship'] ?? 'Friend',
            context: buddy['context'] ?? 'Your buddy!',
            emoji: buddy['emoji'] ?? '👋',
          );
        }).toList(),
        isActive: _currentPage == 6,
        onShare: _shareMyBuddies,
      ),
    );
  }

  Widget _buildObsessionsCard() {
    final obsessions = _result?['obsessions'] as Map<String, dynamic>?;
    final show = _capitalizeWords(obsessions?['show'] ?? 'Not mentioned');
    final movie = _capitalizeWords(obsessions?['movie'] ?? 'Not mentioned');
    final book = _capitalizeWords(obsessions?['book'] ?? 'Not mentioned');
    final celebrity = _capitalizeWords(obsessions?['celebrity'] ?? 'Not mentioned');
    final food = _capitalizeWords(obsessions?['food'] ?? 'Not mentioned');

    return _buildCardBase(
      backgroundColor: WrappedColors.coral,
      child: _TypewriterEndPageAnimated(
        badgeText: "Couldn't Stop Talking About",
        badgeColor: WrappedColors.coral,
        isActive: _currentPage == 7,
        showProgressRing: false,
        items: [
          _TypewriterItem(label: 'Show', value: show, emoji: '📺'),
          _TypewriterItem(label: 'Movie', value: movie, emoji: '🎬'),
          _TypewriterItem(label: 'Book', value: book, emoji: '📚'),
          _TypewriterItem(label: 'Celebrity', value: celebrity, emoji: '⭐'),
          _TypewriterItem(label: 'Food', value: food, emoji: '🍕'),
        ],
        onShare: _shareObsessions,
      ),
    );
  }

  Widget _buildMovieRecsCard() {
    final movies = (_result?['movie_recommendations'] as List?)?.cast<String>() ?? [];

    return _buildCardBase(
      backgroundColor: const Color(0xFF1a0a2e),
      child: _TypewriterEndPageAnimated(
        badgeText: 'Movie Recs For Friends',
        badgeColor: const Color(0xFF1a0a2e),
        isActive: _currentPage == 8,
        showProgressRing: false,
        items: movies.asMap().entries.map((entry) {
          return _TypewriterItem(
            label: '#${entry.key + 1}',
            value: _capitalizeWords(entry.value),
            emoji: '🎬',
          );
        }).toList(),
        onShare: _shareMovieRecs,
      ),
    );
  }

  Widget _buildStruggleCard() {
    final struggle = _result?['struggle'] as Map<String, dynamic>?;
    final title = struggle?['title'] ?? 'The Hard Part';

    return _buildCardBase(
      backgroundColor: const Color(0xFF2d4a3e),
      child: _BigMomentAnimated(
        emoji: '😤',
        headerLine1: 'Biggest',
        headerLine2: 'Struggle',
        title: title,
        subtitle: 'But you pushed through 💪',
        isActive: _currentPage == 9,
        onShare: _shareStruggle,
        buttonColor: const Color(0xFF2d4a3e),
      ),
    );
  }

  Widget _buildPersonalWinCard() {
    final win = _result?['personal_win'] as Map<String, dynamic>?;
    final title = win?['title'] ?? 'Personal Growth';

    return _buildCardBase(
      backgroundColor: WrappedColors.mint,
      child: _BigMomentAnimated(
        emoji: '🏆',
        headerLine1: 'Biggest',
        headerLine2: 'Win',
        title: title,
        subtitle: 'You did it! 🎉',
        isActive: _currentPage == 10,
        onShare: _sharePersonalWin,
        buttonColor: WrappedColors.mint,
      ),
    );
  }

  Widget _buildTopPhrasesCard() {
    final phrases = _result?['top_phrases'] as List<dynamic>? ?? [];

    return _buildCardBase(
      backgroundColor: WrappedColors.orange,
      customPadding: const EdgeInsets.symmetric(horizontal: 0, vertical: 16),
      child: _TopPhrasesAnimated(
        phrases: phrases.take(5).map((p) {
          final phrase = p is Map ? (p['phrase'] ?? '') : p.toString();
          return phrase.toString();
        }).toList(),
        isActive: _currentPage == 11,
        onShare: _shareTopPhrases,
      ),
    );
  }

  Widget _buildSummaryCollageCard() {
    return _buildCardBase(
      backgroundColor: const Color(0xFF0A1628),
      customPadding: const EdgeInsets.only(left: 16, right: 16, top: 16, bottom: 16),
      child: _SummaryCollageAnimated(
        result: _result ?? {},
        isActive: _currentPage == 12,
        onShare: _shareFinalCollage,
        formatCategory: _formatCategory,
        capitalizeWords: _capitalizeWords,
        calculatePercentile: _calculatePercentile,
      ),
    );
  }

  Widget _buildSummaryStat(String value, String label) {
    return Column(
      children: [
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 32,
            fontWeight: FontWeight.w900,
          ),
        ),
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.7),
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildShareableImage(dynamic totalHours, int totalConvs, int totalActions) {
    final hours = totalHours is num ? totalHours.toStringAsFixed(0) : '0';

    return Container(
      width: 1080,
      height: 1920,
      color: WrappedColors.blue,
      child: Padding(
        padding: const EdgeInsets.all(80),
        child: Column(
          children: [
            const Spacer(),
            const Text(
              'My 2025',
              style: TextStyle(
                color: Colors.white,
                fontSize: 80,
                fontWeight: FontWeight.w900,
                decoration: TextDecoration.none,
              ),
            ),
            const Text(
              'remembered by Omi',
              style: TextStyle(
                color: Colors.white70,
                fontSize: 36,
                fontWeight: FontWeight.w500,
                decoration: TextDecoration.none,
              ),
            ),
            const SizedBox(height: 100),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                _buildShareStat(hours, 'hours'),
                _buildShareStat('$totalConvs', 'convos'),
                _buildShareStat('$totalActions', 'actions'),
              ],
            ),
            const Spacer(),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 20),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.2),
                borderRadius: BorderRadius.circular(40),
              ),
              child: const Text(
                'omi.me/wrapped',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 32,
                  fontWeight: FontWeight.w600,
                  decoration: TextDecoration.none,
                ),
              ),
            ),
            const SizedBox(height: 60),
          ],
        ),
      ),
    );
  }

  Widget _buildShareStat(String value, String label) {
    return Column(
      children: [
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 64,
            fontWeight: FontWeight.w900,
            decoration: TextDecoration.none,
          ),
        ),
        Text(
          label,
          style: const TextStyle(
            color: Colors.white70,
            fontSize: 28,
            fontWeight: FontWeight.w500,
            decoration: TextDecoration.none,
          ),
        ),
      ],
    );
  }
}

// Animated Year in Numbers card
class _YearInNumbersAnimated extends StatefulWidget {
  final int totalMinutes;
  final int totalConvs;
  final int daysActive;
  final double percentile;
  final bool isActive;
  final VoidCallback? onShare;
  final GlobalKey? shareKey;

  const _YearInNumbersAnimated({
    required this.totalMinutes,
    required this.totalConvs,
    required this.daysActive,
    required this.percentile,
    required this.isActive,
    this.onShare,
    this.shareKey,
  });

  @override
  State<_YearInNumbersAnimated> createState() => _YearInNumbersAnimatedState();
}

class _YearInNumbersAnimatedState extends State<_YearInNumbersAnimated> with TickerProviderStateMixin {
  late AnimationController _minutesController;
  late AnimationController _convosController;
  late AnimationController _daysController;
  late AnimationController _badgeController;
  late AnimationController _shareButtonController;

  late Animation<double> _minutesAnimation;
  late Animation<double> _convosAnimation;
  late Animation<double> _daysAnimation;
  late Animation<double> _badgeAnimation;
  late Animation<double> _shareButtonAnimation;

  bool _hasAnimated = false;
  final _numberFormat = NumberFormat('#,###');

  // For tick sound during count
  Timer? _tickTimer;
  int _lastTickValue = 0;

  @override
  void initState() {
    super.initState();

    // Minutes count-up animation
    _minutesController = AnimationController(
      duration: const Duration(milliseconds: 1200),
      vsync: this,
    );
    _minutesAnimation = CurvedAnimation(
      parent: _minutesController,
      curve: Curves.easeOutCubic,
    );

    // Conversations count-up animation
    _convosController = AnimationController(
      duration: const Duration(milliseconds: 1000),
      vsync: this,
    );
    _convosAnimation = CurvedAnimation(
      parent: _convosController,
      curve: Curves.easeOutCubic,
    );

    // Days active count-up animation
    _daysController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _daysAnimation = CurvedAnimation(
      parent: _daysController,
      curve: Curves.easeOutCubic,
    );

    // Badge stamp animation
    _badgeController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _badgeAnimation = CurvedAnimation(
      parent: _badgeController,
      curve: Curves.elasticOut,
    );

    // Share button pop animation
    _shareButtonController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _shareButtonAnimation = CurvedAnimation(
      parent: _shareButtonController,
      curve: Curves.elasticOut,
    );

    // Chain animations with sound effects
    _minutesController.addListener(_onMinutesTick);
    _minutesController.addStatusListener((status) {
      if (status == AnimationStatus.completed && mounted) {
        HapticFeedback.mediumImpact();
        _lastTickValue = 0;
        _convosController.forward();
      }
    });

    _convosController.addListener(_onConvosTick);
    _convosController.addStatusListener((status) {
      if (status == AnimationStatus.completed && mounted) {
        HapticFeedback.mediumImpact();
        _lastTickValue = 0;
        _daysController.forward();
      }
    });

    _daysController.addListener(_onDaysTick);
    _daysController.addStatusListener((status) {
      if (status == AnimationStatus.completed && mounted) {
        HapticFeedback.mediumImpact();
        Future.delayed(const Duration(milliseconds: 200), () {
          if (mounted) {
            _badgeController.forward();
          }
        });
      }
    });

    _badgeController.addStatusListener((status) {
      if (status == AnimationStatus.completed && mounted) {
        // Stamp sound - heavy impact
        HapticFeedback.heavyImpact();
        // Start share button animation after badge completes
        Future.delayed(const Duration(milliseconds: 300), () {
          if (mounted) {
            _shareButtonController.forward();
          }
        });
      }
    });

    // Start animation if already active
    if (widget.isActive) {
      _startAnimation();
    }
  }

  void _onMinutesTick() {
    final current = (_minutesAnimation.value * widget.totalMinutes).toInt();
    // Tick every ~5% of the total or every 100 units
    final tickInterval = (widget.totalMinutes / 20).ceil().clamp(10, 500);
    if ((current - _lastTickValue).abs() >= tickInterval) {
      _lastTickValue = current;
      HapticFeedback.selectionClick();
    }
  }

  void _onConvosTick() {
    final current = (_convosAnimation.value * widget.totalConvs).toInt();
    final tickInterval = (widget.totalConvs / 20).ceil().clamp(5, 100);
    if ((current - _lastTickValue).abs() >= tickInterval) {
      _lastTickValue = current;
      HapticFeedback.selectionClick();
    }
  }

  void _onDaysTick() {
    final current = (_daysAnimation.value * widget.daysActive).toInt();
    final tickInterval = (widget.daysActive / 15).ceil().clamp(3, 30);
    if ((current - _lastTickValue).abs() >= tickInterval) {
      _lastTickValue = current;
      HapticFeedback.selectionClick();
    }
  }

  void _startAnimation() {
    if (_hasAnimated) return;
    _hasAnimated = true;
    Future.delayed(const Duration(milliseconds: 300), () {
      if (mounted) {
        _minutesController.forward();
      }
    });
  }

  @override
  void didUpdateWidget(_YearInNumbersAnimated oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !_hasAnimated) {
      _startAnimation();
    }
  }

  @override
  void dispose() {
    _tickTimer?.cancel();
    _minutesController.removeListener(_onMinutesTick);
    _convosController.removeListener(_onConvosTick);
    _daysController.removeListener(_onDaysTick);
    _minutesController.dispose();
    _convosController.dispose();
    _daysController.dispose();
    _badgeController.dispose();
    _shareButtonController.dispose();
    super.dispose();
  }

  // Calculate overall progress (0.0 to 1.0)
  double get _overallProgress {
    // Minutes: 0-33%, Convos: 33-66%, Days: 66-90%, Badge: 90-100%
    if (!_hasAnimated) return 0.0;

    double progress = 0.0;
    progress += _minutesAnimation.value * 0.33;
    progress += _convosAnimation.value * 0.33;
    progress += _daysAnimation.value * 0.24;
    progress += _badgeAnimation.value * 0.10;
    return progress.clamp(0.0, 1.0);
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([
        _minutesAnimation,
        _convosAnimation,
        _daysAnimation,
        _badgeAnimation,
        _shareButtonAnimation,
      ]),
      builder: (context, child) {
        final animatedMinutes = (_minutesAnimation.value * widget.totalMinutes).toInt();
        final animatedConvos = (_convosAnimation.value * widget.totalConvs).toInt();
        final animatedDays = (_daysAnimation.value * widget.daysActive).toInt();

        // Badge scale for stamp effect
        final badgeScale = _badgeAnimation.value;
        final badgeOpacity = _badgeAnimation.value.clamp(0.0, 1.0);

        // Share button scale for pop effect
        final shareButtonScale = _shareButtonAnimation.value;
        final shareButtonOpacity = _shareButtonAnimation.value.clamp(0.0, 1.0);

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 40),
            // Percentile badge - stamps in at the end
            Opacity(
              opacity: badgeOpacity,
              child: Transform.scale(
                scale: badgeScale == 0 ? 0 : (0.5 + badgeScale * 0.5),
                alignment: Alignment.centerLeft,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    'Top ${widget.percentile}% User',
                    style: const TextStyle(
                      color: WrappedColors.mint,
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 32),
            // Minutes - counts up first
            Text(
              _numberFormat.format(animatedMinutes),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 80,
                fontWeight: FontWeight.w900,
                height: 0.9,
              ),
            ),
            Opacity(
              opacity: _minutesAnimation.value > 0.3 ? 1.0 : _minutesAnimation.value / 0.3,
              child: const Text(
                'minutes',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 28,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(height: 36),
            // Conversations - counts up second
            Opacity(
              opacity: _convosController.isAnimating || _convosController.isCompleted ? 1.0 : 0.3,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _numberFormat.format(animatedConvos),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 80,
                      fontWeight: FontWeight.w900,
                      height: 0.9,
                    ),
                  ),
                  Opacity(
                    opacity: _convosAnimation.value > 0.3 ? 1.0 : _convosAnimation.value / 0.3,
                    child: const Text(
                      'conversations',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 28,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 36),
            // Days Active - counts up third
            Opacity(
              opacity: _daysController.isAnimating || _daysController.isCompleted ? 1.0 : 0.3,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _numberFormat.format(animatedDays),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 80,
                      fontWeight: FontWeight.w900,
                      height: 0.9,
                    ),
                  ),
                  Opacity(
                    opacity: _daysAnimation.value > 0.3 ? 1.0 : _daysAnimation.value / 0.3,
                    child: const Text(
                      'days active',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 28,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const Spacer(),
            // Progress circle or Share button (animated pop in)
            shareButtonScale > 0
                ? Opacity(
                    opacity: shareButtonOpacity,
                    child: Transform.scale(
                      scale: shareButtonScale == 0 ? 0 : (0.5 + shareButtonScale * 0.5),
                      alignment: Alignment.centerLeft,
                      child: GestureDetector(
                        onTap: () {
                          HapticFeedback.mediumImpact();
                          widget.onShare?.call();
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.ios_share,
                                color: WrappedColors.mint,
                                size: 18,
                              ),
                              SizedBox(width: 6),
                              Text(
                                'Share',
                                style: TextStyle(
                                  color: WrappedColors.mint,
                                  fontSize: 16,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  )
                : SizedBox(
                    width: 32,
                    height: 32,
                    child: CustomPaint(
                      painter: _CircularProgressPainter(
                        progress: _overallProgress,
                        strokeWidth: 3,
                        backgroundColor: Colors.white.withOpacity(0.3),
                        progressColor: Colors.white,
                      ),
                    ),
                  ),
            const SizedBox(height: 20),
          ],
        );
      },
    );
  }
}

// Reusable animated share button widget
class _AnimatedShareButton extends StatefulWidget {
  final double progress; // 0.0 to 1.0 - when 1.0, show share button
  final VoidCallback? onShare;
  final Color buttonColor;

  const _AnimatedShareButton({
    required this.progress,
    this.onShare,
    this.buttonColor = WrappedColors.mint,
  });

  @override
  State<_AnimatedShareButton> createState() => _AnimatedShareButtonState();
}

class _AnimatedShareButtonState extends State<_AnimatedShareButton> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;
  bool _hasTriggered = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _animation = CurvedAnimation(
      parent: _controller,
      curve: Curves.elasticOut,
    );
  }

  @override
  void didUpdateWidget(_AnimatedShareButton oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.progress >= 1.0 && !_hasTriggered) {
      _hasTriggered = true;
      Future.delayed(const Duration(milliseconds: 300), () {
        if (mounted) _controller.forward();
      });
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _animation,
      builder: (context, child) {
        final scale = _animation.value;
        final opacity = _animation.value.clamp(0.0, 1.0);

        if (scale > 0) {
          return Opacity(
            opacity: opacity,
            child: Transform.scale(
              scale: scale == 0 ? 0 : (0.5 + scale * 0.5),
              alignment: Alignment.centerLeft,
              child: GestureDetector(
                onTap: () {
                  HapticFeedback.mediumImpact();
                  widget.onShare?.call();
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.ios_share,
                        color: widget.buttonColor,
                        size: 18,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'Share',
                        style: TextStyle(
                          color: widget.buttonColor,
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }

        return SizedBox(
          width: 32,
          height: 32,
          child: CustomPaint(
            painter: _CircularProgressPainter(
              progress: widget.progress,
              strokeWidth: 3,
              backgroundColor: Colors.white.withOpacity(0.3),
              progressColor: Colors.white,
            ),
          ),
        );
      },
    );
  }
}

// Custom circular progress painter
class _CircularProgressPainter extends CustomPainter {
  final double progress;
  final double strokeWidth;
  final Color backgroundColor;
  final Color progressColor;

  _CircularProgressPainter({
    required this.progress,
    required this.strokeWidth,
    required this.backgroundColor,
    required this.progressColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (size.width - strokeWidth) / 2;

    // Background circle
    final bgPaint = Paint()
      ..color = backgroundColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth;
    canvas.drawCircle(center, radius, bgPaint);

    // Progress arc
    final progressPaint = Paint()
      ..color = progressColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;

    final sweepAngle = 2 * math.pi * progress;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2, // Start from top
      sweepAngle,
      false,
      progressPaint,
    );
  }

  @override
  bool shouldRepaint(_CircularProgressPainter oldDelegate) {
    return oldDelegate.progress != progress;
  }
}

// Animated category chart widget
class _CategoryChartAnimated extends StatefulWidget {
  final List<_CategoryData> categories;
  final bool isActive;
  final VoidCallback? onShare;

  const _CategoryChartAnimated({
    required this.categories,
    required this.isActive,
    this.onShare,
  });

  @override
  State<_CategoryChartAnimated> createState() => _CategoryChartAnimatedState();
}

class _CategoryChartAnimatedState extends State<_CategoryChartAnimated> with TickerProviderStateMixin {
  late List<AnimationController> _sliceControllers;
  late List<Animation<double>> _sliceAnimations;
  late AnimationController _trophyController;
  late Animation<double> _trophyAnimation;

  bool _hasAnimated = false;

  @override
  void initState() {
    super.initState();

    final numSlices = widget.categories.length;
    _sliceControllers = List.generate(
      numSlices,
      (i) => AnimationController(
        duration: const Duration(milliseconds: 400),
        vsync: this,
      ),
    );

    _sliceAnimations = _sliceControllers.map((controller) {
      return CurvedAnimation(parent: controller, curve: Curves.easeOutCubic);
    }).toList();

    // Trophy slap animation
    _trophyController = AnimationController(
      duration: const Duration(milliseconds: 500),
      vsync: this,
    );
    _trophyAnimation = CurvedAnimation(
      parent: _trophyController,
      curve: Curves.elasticOut,
    );

    // Chain animations - each slice triggers next
    for (int i = 0; i < _sliceControllers.length - 1; i++) {
      _sliceControllers[i].addStatusListener((status) {
        if (status == AnimationStatus.completed && mounted) {
          HapticFeedback.selectionClick();
          _sliceControllers[i + 1].forward();
        }
      });
    }

    // Last slice triggers trophy
    if (_sliceControllers.isNotEmpty) {
      _sliceControllers.last.addStatusListener((status) {
        if (status == AnimationStatus.completed && mounted) {
          HapticFeedback.mediumImpact();
          Future.delayed(const Duration(milliseconds: 200), () {
            if (mounted) _trophyController.forward();
          });
        }
      });
    }

    _trophyController.addStatusListener((status) {
      if (status == AnimationStatus.completed && mounted) {
        HapticFeedback.heavyImpact();
      }
    });

    if (widget.isActive) {
      _startAnimation();
    }
  }

  void _startAnimation() {
    if (_hasAnimated || _sliceControllers.isEmpty) return;
    _hasAnimated = true;
    Future.delayed(const Duration(milliseconds: 300), () {
      if (mounted) {
        _sliceControllers.first.forward();
      }
    });
  }

  @override
  void didUpdateWidget(_CategoryChartAnimated oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !_hasAnimated) {
      _startAnimation();
    }
  }

  @override
  void dispose() {
    for (final controller in _sliceControllers) {
      controller.dispose();
    }
    _trophyController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([
        ..._sliceAnimations,
        _trophyAnimation,
      ]),
      builder: (context, child) {
        // Calculate how many slices are fully visible + current slice progress
        int fullyVisibleSlices = 0;
        double currentSliceProgress = 0.0;

        for (int i = 0; i < _sliceAnimations.length; i++) {
          if (_sliceAnimations[i].value >= 1.0) {
            fullyVisibleSlices++;
          } else if (_sliceAnimations[i].value > 0) {
            currentSliceProgress = _sliceAnimations[i].value;
            fullyVisibleSlices++;
            break;
          } else {
            break;
          }
        }

        // Badge opacity follows first slice animation
        final badgeOpacity = _sliceAnimations.isNotEmpty ? _sliceAnimations.first.value.clamp(0.0, 1.0) : 0.0;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 40),
            // Top badge
            Opacity(
              opacity: badgeOpacity,
              child: Transform.scale(
                scale: 0.5 + badgeOpacity * 0.5,
                alignment: Alignment.centerLeft,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Text(
                    'You Talked About',
                    style: TextStyle(
                      color: Color(0xFF2A9D8F),
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 24),
            // Animated pie chart
            SizedBox(
              width: 200,
              height: 200,
              child: CustomPaint(
                painter: _PieChartPainter(
                  categories: widget.categories,
                  showTrophy: _trophyAnimation.value > 0,
                  trophyScale: _trophyAnimation.value,
                  visibleSlices: fullyVisibleSlices,
                  lastSliceProgress: currentSliceProgress > 0 ? currentSliceProgress : 1.0,
                ),
              ),
            ),
            const SizedBox(height: 40),
            // Animated labels - appear as slices fill
            ...widget.categories.asMap().entries.map((entry) {
              final index = entry.key;
              final cat = entry.value;
              final isFirst = index == 0;

              // Label appears when its slice starts animating
              final labelOpacity =
                  index < _sliceAnimations.length ? _sliceAnimations[index].value.clamp(0.0, 1.0) : 0.0;

              return Opacity(
                opacity: labelOpacity,
                child: Transform.translate(
                  offset: Offset(20 * (1 - labelOpacity), 0),
                  child: Padding(
                    padding: EdgeInsets.symmetric(vertical: isFirst ? 12 : 10),
                    child: Row(
                      children: [
                        Container(
                          width: isFirst ? 24 : 20,
                          height: isFirst ? 24 : 20,
                          decoration: BoxDecoration(
                            color: cat.color,
                            borderRadius: BorderRadius.circular(4),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Text(
                            '${cat.name} · ${cat.percentage}%',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: isFirst ? 32 : 26,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            }),
            const Spacer(),
            // Share button
            _AnimatedShareButton(
              progress: _trophyAnimation.value,
              onShare: widget.onShare,
              buttonColor: WrappedColors.mint,
            ),
            const SizedBox(height: 20),
          ],
        );
      },
    );
  }
}

// Animated actions card widget
class _ActionsAnimated extends StatefulWidget {
  final int totalTasks;
  final int completedTasks;
  final int completionRate;
  final bool isActive;
  final VoidCallback? onShare;

  const _ActionsAnimated({
    required this.totalTasks,
    required this.completedTasks,
    required this.completionRate,
    required this.isActive,
    this.onShare,
  });

  @override
  State<_ActionsAnimated> createState() => _ActionsAnimatedState();
}

class _ActionsAnimatedState extends State<_ActionsAnimated> with TickerProviderStateMixin {
  late AnimationController _totalController;
  late AnimationController _completedController;
  late AnimationController _checkmarkController;
  late AnimationController _chipController;
  late AnimationController _strikethroughController;

  late Animation<double> _totalAnimation;
  late Animation<double> _completedAnimation;
  late Animation<double> _checkmarkAnimation;
  late Animation<double> _chipAnimation;
  late Animation<double> _strikethroughAnimation;

  bool _hasAnimated = false;
  int _lastTickValue = 0;
  final _numberFormat = NumberFormat('#,###');

  @override
  void initState() {
    super.initState();

    // Total tasks count-up animation
    _totalController = AnimationController(
      duration: const Duration(milliseconds: 1000),
      vsync: this,
    );
    _totalAnimation = CurvedAnimation(
      parent: _totalController,
      curve: Curves.easeOutCubic,
    );

    // Completed tasks count-up animation
    _completedController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _completedAnimation = CurvedAnimation(
      parent: _completedController,
      curve: Curves.easeOutCubic,
    );

    // Checkmark slap animation
    _checkmarkController = AnimationController(
      duration: const Duration(milliseconds: 500),
      vsync: this,
    );
    _checkmarkAnimation = CurvedAnimation(
      parent: _checkmarkController,
      curve: Curves.elasticOut,
    );

    // Chip slap animation (at top)
    _chipController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _chipAnimation = CurvedAnimation(
      parent: _chipController,
      curve: Curves.elasticOut,
    );

    // Strikethrough animation
    _strikethroughController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _strikethroughAnimation = CurvedAnimation(
      parent: _strikethroughController,
      curve: Curves.easeOut,
    );

    // Chain animations
    _totalController.addListener(_onTotalTick);
    _totalController.addStatusListener((status) {
      if (status == AnimationStatus.completed && mounted) {
        HapticFeedback.mediumImpact();
        _lastTickValue = 0;
        _completedController.forward();
      }
    });

    _completedController.addListener(_onCompletedTick);
    _completedController.addStatusListener((status) {
      if (status == AnimationStatus.completed && mounted) {
        HapticFeedback.mediumImpact();
        Future.delayed(const Duration(milliseconds: 200), () {
          if (mounted) _checkmarkController.forward();
        });
      }
    });

    _checkmarkController.addStatusListener((status) {
      if (status == AnimationStatus.completed && mounted) {
        HapticFeedback.heavyImpact();
        Future.delayed(const Duration(milliseconds: 200), () {
          if (mounted) _chipController.forward();
        });
      }
    });

    _chipController.addStatusListener((status) {
      if (status == AnimationStatus.completed && mounted) {
        HapticFeedback.heavyImpact();
        Future.delayed(const Duration(milliseconds: 200), () {
          if (mounted) _strikethroughController.forward();
        });
      }
    });

    if (widget.isActive) {
      _startAnimation();
    }
  }

  void _onTotalTick() {
    final current = (_totalAnimation.value * widget.totalTasks).toInt();
    final tickInterval = (widget.totalTasks / 15).ceil().clamp(1, 50);
    if ((current - _lastTickValue).abs() >= tickInterval) {
      _lastTickValue = current;
      HapticFeedback.selectionClick();
    }
  }

  void _onCompletedTick() {
    final current = (_completedAnimation.value * widget.completedTasks).toInt();
    final tickInterval = (widget.completedTasks / 12).ceil().clamp(1, 30);
    if ((current - _lastTickValue).abs() >= tickInterval) {
      _lastTickValue = current;
      HapticFeedback.selectionClick();
    }
  }

  void _startAnimation() {
    if (_hasAnimated) return;
    _hasAnimated = true;
    Future.delayed(const Duration(milliseconds: 300), () {
      if (mounted) {
        _totalController.forward();
      }
    });
  }

  @override
  void didUpdateWidget(_ActionsAnimated oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !_hasAnimated) {
      _startAnimation();
    }
  }

  @override
  void dispose() {
    _totalController.removeListener(_onTotalTick);
    _completedController.removeListener(_onCompletedTick);
    _totalController.dispose();
    _completedController.dispose();
    _checkmarkController.dispose();
    _chipController.dispose();
    _strikethroughController.dispose();
    super.dispose();
  }

  // Calculate overall progress (0.0 to 1.0)
  double get _overallProgress {
    if (!_hasAnimated) return 0.0;
    double progress = 0.0;
    progress += _totalAnimation.value * 0.30;
    progress += _completedAnimation.value * 0.30;
    progress += _checkmarkAnimation.value * 0.15;
    progress += _chipAnimation.value * 0.15;
    progress += _strikethroughAnimation.value * 0.10;
    return progress.clamp(0.0, 1.0);
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([
        _totalAnimation,
        _completedAnimation,
        _checkmarkAnimation,
        _chipAnimation,
        _strikethroughAnimation,
      ]),
      builder: (context, child) {
        final animatedTotal = (_totalAnimation.value * widget.totalTasks).toInt();
        final animatedCompleted = (_completedAnimation.value * widget.completedTasks).toInt();
        final checkmarkScale = _checkmarkAnimation.value;
        final chipScale = _chipAnimation.value;
        final strikethroughProgress = _strikethroughAnimation.value;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 40),
            // Completion rate chip at top - stamps in at the end
            Opacity(
              opacity: chipScale > 0 ? 1.0 : 0.0,
              child: Transform.scale(
                scale: chipScale == 0 ? 0 : (0.5 + chipScale * 0.5),
                alignment: Alignment.centerLeft,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        '${widget.completionRate}% ',
                        style: const TextStyle(
                          color: WrappedColors.indigo,
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      // "Completed" with strikethrough animation
                      Stack(
                        children: [
                          Text(
                            'Completed',
                            style: TextStyle(
                              color: WrappedColors.indigo,
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                              decoration:
                                  strikethroughProgress > 0.9 ? TextDecoration.lineThrough : TextDecoration.none,
                              decorationColor: WrappedColors.indigo,
                              decorationThickness: 2,
                            ),
                          ),
                          // Animated strikethrough line
                          if (strikethroughProgress > 0 && strikethroughProgress <= 0.9)
                            Positioned(
                              top: 0,
                              bottom: 0,
                              left: 0,
                              child: Center(
                                child: Container(
                                  width: 75 * strikethroughProgress,
                                  height: 2,
                                  color: WrappedColors.indigo,
                                ),
                              ),
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 32),
            // Tasks generated - counts up first
            Text(
              _numberFormat.format(animatedTotal),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 80,
                fontWeight: FontWeight.w900,
                height: 0.9,
              ),
            ),
            Opacity(
              opacity: _totalAnimation.value > 0.3 ? 1.0 : _totalAnimation.value / 0.3,
              child: const Text(
                'tasks generated',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 28,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(height: 36),
            // Tasks completed - counts up second, with checkmark
            Opacity(
              opacity: _completedController.isAnimating || _completedController.isCompleted ? 1.0 : 0.3,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _numberFormat.format(animatedCompleted),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 80,
                      fontWeight: FontWeight.w900,
                      height: 0.9,
                    ),
                  ),
                  Row(
                    children: [
                      Opacity(
                        opacity: _completedAnimation.value > 0.3 ? 1.0 : _completedAnimation.value / 0.3,
                        child: const Text(
                          'tasks completed',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 28,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      // Checkmark that slaps in
                      if (checkmarkScale > 0)
                        Transform.scale(
                          scale: checkmarkScale,
                          child: Container(
                            width: 32,
                            height: 32,
                            decoration: const BoxDecoration(
                              color: Color(0xFF4CAF50),
                              shape: BoxShape.circle,
                            ),
                            child: const Icon(
                              Icons.check,
                              color: Colors.white,
                              size: 20,
                            ),
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ),
            const Spacer(),
            // Share button
            _AnimatedShareButton(
              progress: _overallProgress,
              onShare: widget.onShare,
              buttonColor: WrappedColors.indigo,
            ),
            const SizedBox(height: 20),
          ],
        );
      },
    );
  }
}

// Category data for donut chart
class _CategoryData {
  final String name;
  final int percentage;
  final Color color;

  _CategoryData({
    required this.name,
    required this.percentage,
    required this.color,
  });
}

// Pie chart painter (filled) with animation support
class _PieChartPainter extends CustomPainter {
  final List<_CategoryData> categories;
  final bool showTrophy;
  final double trophyScale;
  final int visibleSlices; // How many slices to show (for animation)
  final double lastSliceProgress; // Progress of the last visible slice (0-1)

  _PieChartPainter({
    required this.categories,
    this.showTrophy = false,
    this.trophyScale = 1.0,
    this.visibleSlices = 999,
    this.lastSliceProgress = 1.0,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;

    // Calculate total percentage (should be ~100)
    final totalPct = categories.fold<int>(0, (sum, c) => sum + c.percentage);

    double startAngle = -math.pi / 2; // Start from top

    final slicesToDraw = visibleSlices.clamp(0, categories.length);

    for (int i = 0; i < slicesToDraw; i++) {
      final category = categories[i];
      double sweepAngle = (category.percentage / (totalPct > 0 ? totalPct : 100)) * 2 * math.pi;

      // If this is the last visible slice, apply progress
      if (i == slicesToDraw - 1 && lastSliceProgress < 1.0) {
        sweepAngle *= lastSliceProgress;
      }

      final paint = Paint()
        ..color = category.color
        ..style = PaintingStyle.fill;

      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        startAngle,
        sweepAngle,
        true, // Use center for pie chart
        paint,
      );

      startAngle += sweepAngle;
    }

    // Draw trophy emoji in the top (first) slice
    if (showTrophy && categories.isNotEmpty && trophyScale > 0) {
      final firstSweep = (categories[0].percentage / (totalPct > 0 ? totalPct : 100)) * 2 * math.pi;
      final midAngle = -math.pi / 2 + firstSweep / 2;
      final labelRadius = radius * 0.55;
      final labelX = center.dx + labelRadius * math.cos(midAngle);
      final labelY = center.dy + labelRadius * math.sin(midAngle);

      final textPainter = TextPainter(
        text: TextSpan(
          text: '🏆',
          style: TextStyle(
            fontSize: 36 * trophyScale,
          ),
        ),
        textDirection: ui.TextDirection.ltr,
      );
      textPainter.layout();
      textPainter.paint(
        canvas,
        Offset(labelX - textPainter.width / 2, labelY - textPainter.height / 2),
      );
    }
  }

  @override
  bool shouldRepaint(_PieChartPainter oldDelegate) {
    return oldDelegate.visibleSlices != visibleSlices ||
        oldDelegate.lastSliceProgress != lastSliceProgress ||
        oldDelegate.showTrophy != showTrophy ||
        oldDelegate.trophyScale != trophyScale;
  }
}

// Data class for memorable days
class _MemorableDayData {
  final String emoji;
  final String label;
  final String title;
  final String description;
  final String dateStr;
  final int month;
  final int day;

  _MemorableDayData({
    required this.emoji,
    required this.label,
    required this.title,
    required this.description,
    required this.dateStr,
  })  : month = _parseMonth(dateStr),
        day = _parseDay(dateStr);

  static int _parseMonth(String dateStr) {
    final months = {
      'january': 1,
      'february': 2,
      'march': 3,
      'april': 4,
      'may': 5,
      'june': 6,
      'july': 7,
      'august': 8,
      'september': 9,
      'october': 10,
      'november': 11,
      'december': 12,
    };
    final lower = dateStr.toLowerCase();
    for (final entry in months.entries) {
      if (lower.contains(entry.key)) return entry.value;
    }
    return 1;
  }

  static int _parseDay(String dateStr) {
    final match = RegExp(r'\d+').firstMatch(dateStr);
    if (match != null) {
      return int.tryParse(match.group(0)!) ?? 1;
    }
    return 1;
  }
}

// Animated Memorable Days Card with Calendar Animation
class _MemorableDaysAnimated extends StatefulWidget {
  final List<_MemorableDayData> days;
  final bool isActive;
  final String headerLine1;
  final String headerLine2;
  final String summaryBadgeText;
  final Color badgeColor;
  final bool isSingleMoment;
  final String? badgeEmoji;
  final VoidCallback? onShare;

  const _MemorableDaysAnimated({
    required this.days,
    required this.isActive,
    this.headerLine1 = 'Your',
    this.headerLine2 = 'Top Days',
    this.summaryBadgeText = 'Your Top Days',
    this.onShare,
    this.badgeColor = WrappedColors.teal,
    this.isSingleMoment = false,
    this.badgeEmoji,
  });

  @override
  State<_MemorableDaysAnimated> createState() => _MemorableDaysAnimatedState();
}

class _MemorableDaysAnimatedState extends State<_MemorableDaysAnimated> with TickerProviderStateMixin {
  late AnimationController _introController;
  late AnimationController _calendarController;
  late AnimationController _dayTransitionController;
  late AnimationController _summaryController;

  late Animation<double> _introAnimation;
  late Animation<double> _summaryAnimation;

  // Horizontal scroll controller for calendar
  late ScrollController _calendarScrollController;
  static const double _monthCardWidth = 280.0;

  bool _hasAnimated = false;
  int _currentDayIndex = 0;
  int _displayedMonth = 1; // Start from January
  double _circleScale = 0.0;
  double _detailsOpacity = 0.0;
  bool _showSummary = false; // Show final summary view

  // Month names
  static const _monthNames = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December'
  ];

  @override
  void initState() {
    super.initState();

    // Initialize scroll controller
    _calendarScrollController = ScrollController();

    // Intro animation - title appears
    _introController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _introAnimation = CurvedAnimation(
      parent: _introController,
      curve: Curves.easeOutCubic,
    );

    // Calendar scroll animation
    _calendarController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );

    // Day transition controller
    _dayTransitionController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );

    // Summary view animation
    _summaryController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _summaryAnimation = CurvedAnimation(
      parent: _summaryController,
      curve: Curves.easeOutCubic,
    );

    _introController.addStatusListener((status) {
      if (status == AnimationStatus.completed && mounted) {
        HapticFeedback.mediumImpact();
        _startCalendarSequence();
      }
    });

    if (widget.isActive) {
      _startAnimation();
    }
  }

  void _startAnimation() {
    if (_hasAnimated) return;
    _hasAnimated = true;
    Future.delayed(const Duration(milliseconds: 300), () {
      if (mounted) {
        _introController.forward();
      }
    });
  }

  void _startCalendarSequence() async {
    if (widget.days.isEmpty) return;

    // Animate to each day in sequence
    for (int i = 0; i < widget.days.length; i++) {
      if (!mounted) return;

      setState(() => _currentDayIndex = i);
      final targetDay = widget.days[i];

      // Scroll through months to reach the target
      await _scrollToMonth(targetDay.month);

      if (!mounted) return;

      // Circle the date
      await _circleDate();

      if (!mounted) return;

      // Show details
      await _showDetails();

      if (!mounted) return;

      // Pause to display
      await Future.delayed(const Duration(milliseconds: 1500));

      if (!mounted) return;

      // Fade out details before next day
      await _hideDetails();
    }

    // After all days shown, transition to summary view
    if (!mounted) return;
    await Future.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;

    setState(() => _showSummary = true);
    _summaryController.forward();
    HapticFeedback.mediumImpact();
  }

  Future<void> _scrollToMonth(int targetMonth) async {
    // Animate scroll to target month, centered in viewport
    if (_calendarScrollController.hasClients) {
      final viewportWidth = _calendarScrollController.position.viewportDimension;
      // Calculate offset to center the target month
      // Left edge of target month - offset to center it
      final monthLeftEdge = (targetMonth - 1) * (_monthCardWidth + 12); // +12 for margin
      final centerOffset = monthLeftEdge - (viewportWidth - _monthCardWidth) / 2;
      // Clamp to valid scroll range
      final maxScroll = _calendarScrollController.position.maxScrollExtent;
      final targetOffset = centerOffset.clamp(0.0, maxScroll);

      await _calendarScrollController.animateTo(
        targetOffset,
        duration: Duration(milliseconds: 300 + (targetMonth - _displayedMonth).abs() * 100),
        curve: Curves.easeOutCubic,
      );
    }

    if (!mounted) return;
    setState(() {
      _displayedMonth = targetMonth;
    });
    HapticFeedback.selectionClick();
  }

  Future<void> _circleDate() async {
    // Animate circle appearing
    for (double scale = 0.0; scale <= 1.0; scale += 0.1) {
      if (!mounted) return;
      await Future.delayed(const Duration(milliseconds: 20));
      if (!mounted) return;
      setState(() => _circleScale = scale);
    }
    if (!mounted) return;
    setState(() => _circleScale = 1.0);
    HapticFeedback.mediumImpact();
  }

  Future<void> _showDetails() async {
    // Fade in details
    for (double opacity = 0.0; opacity <= 1.0; opacity += 0.1) {
      if (!mounted) return;
      await Future.delayed(const Duration(milliseconds: 30));
      if (!mounted) return;
      setState(() => _detailsOpacity = opacity);
    }
    if (!mounted) return;
    setState(() => _detailsOpacity = 1.0);
  }

  Future<void> _hideDetails() async {
    // Fade out details and circle
    for (double val = 1.0; val >= 0.0; val -= 0.15) {
      if (!mounted) return;
      await Future.delayed(const Duration(milliseconds: 25));
      if (!mounted) return;
      setState(() {
        _detailsOpacity = val;
        _circleScale = val;
      });
    }
    if (!mounted) return;
    setState(() {
      _detailsOpacity = 0.0;
      _circleScale = 0.0;
    });
  }

  @override
  void didUpdateWidget(_MemorableDaysAnimated oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !_hasAnimated) {
      _startAnimation();
    }
  }

  @override
  void dispose() {
    _introController.dispose();
    _calendarController.dispose();
    _dayTransitionController.dispose();
    _summaryController.dispose();
    _calendarScrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Show summary view after calendar animation completes
    if (_showSummary) {
      return AnimatedBuilder(
        animation: _summaryAnimation,
        builder: (context, child) => _buildSummaryView(),
      );
    }

    return AnimatedBuilder(
      animation: _introAnimation,
      builder: (context, child) {
        final currentDay =
            widget.days.isNotEmpty && _currentDayIndex < widget.days.length ? widget.days[_currentDayIndex] : null;

        return Column(
          children: [
            const SizedBox(height: 20),
            // Title
            Opacity(
              opacity: _introAnimation.value,
              child: Transform.translate(
                offset: Offset(0, 20 * (1 - _introAnimation.value)),
                child: Column(
                  children: [
                    Text(
                      widget.headerLine1,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 20,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    Text(
                      widget.headerLine2,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 36,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
            // Calendar view
            if (_introAnimation.value > 0.5)
              Opacity(
                opacity: ((_introAnimation.value - 0.5) * 2).clamp(0.0, 1.0),
                child: _buildCalendar(currentDay),
              ),
            const SizedBox(height: 20),
            // Day details card
            if (currentDay != null && _detailsOpacity > 0)
              Opacity(
                opacity: _detailsOpacity,
                child: Transform.translate(
                  offset: Offset(0, 20 * (1 - _detailsOpacity)),
                  child: _buildDayDetails(currentDay),
                ),
              ),
            const Spacer(),
            // Day indicators
            if (_introAnimation.value > 0.8)
              Opacity(
                opacity: ((_introAnimation.value - 0.8) * 5).clamp(0.0, 1.0),
                child: _buildDayIndicators(),
              ),
            const SizedBox(height: 20),
          ],
        );
      },
    );
  }

  // Final summary view similar to Year in Numbers / Actions card
  Widget _buildSummaryView() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 40),
        // Title badge
        Opacity(
          opacity: _summaryAnimation.value,
          child: Transform.scale(
            scale: 0.5 + _summaryAnimation.value * 0.5,
            alignment: Alignment.centerLeft,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(20),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (widget.badgeEmoji != null) ...[
                    Text(
                      widget.badgeEmoji!,
                      style: const TextStyle(fontSize: 18),
                    ),
                    const SizedBox(width: 6),
                  ],
                  Text(
                    widget.summaryBadgeText,
                    style: TextStyle(
                      color: widget.badgeColor,
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 24),
        // Days list - stacked vertically like Year in Numbers
        ...widget.days.asMap().entries.map((entry) {
          final index = entry.key;
          final day = entry.value;
          // Stagger the animation for each day
          final delayedProgress = ((_summaryAnimation.value - index * 0.15) / 0.7).clamp(0.0, 1.0);

          return Opacity(
            opacity: delayedProgress,
            child: Transform.translate(
              offset: Offset(30 * (1 - delayedProgress), 0),
              child: Padding(
                padding: EdgeInsets.only(bottom: index < widget.days.length - 1 ? 28 : 0),
                child: _buildSummaryDayItem(day, delayedProgress),
              ),
            ),
          );
        }),
        const Spacer(),
        // Share button
        _AnimatedShareButton(
          progress: _summaryAnimation.value,
          onShare: widget.onShare,
          buttonColor: widget.badgeColor,
        ),
        const SizedBox(height: 20),
      ],
    );
  }

  Widget _buildSummaryDayItem(_MemorableDayData day, double progress) {
    final isSingle = widget.isSingleMoment;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // For single moments (funniest/cringe), just show date since emoji is in badge
        // For multi-day (Your Top Days), show emoji + label + date
        if (isSingle) ...[
          // Just date for single moments (emoji is in the badge)
          Text(
            day.dateStr,
            style: TextStyle(
              color: Colors.white.withOpacity(0.6),
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 12),
        ] else ...[
          // Label with emoji and date in same row for multi-day
          Row(
            children: [
              Text(
                day.emoji,
                style: const TextStyle(fontSize: 20),
              ),
              const SizedBox(width: 10),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 8,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  day.label.toUpperCase(),
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.9),
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '·',
                style: TextStyle(
                  color: Colors.white.withOpacity(0.5),
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                day.dateStr,
                style: TextStyle(
                  color: Colors.white.withOpacity(0.6),
                  fontSize: 10,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
        ],
        // Title as text
        Text(
          day.title,
          style: TextStyle(
            color: Colors.white,
            fontSize: isSingle ? 32 : 20,
            fontWeight: FontWeight.w700,
            height: 1.3,
          ),
        ),
        // Description if available
        if (day.description.isNotEmpty) ...[
          SizedBox(height: isSingle ? 16 : 6),
          Text(
            day.description,
            style: TextStyle(
              color: Colors.white.withOpacity(0.85),
              fontSize: isSingle ? 18 : 14,
              fontWeight: FontWeight.w400,
              height: 1.4,
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildCalendar(_MemorableDayData? currentDay) {
    return SizedBox(
      height: 220,
      child: ListView.builder(
        controller: _calendarScrollController,
        scrollDirection: Axis.horizontal,
        physics: const NeverScrollableScrollPhysics(), // Controlled programmatically
        itemCount: 12,
        itemBuilder: (context, index) {
          final month = index + 1;
          final daysInMonth = _getDaysInMonth(month, 2025);
          final firstDayOfWeek = _getFirstDayOfWeek(month, 2025);
          final isTargetMonth = currentDay?.month == month;

          return Container(
            width: _monthCardWidth,
            margin: const EdgeInsets.only(right: 12),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(isTargetMonth ? 0.2 : 0.1),
              borderRadius: BorderRadius.circular(16),
              border: isTargetMonth ? Border.all(color: Colors.white.withOpacity(0.3), width: 1) : null,
            ),
            child: Column(
              children: [
                // Month header
                Text(
                  _monthNames[month - 1],
                  style: TextStyle(
                    color: Colors.white.withOpacity(isTargetMonth ? 1.0 : 0.6),
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                // Day headers
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                  children: ['S', 'M', 'T', 'W', 'T', 'F', 'S']
                      .map((d) => SizedBox(
                            width: 28,
                            child: Text(
                              d,
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: Colors.white.withOpacity(0.5),
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ))
                      .toList(),
                ),
                const SizedBox(height: 4),
                // Calendar grid
                Expanded(
                  child: _buildMonthGrid(month, daysInMonth, firstDayOfWeek, currentDay),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildMonthGrid(int month, int daysInMonth, int firstDayOfWeek, _MemorableDayData? currentDay) {
    final targetDay = currentDay?.month == month ? currentDay?.day : null;

    List<Widget> rows = [];
    List<Widget> currentRow = [];

    // Add empty cells for days before the 1st
    for (int i = 0; i < firstDayOfWeek; i++) {
      currentRow.add(const SizedBox(width: 28, height: 24));
    }

    // Add day cells
    for (int day = 1; day <= daysInMonth; day++) {
      final isTarget = day == targetDay;

      currentRow.add(
        SizedBox(
          width: 28,
          height: 24,
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Circle highlight for target day
              if (isTarget && _circleScale > 0)
                Transform.scale(
                  scale: _circleScale,
                  child: Container(
                    width: 24,
                    height: 24,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: Colors.white,
                        width: 2,
                      ),
                      color: Colors.white.withOpacity(0.3),
                    ),
                  ),
                ),
              Text(
                '$day',
                style: TextStyle(
                  color: isTarget && _circleScale > 0.5 ? Colors.white : Colors.white.withOpacity(0.7),
                  fontSize: 11,
                  fontWeight: isTarget && _circleScale > 0.5 ? FontWeight.w800 : FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      );

      // Start new row after Saturday
      if ((firstDayOfWeek + day) % 7 == 0) {
        rows.add(
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: currentRow,
          ),
        );
        currentRow = [];
      }
    }

    // Add remaining days in the last row
    if (currentRow.isNotEmpty) {
      while (currentRow.length < 7) {
        currentRow.add(const SizedBox(width: 28, height: 24));
      }
      rows.add(
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: currentRow,
        ),
      );
    }

    return Column(
      mainAxisAlignment: MainAxisAlignment.start,
      children: rows,
    );
  }

  Widget _buildDayDetails(_MemorableDayData day) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 8),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.2),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        children: [
          Text(day.emoji, style: const TextStyle(fontSize: 36)),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  day.label.toUpperCase(),
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.7),
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.5,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  day.title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                if (day.description.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    day.description,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.8),
                      fontSize: 13,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDayIndicators() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(widget.days.length, (index) {
        final isActive = index == _currentDayIndex;
        final isPast = index < _currentDayIndex;
        return Container(
          width: isActive ? 24 : 8,
          height: 8,
          margin: const EdgeInsets.symmetric(horizontal: 4),
          decoration: BoxDecoration(
            color: isActive || isPast ? Colors.white : Colors.white.withOpacity(0.3),
            borderRadius: BorderRadius.circular(4),
          ),
        );
      }),
    );
  }

  int _getDaysInMonth(int month, int year) {
    return DateTime(year, month + 1, 0).day;
  }

  int _getFirstDayOfWeek(int month, int year) {
    return DateTime(year, month, 1).weekday % 7;
  }
}

// Data class for typewriter end page items
class _TypewriterItem {
  final String label;
  final String value;
  final String? emoji;

  const _TypewriterItem({
    required this.label,
    required this.value,
    this.emoji,
  });
}

// Animated end-page widget with typewriter effect (like Top Days summary)
class _TypewriterEndPageAnimated extends StatefulWidget {
  final String badgeText;
  final Color badgeColor;
  final List<_TypewriterItem> items;
  final bool isActive;
  final bool showProgressRing;
  final VoidCallback? onShare;

  const _TypewriterEndPageAnimated({
    required this.badgeText,
    required this.badgeColor,
    required this.items,
    required this.isActive,
    this.showProgressRing = true,
    this.onShare,
  });

  @override
  State<_TypewriterEndPageAnimated> createState() => _TypewriterEndPageAnimatedState();
}

class _TypewriterEndPageAnimatedState extends State<_TypewriterEndPageAnimated> with TickerProviderStateMixin {
  late AnimationController _mainController;
  late Animation<double> _mainAnimation;
  late List<AnimationController> _itemControllers;
  late List<Animation<double>> _itemAnimations;

  bool _hasAnimated = false;

  @override
  void initState() {
    super.initState();

    _mainController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _mainAnimation = CurvedAnimation(
      parent: _mainController,
      curve: Curves.easeOutCubic,
    );

    // Create controllers for each item
    _itemControllers = List.generate(
      widget.items.length,
      (index) => AnimationController(
        duration: const Duration(milliseconds: 500),
        vsync: this,
      ),
    );
    _itemAnimations = _itemControllers.map((c) => CurvedAnimation(parent: c, curve: Curves.easeOutBack)).toList();

    if (widget.isActive) {
      _startAnimation();
    }
  }

  void _startAnimation() async {
    if (_hasAnimated) return;
    _hasAnimated = true;

    await Future.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;

    _mainController.forward();
    HapticFeedback.mediumImpact();

    // Stagger item animations
    for (int i = 0; i < _itemControllers.length; i++) {
      await Future.delayed(const Duration(milliseconds: 120));
      if (!mounted) return;
      _itemControllers[i].forward();
      HapticFeedback.selectionClick();
    }
  }

  @override
  void didUpdateWidget(_TypewriterEndPageAnimated oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !_hasAnimated) {
      _startAnimation();
    }
  }

  @override
  void dispose() {
    _mainController.dispose();
    for (final c in _itemControllers) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _mainAnimation,
      builder: (context, child) {
        final mainOpacity = _mainAnimation.value.clamp(0.0, 1.0);

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 40),
            // Title badge
            Opacity(
              opacity: mainOpacity,
              child: Transform.scale(
                scale: 0.5 + mainOpacity * 0.5,
                alignment: Alignment.centerLeft,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    widget.badgeText,
                    style: TextStyle(
                      color: widget.badgeColor,
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 32),
            // Items list
            ...widget.items.asMap().entries.map((entry) {
              final index = entry.key;
              final item = entry.value;

              return AnimatedBuilder(
                animation: _itemAnimations.length > index ? _itemAnimations[index] : _mainAnimation,
                builder: (context, child) {
                  final rawProgress = _itemAnimations.length > index ? _itemAnimations[index].value : 0.0;
                  final progress = rawProgress.clamp(0.0, 1.0);

                  return Opacity(
                    opacity: progress,
                    child: Transform.translate(
                      offset: Offset(-30 * (1 - rawProgress), 0),
                      child: Padding(
                        padding: const EdgeInsets.only(bottom: 20),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Rank number
                            Container(
                              width: 28,
                              height: 28,
                              decoration: BoxDecoration(
                                color: Colors.white.withOpacity(0.2),
                                shape: BoxShape.circle,
                              ),
                              child: Center(
                                child: Text(
                                  '${index + 1}',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 14,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            // Emoji
                            Text(
                              item.emoji ?? '',
                              style: const TextStyle(fontSize: 28),
                            ),
                            const SizedBox(width: 12),
                            // Content
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    item.label.toUpperCase(),
                                    style: TextStyle(
                                      color: Colors.white.withOpacity(0.6),
                                      fontSize: 11,
                                      fontWeight: FontWeight.w700,
                                      letterSpacing: 1.0,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    item.value,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 18,
                                      fontWeight: FontWeight.w700,
                                      height: 1.2,
                                    ),
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
            }),
            const Spacer(),
            // Share button
            _AnimatedShareButton(
              progress: mainOpacity,
              onShare: widget.onShare,
              buttonColor: widget.badgeColor,
            ),
            const SizedBox(height: 20),
          ],
        );
      },
    );
  }
}

// Animated Top 5 Phrases widget - left aligned with staggered animations
class _TopPhrasesAnimated extends StatefulWidget {
  final List<String> phrases;
  final bool isActive;
  final VoidCallback? onShare;

  const _TopPhrasesAnimated({
    required this.phrases,
    required this.isActive,
    this.onShare,
  });

  @override
  State<_TopPhrasesAnimated> createState() => _TopPhrasesAnimatedState();
}

class _TopPhrasesAnimatedState extends State<_TopPhrasesAnimated> with TickerProviderStateMixin {
  late AnimationController _mainController;
  late Animation<double> _mainAnimation;
  late List<AnimationController> _phraseControllers;
  late List<Animation<double>> _phraseAnimations;

  bool _hasAnimated = false;

  @override
  void initState() {
    super.initState();

    _mainController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _mainAnimation = CurvedAnimation(
      parent: _mainController,
      curve: Curves.easeOutCubic,
    );

    _phraseControllers = List.generate(
      widget.phrases.length,
      (index) => AnimationController(
        duration: const Duration(milliseconds: 600),
        vsync: this,
      ),
    );
    _phraseAnimations = _phraseControllers.map((c) => CurvedAnimation(parent: c, curve: Curves.easeOutBack)).toList();

    if (widget.isActive) {
      _startAnimation();
    }
  }

  void _startAnimation() async {
    if (_hasAnimated) return;
    _hasAnimated = true;

    await Future.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;

    _mainController.forward();
    HapticFeedback.mediumImpact();

    // Stagger phrase animations
    for (int i = 0; i < _phraseControllers.length; i++) {
      await Future.delayed(const Duration(milliseconds: 150));
      if (!mounted) return;
      _phraseControllers[i].forward();
      HapticFeedback.selectionClick();
    }
  }

  @override
  void didUpdateWidget(_TopPhrasesAnimated oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !_hasAnimated) {
      _startAnimation();
    }
  }

  @override
  void dispose() {
    _mainController.dispose();
    for (final c in _phraseControllers) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _mainAnimation,
      builder: (context, child) {
        final mainOpacity = _mainAnimation.value.clamp(0.0, 1.0);

        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 40),
              // Badge
              Opacity(
                opacity: mainOpacity,
                child: Transform.scale(
                  scale: 0.5 + mainOpacity * 0.5,
                  alignment: Alignment.centerLeft,
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: const Text(
                        'Top 5 Phrases',
                        style: TextStyle(
                          color: WrappedColors.orange,
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 32),
              // Phrases list
              ...widget.phrases.asMap().entries.map((entry) {
                final index = entry.key;
                final phrase = entry.value;

                return AnimatedBuilder(
                  animation: _phraseAnimations.length > index ? _phraseAnimations[index] : _mainAnimation,
                  builder: (context, child) {
                    final rawProgress = _phraseAnimations.length > index ? _phraseAnimations[index].value : 0.0;
                    final progress = rawProgress.clamp(0.0, 1.0);

                    return Opacity(
                      opacity: progress,
                      child: Transform.translate(
                        offset: Offset(-40 * (1 - rawProgress), 0),
                        child: Padding(
                          padding: const EdgeInsets.only(bottom: 20),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Container(
                                width: 32,
                                height: 32,
                                decoration: BoxDecoration(
                                  color: Colors.white.withOpacity(0.2),
                                  shape: BoxShape.circle,
                                ),
                                child: Center(
                                  child: Text(
                                    '${index + 1}',
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 16,
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 16),
                              Expanded(
                                child: Text(
                                  '"$phrase"',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 24,
                                    fontWeight: FontWeight.w600,
                                    fontStyle: FontStyle.italic,
                                    height: 1.3,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                );
              }),
              const Spacer(),
              // Share button
              Align(
                alignment: Alignment.centerLeft,
                child: _AnimatedShareButton(
                  progress: mainOpacity,
                  onShare: widget.onShare,
                  buttonColor: WrappedColors.blue,
                ),
              ),
              const SizedBox(height: 20),
            ],
          ),
        );
      },
    );
  }
}

// Data class for buddy information
class _BuddyData {
  final String name;
  final String relationship;
  final String context;
  final String emoji;

  const _BuddyData({
    required this.name,
    required this.relationship,
    required this.context,
    required this.emoji,
  });
}

// Animated My Buddies widget - shows top 5 people
class _MyBuddiesAnimated extends StatefulWidget {
  final List<_BuddyData> buddies;
  final bool isActive;
  final VoidCallback? onShare;

  const _MyBuddiesAnimated({
    required this.buddies,
    required this.isActive,
    this.onShare,
  });

  @override
  State<_MyBuddiesAnimated> createState() => _MyBuddiesAnimatedState();
}

class _MyBuddiesAnimatedState extends State<_MyBuddiesAnimated> with TickerProviderStateMixin {
  late AnimationController _mainController;
  late Animation<double> _mainAnimation;
  late List<AnimationController> _buddyControllers;
  late List<Animation<double>> _buddyAnimations;

  bool _hasAnimated = false;

  @override
  void initState() {
    super.initState();

    _mainController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _mainAnimation = CurvedAnimation(
      parent: _mainController,
      curve: Curves.easeOutCubic,
    );

    _buddyControllers = List.generate(
      widget.buddies.length,
      (index) => AnimationController(
        duration: const Duration(milliseconds: 500),
        vsync: this,
      ),
    );
    _buddyAnimations = _buddyControllers.map((c) => CurvedAnimation(parent: c, curve: Curves.easeOutBack)).toList();

    if (widget.isActive) {
      _startAnimation();
    }
  }

  void _startAnimation() async {
    if (_hasAnimated) return;
    _hasAnimated = true;

    await Future.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;

    _mainController.forward();
    HapticFeedback.mediumImpact();

    // Stagger buddy animations
    for (int i = 0; i < _buddyControllers.length; i++) {
      await Future.delayed(const Duration(milliseconds: 120));
      if (!mounted) return;
      _buddyControllers[i].forward();
      HapticFeedback.selectionClick();
    }
  }

  @override
  void didUpdateWidget(_MyBuddiesAnimated oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !_hasAnimated) {
      _startAnimation();
    }
  }

  @override
  void dispose() {
    _mainController.dispose();
    for (final c in _buddyControllers) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _mainAnimation,
      builder: (context, child) {
        final mainOpacity = _mainAnimation.value.clamp(0.0, 1.0);

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 40),
            // Badge
            Opacity(
              opacity: mainOpacity,
              child: Transform.scale(
                scale: 0.5 + mainOpacity * 0.5,
                alignment: Alignment.centerLeft,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text('👥', style: TextStyle(fontSize: 18)),
                      SizedBox(width: 6),
                      Text(
                        'My Buddies',
                        style: TextStyle(
                          color: Color(0xFF6B5B95),
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 24),
            // Buddies list
            ...widget.buddies.asMap().entries.map((entry) {
              final index = entry.key;
              final buddy = entry.value;

              return AnimatedBuilder(
                animation: _buddyAnimations.length > index ? _buddyAnimations[index] : _mainAnimation,
                builder: (context, child) {
                  final rawProgress = _buddyAnimations.length > index ? _buddyAnimations[index].value : 0.0;
                  final progress = rawProgress.clamp(0.0, 1.0);

                  return Opacity(
                    opacity: progress,
                    child: Transform.translate(
                      offset: Offset(-30 * (1 - rawProgress), 0),
                      child: Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Rank number
                            Container(
                              width: 28,
                              height: 28,
                              decoration: BoxDecoration(
                                color: Colors.white.withOpacity(0.2),
                                shape: BoxShape.circle,
                              ),
                              child: Center(
                                child: Text(
                                  '${index + 1}',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 14,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            // Emoji
                            Text(
                              buddy.emoji,
                              style: const TextStyle(fontSize: 28),
                            ),
                            const SizedBox(width: 12),
                            // Info
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    buddy.name,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 20,
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    buddy.relationship,
                                    style: TextStyle(
                                      color: Colors.white.withOpacity(0.7),
                                      fontSize: 12,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    buddy.context,
                                    style: TextStyle(
                                      color: Colors.white.withOpacity(0.6),
                                      fontSize: 13,
                                      fontStyle: FontStyle.italic,
                                    ),
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
            }),
            const Spacer(),
            // Share button
            _AnimatedShareButton(
              progress: mainOpacity,
              onShare: widget.onShare,
              buttonColor: const Color(0xFF6B5B95),
            ),
            const SizedBox(height: 20),
          ],
        );
      },
    );
  }
}

// Animated Big Moment widget for Struggle/Win - left aligned
class _BigMomentAnimated extends StatefulWidget {
  final String emoji;
  final String headerLine1;
  final String headerLine2;
  final String title;
  final String subtitle;
  final bool isActive;
  final VoidCallback? onShare;
  final Color? buttonColor;

  const _BigMomentAnimated({
    required this.emoji,
    required this.headerLine1,
    required this.headerLine2,
    required this.title,
    required this.subtitle,
    required this.isActive,
    this.onShare,
    this.buttonColor,
  });

  @override
  State<_BigMomentAnimated> createState() => _BigMomentAnimatedState();
}

class _BigMomentAnimatedState extends State<_BigMomentAnimated> with TickerProviderStateMixin {
  late AnimationController _mainController;
  late Animation<double> _mainAnimation;
  late AnimationController _titleController;
  late Animation<double> _titleAnimation;
  late AnimationController _contentController;
  late Animation<double> _contentAnimation;

  bool _hasAnimated = false;

  @override
  void initState() {
    super.initState();

    _mainController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _mainAnimation = CurvedAnimation(
      parent: _mainController,
      curve: Curves.easeOutCubic,
    );

    _titleController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );
    _titleAnimation = CurvedAnimation(
      parent: _titleController,
      curve: Curves.easeOutBack,
    );

    _contentController = AnimationController(
      duration: const Duration(milliseconds: 700),
      vsync: this,
    );
    _contentAnimation = CurvedAnimation(
      parent: _contentController,
      curve: Curves.easeOutCubic,
    );

    if (widget.isActive) {
      _startAnimation();
    }
  }

  void _startAnimation() async {
    if (_hasAnimated) return;
    _hasAnimated = true;

    await Future.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;

    _mainController.forward();
    HapticFeedback.mediumImpact();

    await Future.delayed(const Duration(milliseconds: 400));
    if (!mounted) return;
    _titleController.forward();
    HapticFeedback.selectionClick();

    await Future.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;
    _contentController.forward();
  }

  @override
  void didUpdateWidget(_BigMomentAnimated oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !_hasAnimated) {
      _startAnimation();
    }
  }

  @override
  void dispose() {
    _mainController.dispose();
    _titleController.dispose();
    _contentController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([_mainAnimation, _titleAnimation, _contentAnimation]),
      builder: (context, child) {
        final mainOpacity = _mainAnimation.value.clamp(0.0, 1.0);
        final titleOpacity = _titleAnimation.value.clamp(0.0, 1.0);
        final contentOpacity = _contentAnimation.value.clamp(0.0, 1.0);

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 40),
            // Emoji with scale animation
            Opacity(
              opacity: mainOpacity,
              child: Transform.scale(
                scale: 0.3 + mainOpacity * 0.7,
                alignment: Alignment.centerLeft,
                child: Text(
                  widget.emoji,
                  style: const TextStyle(fontSize: 72),
                ),
              ),
            ),
            const SizedBox(height: 24),
            // Header lines
            Opacity(
              opacity: titleOpacity,
              child: Transform.translate(
                offset: Offset(-30 * (1 - titleOpacity), 0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.headerLine1,
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.8),
                        fontSize: 24,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    Text(
                      widget.headerLine2,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 56,
                        fontWeight: FontWeight.w900,
                        height: 1.1,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 32),
            // Title quote - right below header
            Opacity(
              opacity: contentOpacity,
              child: Transform.translate(
                offset: Offset(0, 20 * (1 - contentOpacity)),
                child: Text(
                  '"${widget.title}"',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.w600,
                    fontStyle: FontStyle.italic,
                    height: 1.4,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 72),
            // Subtitle directly under the main quote
            Opacity(
              opacity: contentOpacity,
              child: Text(
                widget.subtitle,
                style: TextStyle(
                  color: Colors.white.withOpacity(0.7),
                  fontSize: 18,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            const Spacer(),
            // Share button
            _AnimatedShareButton(
              progress: contentOpacity,
              onShare: widget.onShare,
              buttonColor: widget.buttonColor ?? WrappedColors.coral,
            ),
            const SizedBox(height: 20),
          ],
        );
      },
    );
  }
}

// Summary Collage animated final page - dense, max-info layout
class _SummaryCollageAnimated extends StatefulWidget {
  final Map<String, dynamic> result;
  final bool isActive;
  final VoidCallback? onShare;
  final String Function(String) formatCategory;
  final String Function(String) capitalizeWords;
  final double Function(int) calculatePercentile;

  const _SummaryCollageAnimated({
    required this.result,
    required this.isActive,
    this.onShare,
    required this.formatCategory,
    required this.capitalizeWords,
    required this.calculatePercentile,
  });

  @override
  State<_SummaryCollageAnimated> createState() => _SummaryCollageAnimatedState();
}

class _SummaryCollageAnimatedState extends State<_SummaryCollageAnimated> with TickerProviderStateMixin {
  late AnimationController _mainController;
  late Animation<double> _mainAnimation;
  late AnimationController _tilesController;
  late Animation<double> _tilesAnimation;

  bool _hasAnimated = false;

  @override
  void initState() {
    super.initState();

    _mainController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _mainAnimation = CurvedAnimation(
      parent: _mainController,
      curve: Curves.easeOutCubic,
    );

    _tilesController = AnimationController(
      duration: const Duration(milliseconds: 1200),
      vsync: this,
    );
    _tilesAnimation = CurvedAnimation(
      parent: _tilesController,
      curve: Curves.easeOutCubic,
    );

    _mainController.addStatusListener((status) {
      if (status == AnimationStatus.completed && mounted) {
        _tilesController.forward();
      }
    });

    if (widget.isActive) {
      _startAnimation();
    }
  }

  void _startAnimation() async {
    if (_hasAnimated) return;
    _hasAnimated = true;

    await Future.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;

    _mainController.forward();
    HapticFeedback.mediumImpact();
  }

  @override
  void didUpdateWidget(_SummaryCollageAnimated oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !_hasAnimated) {
      _startAnimation();
    }
  }

  @override
  void dispose() {
    _mainController.dispose();
    _tilesController.dispose();
    super.dispose();
  }

  String _formatNumber(int num) {
    if (num >= 1000) {
      return '${(num / 1000).toStringAsFixed(1)}k';
    }
    return num.toString();
  }

  @override
  Widget build(BuildContext context) {
    final totalHours = (widget.result['total_time_hours'] ?? 0.0) as num;
    final totalMinutes = (totalHours * 60).toInt();
    final totalConvs = widget.result['total_conversations'] ?? 0;
    final daysActive = widget.result['days_active'] ?? (totalConvs / 3).ceil();
    final percentile = widget.calculatePercentile(totalConvs);

    // Buddies
    final buddiesRaw = (widget.result['top_buddies'] as List<dynamic>?) ?? [];

    // Obsessions
    final obsessions = widget.result['obsessions'] as Map<String, dynamic>?;

    // Phrases
    final phrases = widget.result['top_phrases'] as List<dynamic>? ?? [];

    // Actions
    final totalActions = widget.result['total_action_items'] ?? 0;
    final completedActions = widget.result['completed_action_items'] ?? 0;
    final completionRate = (((widget.result['action_items_completion_rate'] ?? 0.0) as num) * 100).toInt();

    // Signature + archetype
    final archetype = (widget.result['decision_style'] as Map<String, dynamic>?)?['name'] ?? 'Thinker';
    final signaturePhrase = (widget.result['signature_phrase'] as Map<String, dynamic>?)?['phrase'] ?? 'okay';
    final signatureCount = (widget.result['signature_phrase'] as Map<String, dynamic>?)?['count'] ?? 0;

    // Struggle + Win
    final struggle = (widget.result['struggle'] as Map<String, dynamic>?)?['title'] ?? 'The Hard Part';
    final biggestWin = (widget.result['personal_win'] as Map<String, dynamic>?)?['title'] ?? 'Personal Growth';

    return AnimatedBuilder(
      animation: Listenable.merge([_mainAnimation, _tilesAnimation]),
      builder: (context, child) {
        final mainOpacity = _mainAnimation.value.clamp(0.0, 1.0);
        final tilesProgress = _tilesAnimation.value.clamp(0.0, 1.0);

        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SizedBox(height: 24),
            // Header with 2025 and percentile
            Opacity(
              opacity: mainOpacity,
              child: Transform.translate(
                offset: Offset(0, 20 * (1 - mainOpacity)),
                child: Row(
                  children: [
                    ShaderMask(
                      shaderCallback: (bounds) => const LinearGradient(
                        colors: [Color(0xFF4ECDC4), Color(0xFF44A08D)],
                      ).createShader(bounds),
                      child: const Text(
                        '2025',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 48,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ),
                    const Spacer(),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Text(
                        'Top $percentile% User',
                        style: const TextStyle(
                          color: WrappedColors.mint,
                          fontSize: 14,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),

            // Stats Row
            _buildAnimatedTile(
              delay: 0.0,
              progress: tilesProgress,
              child: Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: WrappedColors.mint,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                  children: [
                    _buildStatItem(_formatNumber(totalMinutes), 'mins', Colors.white),
                    _buildStatItem(_formatNumber(totalConvs), 'convos', Colors.white),
                    _buildStatItem(_formatNumber(daysActive), 'days', Colors.white),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),

            // Buddies + Obsessions Row
            IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(
                    child: _buildAnimatedTile(
                      delay: 0.1,
                      progress: tilesProgress,
                      child: _buildMiniTile(
                        'BUDDIES',
                        const Color(0xFF6B5B95),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: buddiesRaw.take(4).map((b) {
                            final buddy = b as Map<String, dynamic>;
                            return Padding(
                              padding: const EdgeInsets.only(bottom: 6),
                              child: Row(
                                children: [
                                  Text(buddy['emoji'] ?? '👋', style: const TextStyle(fontSize: 16)),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      buddy['name'] ?? '',
                                      style: const TextStyle(
                                          color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                ],
                              ),
                            );
                          }).toList(),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _buildAnimatedTile(
                      delay: 0.15,
                      progress: tilesProgress,
                      child: _buildMiniTile(
                        'OBSESSIONS',
                        WrappedColors.coral,
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            _buildObsessionRow('📺', widget.capitalizeWords(obsessions?['show'] ?? '-')),
                            _buildObsessionRow('🎬', widget.capitalizeWords(obsessions?['movie'] ?? '-')),
                            _buildObsessionRow('🍕', widget.capitalizeWords(obsessions?['food'] ?? '-')),
                            _buildObsessionRow('⭐', widget.capitalizeWords(obsessions?['celebrity'] ?? '-')),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),

            // Struggle + Win Row
            IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(
                    child: _buildAnimatedTile(
                      delay: 0.2,
                      progress: tilesProgress,
                      child: Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: const Color(0xFF2d4a3e),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Row(
                              children: [
                                Text('😤', style: TextStyle(fontSize: 18)),
                                SizedBox(width: 6),
                                Text('STRUGGLE',
                                    style: TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w800)),
                              ],
                            ),
                            const SizedBox(height: 8),
                            Text(
                              struggle,
                              style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
                              maxLines: 3,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _buildAnimatedTile(
                      delay: 0.25,
                      progress: tilesProgress,
                      child: Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: WrappedColors.mint,
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Row(
                              children: [
                                Text('🏆', style: TextStyle(fontSize: 18)),
                                SizedBox(width: 6),
                                Text('WIN',
                                    style: TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w800)),
                              ],
                            ),
                            const SizedBox(height: 8),
                            Text(
                              biggestWin,
                              style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
                              maxLines: 3,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),

            // Top Phrases (vertical)
            _buildAnimatedTile(
              delay: 0.3,
              progress: tilesProgress,
              child: _buildMiniTile(
                'TOP PHRASES',
                WrappedColors.orange,
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: phrases.take(3).map((p) {
                    final phrase = p is Map ? (p['phrase'] ?? '') : p.toString();
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: Text(
                        '"$phrase"',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          fontStyle: FontStyle.italic,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    );
                  }).toList(),
                ),
              ),
            ),

            const Spacer(),

            // Share button row with omi branding
            Row(
              children: [
                _AnimatedShareButton(
                  progress: tilesProgress,
                  onShare: widget.onShare,
                  buttonColor: WrappedColors.mint,
                ),
                const Spacer(),
                Opacity(
                  opacity: tilesProgress.clamp(0.0, 1.0),
                  child: const Text(
                    'omi',
                    style: TextStyle(
                      color: Colors.white54,
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
          ],
        );
      },
    );
  }

  Widget _buildAnimatedTile({required double delay, required double progress, required Widget child}) {
    final adjustedProgress = ((progress - delay) / (1 - delay)).clamp(0.0, 1.0);
    return Opacity(
      opacity: adjustedProgress,
      child: Transform.translate(
        offset: Offset(0, 15 * (1 - adjustedProgress)),
        child: child,
      ),
    );
  }

  Widget _buildStatItem(String value, String label, Color color) {
    return Column(
      children: [
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 26,
            fontWeight: FontWeight.w900,
          ),
        ),
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.7),
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildMiniTile(String title, Color color, Widget content) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 10),
          content,
        ],
      ),
    );
  }

  Widget _buildObsessionRow(String emoji, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          Text(emoji, style: const TextStyle(fontSize: 14)),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

// That's a Wrap animated end card - premium design (DEPRECATED - kept for reference)
class _ThatsAWrapAnimated extends StatefulWidget {
  final double totalHours;
  final int totalConvs;
  final int totalActions;
  final int completionRate;
  final String archetype;
  final String phrase;
  final int phraseCount;
  final GlobalKey shareCardKey;
  final Widget Function(dynamic, int, int) buildShareableImage;
  final VoidCallback onShare;
  final bool isActive;

  const _ThatsAWrapAnimated({
    required this.totalHours,
    required this.totalConvs,
    required this.totalActions,
    required this.completionRate,
    required this.archetype,
    required this.phrase,
    required this.phraseCount,
    required this.shareCardKey,
    required this.buildShareableImage,
    required this.onShare,
    required this.isActive,
  });

  @override
  State<_ThatsAWrapAnimated> createState() => _ThatsAWrapAnimatedState();
}

class _ThatsAWrapAnimatedState extends State<_ThatsAWrapAnimated> with TickerProviderStateMixin {
  late AnimationController _mainController;
  late Animation<double> _mainAnimation;
  late AnimationController _statsController;
  late Animation<double> _statsAnimation;
  late AnimationController _buttonController;
  late Animation<double> _buttonAnimation;

  bool _hasAnimated = false;

  @override
  void initState() {
    super.initState();

    _mainController = AnimationController(
      duration: const Duration(milliseconds: 1000),
      vsync: this,
    );
    _mainAnimation = CurvedAnimation(
      parent: _mainController,
      curve: Curves.easeOutCubic,
    );

    _statsController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _statsAnimation = CurvedAnimation(
      parent: _statsController,
      curve: Curves.easeOutBack,
    );

    _buttonController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );
    _buttonAnimation = CurvedAnimation(
      parent: _buttonController,
      curve: Curves.elasticOut,
    );

    if (widget.isActive) {
      _startAnimation();
    }
  }

  void _startAnimation() async {
    if (_hasAnimated) return;
    _hasAnimated = true;

    await Future.delayed(const Duration(milliseconds: 300));
    if (!mounted) return;

    _mainController.forward();
    HapticFeedback.heavyImpact();

    await Future.delayed(const Duration(milliseconds: 600));
    if (!mounted) return;
    _statsController.forward();

    await Future.delayed(const Duration(milliseconds: 500));
    if (!mounted) return;
    _buttonController.forward();
  }

  @override
  void didUpdateWidget(_ThatsAWrapAnimated oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !_hasAnimated) {
      _startAnimation();
    }
  }

  @override
  void dispose() {
    _mainController.dispose();
    _statsController.dispose();
    _buttonController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        // Hidden share card
        SizedBox.shrink(
          child: OverflowBox(
            maxWidth: 1080,
            maxHeight: 1920,
            child: Transform.translate(
              offset: const Offset(-10000, -10000),
              child: RepaintBoundary(
                key: widget.shareCardKey,
                child: widget.buildShareableImage(widget.totalHours, widget.totalConvs, widget.totalActions),
              ),
            ),
          ),
        ),
        // Main content
        AnimatedBuilder(
          animation: Listenable.merge([_mainAnimation, _statsAnimation, _buttonAnimation]),
          builder: (context, child) {
            final mainOpacity = _mainAnimation.value.clamp(0.0, 1.0);
            final statsOpacity = _statsAnimation.value.clamp(0.0, 1.0);
            final buttonOpacity = _buttonAnimation.value.clamp(0.0, 1.0);

            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 48),
                // Animated "2025" large text
                Opacity(
                  opacity: mainOpacity,
                  child: Transform.scale(
                    scale: 0.5 + mainOpacity * 0.5,
                    alignment: Alignment.centerLeft,
                    child: ShaderMask(
                      shaderCallback: (bounds) => const LinearGradient(
                        colors: [
                          Color(0xFF667eea),
                          Color(0xFF764ba2),
                          Color(0xFFf953c6),
                        ],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ).createShader(bounds),
                      child: const Text(
                        '2025',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 100,
                          fontWeight: FontWeight.w900,
                          height: 0.9,
                          letterSpacing: -4,
                        ),
                      ),
                    ),
                  ),
                ),
                // "That's a wrap" text
                Opacity(
                  opacity: mainOpacity,
                  child: Transform.translate(
                    offset: Offset(-20 * (1 - mainOpacity), 0),
                    child: const Text(
                      "That's a wrap!",
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 32,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 40),
                // Stats grid with glassmorphism
                Opacity(
                  opacity: statsOpacity,
                  child: Transform.translate(
                    offset: Offset(0, 30 * (1 - statsOpacity)),
                    child: Container(
                      padding: const EdgeInsets.all(24),
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: [
                            Colors.white.withOpacity(0.15),
                            Colors.white.withOpacity(0.05),
                          ],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(
                          color: Colors.white.withOpacity(0.2),
                          width: 1,
                        ),
                      ),
                      child: Column(
                        children: [
                          // Stats row
                          Row(
                            children: [
                              Expanded(child: _buildStatItem('${widget.totalHours.toStringAsFixed(0)}', 'hours', '⏱️')),
                              Container(width: 1, height: 50, color: Colors.white.withOpacity(0.2)),
                              Expanded(child: _buildStatItem('${widget.totalConvs}', 'convos', '💬')),
                              Container(width: 1, height: 50, color: Colors.white.withOpacity(0.2)),
                              Expanded(child: _buildStatItem('${widget.totalActions}', 'actions', '✅')),
                            ],
                          ),
                          const SizedBox(height: 20),
                          Container(height: 1, color: Colors.white.withOpacity(0.15)),
                          const SizedBox(height: 20),
                          // Archetype badge
                          Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                                decoration: BoxDecoration(
                                  gradient: const LinearGradient(
                                    colors: [Color(0xFF667eea), Color(0xFF764ba2)],
                                  ),
                                  borderRadius: BorderRadius.circular(20),
                                ),
                                child: Text(
                                  widget.archetype,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Text(
                                '${widget.completionRate}% done',
                                style: TextStyle(
                                  color: Colors.white.withOpacity(0.7),
                                  fontSize: 16,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          // Signature phrase
                          Row(
                            children: [
                              const Text('🗣️', style: TextStyle(fontSize: 20)),
                              const SizedBox(width: 10),
                              Expanded(
                                child: Text(
                                  '"${widget.phrase}" × ${widget.phraseCount}',
                                  style: TextStyle(
                                    color: Colors.white.withOpacity(0.8),
                                    fontSize: 16,
                                    fontStyle: FontStyle.italic,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const Spacer(),
                // Share button with animation
                Opacity(
                  opacity: buttonOpacity,
                  child: Transform.scale(
                    scale: 0.8 + buttonOpacity * 0.2,
                    child: GestureDetector(
                      onTap: widget.onShare,
                      child: Container(
                        width: double.infinity,
                        padding: const EdgeInsets.symmetric(vertical: 20),
                        decoration: BoxDecoration(
                          gradient: const LinearGradient(
                            colors: [Color(0xFF667eea), Color(0xFF764ba2)],
                            begin: Alignment.centerLeft,
                            end: Alignment.centerRight,
                          ),
                          borderRadius: BorderRadius.circular(40),
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFF667eea).withOpacity(0.4),
                              blurRadius: 20,
                              offset: const Offset(0, 8),
                            ),
                          ],
                        ),
                        child: const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.share_rounded, color: Colors.white, size: 24),
                            SizedBox(width: 12),
                            Text(
                              'Share Your Wrapped',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 20,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 32),
                // Footer
                Opacity(
                  opacity: buttonOpacity * 0.7,
                  child: Center(
                    child: Text(
                      'omi.me/wrapped',
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.5),
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 20),
              ],
            );
          },
        ),
      ],
    );
  }

  Widget _buildStatItem(String value, String label, String emoji) {
    return Column(
      children: [
        Text(emoji, style: const TextStyle(fontSize: 24)),
        const SizedBox(height: 8),
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 28,
            fontWeight: FontWeight.w900,
          ),
        ),
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.6),
            fontSize: 13,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}
