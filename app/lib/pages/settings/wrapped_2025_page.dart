import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:omi/backend/http/api/wrapped.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

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

  // Key for capturing share image
  final GlobalKey _shareCardKey = GlobalKey();

  // Total number of cards
  int get _totalCards => 14;

  @override
  void initState() {
    super.initState();
    _loadWrappedStatus();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _pageController.dispose();
    super.dispose();
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
        }
      }
    });
  }

  Future<void> _generateWrapped() async {
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
      setState(() {
        _status = WrappedStatus.error;
        _error = 'Failed to start generation. Please try again.';
      });
    }
  }

  Future<void> _shareWrapped() async {
    try {
      HapticFeedback.mediumImpact();

      await Future.delayed(const Duration(milliseconds: 100));

      final boundary = _shareCardKey.currentContext?.findRenderObject() as RenderRepaintBoundary?;
      if (boundary == null) {
        debugPrint('Share card boundary is null');
        return;
      }

      if (boundary.debugNeedsPaint) {
        debugPrint('Waiting for paint to complete...');
        await Future.delayed(const Duration(milliseconds: 200));
      }

      final image = await boundary.toImage(pixelRatio: 3.0);
      final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
      if (byteData == null) return;

      final bytes = byteData.buffer.asUint8List();

      final directory = await getTemporaryDirectory();
      final file = File('${directory.path}/omi_wrapped_2025.png');
      await file.writeAsBytes(bytes);

      final box = context.findRenderObject() as RenderBox?;
      final sharePositionOrigin = box != null ? Rect.fromLTWH(0, 0, box.size.width, box.size.height / 2) : null;

      await Share.shareXFiles(
        [XFile(file.path)],
        text: 'My 2025, remembered by Omi ✨ omi.me/wrapped',
        sharePositionOrigin: sharePositionOrigin,
      );
    } catch (e) {
      debugPrint('Error sharing wrapped: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Failed to share. Please try again.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: _isLoading ? const Center(child: CircularProgressIndicator(color: Colors.white)) : _buildContent(),
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
              const Text(
                '2025',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 140,
                  fontWeight: FontWeight.w900,
                  height: 0.9,
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
        // Static progress dots on the right (don't scroll)
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
  }) {
    return Container(
      color: backgroundColor,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.only(left: 24, right: 40, top: 16, bottom: 16),
          child: child,
        ),
      ),
    );
  }

  List<Widget> _buildCardsList() {
    return [
      _buildIntroCard(),
      _buildYearInNumbersCard(),
      _buildTopCategoryCard(),
      _buildActionsCard(),
      _buildMemorableDaysCard(),
      _buildFunniestEventCard(),
      _buildEmbarrassingEventCard(),
      _buildFavoritesCard(),
      _buildObsessionsCard(),
      _buildMovieRecsCard(),
      _buildStruggleCard(),
      _buildPersonalWinCard(),
      _buildTopPhrasesCard(),
      _buildShareCard(),
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
      backgroundColor: const Color(0xFF1a237e), // Deep indigo
      child: _CategoryChartAnimated(
        categories: categories,
        isActive: _currentPage == 2,
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
      ),
    );
  }

  Widget _buildFunniestEventCard() {
    final event = _result?['funniest_event'] as Map<String, dynamic>?;
    final title = event?['title'] ?? 'A Hilarious Moment';
    final story = event?['story'] ?? 'You had some funny moments this year!';
    final dateStr = event?['date'] ?? 'January 1';

    final funniestDay = _MemorableDayData(
      emoji: '😂',
      label: 'Funniest',
      title: title,
      description: story,
      dateStr: dateStr,
    );

    return _buildCardBase(
      backgroundColor: WrappedColors.yellow,
      child: _MemorableDaysAnimated(
        days: [funniestDay],
        isActive: _currentPage == 5,
        headerLine1: 'Funniest',
        headerLine2: 'Moment',
        summaryBadgeText: 'Funniest Moment',
        badgeColor: WrappedColors.yellow,
      ),
    );
  }

  Widget _buildEmbarrassingEventCard() {
    final event = _result?['most_embarrassing_event'] as Map<String, dynamic>?;
    final title = event?['title'] ?? 'That Awkward Moment';
    final story = event?['story'] ?? "We've all been there!";
    final dateStr = event?['date'] ?? 'January 1';

    final cringeDay = _MemorableDayData(
      emoji: '😅',
      label: 'Cringe',
      title: title,
      description: story,
      dateStr: dateStr,
    );

    return _buildCardBase(
      backgroundColor: WrappedColors.pink,
      child: _MemorableDaysAnimated(
        days: [cringeDay],
        isActive: _currentPage == 6,
        headerLine1: 'Most',
        headerLine2: 'Cringe',
        summaryBadgeText: 'Most Cringe',
        badgeColor: WrappedColors.pink,
      ),
    );
  }

  Widget _buildFavoritesCard() {
    final favorites = _result?['favorites'] as Map<String, dynamic>?;
    final word = _capitalizeWords(favorites?['word'] ?? 'Amazing');
    final person = _capitalizeWords(favorites?['person'] ?? 'Someone special');
    final food = _capitalizeWords(favorites?['food'] ?? 'Coffee');

    return _buildCardBase(
      backgroundColor: const Color(0xFFFF6B9D),
      child: _TypewriterEndPageAnimated(
        badgeText: 'Favorites',
        badgeColor: const Color(0xFFFF6B9D),
        isActive: _currentPage == 7,
        showProgressRing: false,
        items: [
          _TypewriterItem(label: 'Word', value: word),
          _TypewriterItem(label: 'Person', value: person),
          _TypewriterItem(label: 'Food', value: food),
        ],
      ),
    );
  }

  Widget _buildObsessionsCard() {
    final obsessions = _result?['obsessions'] as Map<String, dynamic>?;
    final show = _capitalizeWords(obsessions?['show'] ?? 'Not mentioned');
    final movie = _capitalizeWords(obsessions?['movie'] ?? 'Not mentioned');
    final book = _capitalizeWords(obsessions?['book'] ?? 'Not mentioned');
    final celebrity = _capitalizeWords(obsessions?['celebrity'] ?? 'Not mentioned');

    return _buildCardBase(
      backgroundColor: WrappedColors.coral,
      child: _TypewriterEndPageAnimated(
        badgeText: "Couldn't Stop Talking About",
        badgeColor: WrappedColors.coral,
        isActive: _currentPage == 8,
        showProgressRing: false,
        items: [
          _TypewriterItem(label: 'Show', value: show, emoji: '📺'),
          _TypewriterItem(label: 'Movie', value: movie, emoji: '🎬'),
          _TypewriterItem(label: 'Book', value: book, emoji: '📚'),
          _TypewriterItem(label: 'Celebrity', value: celebrity, emoji: '⭐'),
        ],
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
        isActive: _currentPage == 9,
        showProgressRing: false,
        items: movies.asMap().entries.map((entry) {
          return _TypewriterItem(
            label: '#${entry.key + 1}',
            value: _capitalizeWords(entry.value),
            emoji: '🎬',
          );
        }).toList(),
      ),
    );
  }

  Widget _buildStruggleCard() {
    final struggle = _result?['struggle'] as Map<String, dynamic>?;
    final title = struggle?['title'] ?? 'The Hard Part';

    return _buildCardBase(
      backgroundColor: const Color(0xFF2d4a3e),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          const Text(
            'Biggest',
            style: TextStyle(
              color: Colors.white,
              fontSize: 28,
              fontWeight: FontWeight.w500,
            ),
          ),
          const Text(
            'Struggle',
            style: TextStyle(
              color: Colors.white,
              fontSize: 56,
              fontWeight: FontWeight.w900,
            ),
          ),
          const Spacer(),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Text(
              '"$title"',
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 28,
                fontWeight: FontWeight.w700,
                fontStyle: FontStyle.italic,
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'But you pushed through 💪',
            style: TextStyle(
              color: Colors.white.withOpacity(0.8),
              fontSize: 18,
            ),
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildPersonalWinCard() {
    final win = _result?['personal_win'] as Map<String, dynamic>?;
    final title = win?['title'] ?? 'Personal Growth';

    return _buildCardBase(
      backgroundColor: WrappedColors.mint,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          const Text(
            '🏆',
            style: TextStyle(fontSize: 72),
          ),
          const SizedBox(height: 16),
          const Text(
            'Biggest',
            style: TextStyle(
              color: Colors.white,
              fontSize: 28,
              fontWeight: FontWeight.w500,
            ),
          ),
          const Text(
            'Win',
            style: TextStyle(
              color: Colors.white,
              fontSize: 64,
              fontWeight: FontWeight.w900,
            ),
          ),
          const Spacer(),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 28,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildTopPhrasesCard() {
    final phrases = _result?['top_phrases'] as List<dynamic>? ?? [];

    return _buildCardBase(
      backgroundColor: WrappedColors.orange,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          const Text(
            'Your Top 5',
            style: TextStyle(
              color: Colors.white,
              fontSize: 28,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Phrases',
            style: TextStyle(
              color: Colors.white,
              fontSize: 64,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 40),
          ...phrases.take(5).map((p) {
            final phrase = p is Map ? (p['phrase'] ?? '') : p.toString();
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 24),
              child: Text(
                '"$phrase"',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                  fontStyle: FontStyle.italic,
                ),
                textAlign: TextAlign.center,
              ),
            );
          }).toList(),
          const Spacer(),
        ],
      ),
    );
  }

  Widget _buildShareCard() {
    final totalHours = _result?['total_time_hours'] ?? 0.0;
    final totalConvs = _result?['total_conversations'] ?? 0;
    final totalActions = _result?['total_action_items'] ?? 0;
    final completionRate = ((_result?['action_items_completion_rate'] ?? 0.0) * 100).toInt();
    final archetype = _result?['decision_style']?['name'] ?? 'Thinker';
    final phrase = _result?['signature_phrase']?['phrase'] ?? 'okay';
    final phraseCount = _result?['signature_phrase']?['count'] ?? 0;

    return _buildCardBase(
      backgroundColor: WrappedColors.blue,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Hidden share card
          SizedBox.shrink(
            child: OverflowBox(
              maxWidth: 1080,
              maxHeight: 1920,
              child: Transform.translate(
                offset: const Offset(-10000, -10000),
                child: RepaintBoundary(
                  key: _shareCardKey,
                  child: _buildShareableImage(totalHours, totalConvs, totalActions),
                ),
              ),
            ),
          ),
          const Spacer(),
          const Text(
            "That's a wrap!",
            style: TextStyle(
              color: Colors.white,
              fontSize: 36,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 24),
          // Summary stats row
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 16),
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.15),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                  children: [
                    _buildSummaryStat('${(totalHours as num).toStringAsFixed(0)}', 'hours'),
                    _buildSummaryStat('$totalConvs', 'convos'),
                    _buildSummaryStat('$totalActions', 'actions'),
                  ],
                ),
                const SizedBox(height: 16),
                const Divider(color: Colors.white24, height: 1),
                const SizedBox(height: 16),
                Text(
                  'You\'re a $archetype',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'You said "$phrase" $phraseCount times',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.8),
                    fontSize: 16,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '$completionRate% tasks completed',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.8),
                    fontSize: 16,
                  ),
                ),
              ],
            ),
          ),
          const Spacer(),
          GestureDetector(
            onTap: _shareWrapped,
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 20),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(40),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.share, color: WrappedColors.blue, size: 24),
                  const SizedBox(width: 12),
                  const Text(
                    'Share to Stories',
                    style: TextStyle(
                      color: WrappedColors.blue,
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 40),
        ],
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

  const _YearInNumbersAnimated({
    required this.totalMinutes,
    required this.totalConvs,
    required this.daysActive,
    required this.percentile,
    required this.isActive,
  });

  @override
  State<_YearInNumbersAnimated> createState() => _YearInNumbersAnimatedState();
}

class _YearInNumbersAnimatedState extends State<_YearInNumbersAnimated> with TickerProviderStateMixin {
  late AnimationController _minutesController;
  late AnimationController _convosController;
  late AnimationController _daysController;
  late AnimationController _badgeController;

  late Animation<double> _minutesAnimation;
  late Animation<double> _convosAnimation;
  late Animation<double> _daysAnimation;
  late Animation<double> _badgeAnimation;

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
      ]),
      builder: (context, child) {
        final animatedMinutes = (_minutesAnimation.value * widget.totalMinutes).toInt();
        final animatedConvos = (_convosAnimation.value * widget.totalConvs).toInt();
        final animatedDays = (_daysAnimation.value * widget.daysActive).toInt();

        // Badge scale for stamp effect
        final badgeScale = _badgeAnimation.value;
        final badgeOpacity = _badgeAnimation.value.clamp(0.0, 1.0);

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
            // Progress circle - bottom left
            SizedBox(
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

  const _CategoryChartAnimated({
    required this.categories,
    required this.isActive,
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

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 40),
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

  const _ActionsAnimated({
    required this.totalTasks,
    required this.completedTasks,
    required this.completionRate,
    required this.isActive,
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
            // Progress circle - bottom left
            SizedBox(
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

  const _MemorableDaysAnimated({
    required this.days,
    required this.isActive,
    this.headerLine1 = 'Your',
    this.headerLine2 = 'Top Days',
    this.summaryBadgeText = 'Your Top Days',
    this.badgeColor = WrappedColors.teal,
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
    // Scroll through months one by one for effect
    while (_displayedMonth != targetMonth && mounted) {
      await Future.delayed(const Duration(milliseconds: 150));
      if (!mounted) return;

      setState(() {
        if (_displayedMonth < targetMonth) {
          _displayedMonth++;
        } else {
          _displayedMonth--;
        }
      });
      HapticFeedback.selectionClick();
    }
  }

  Future<void> _circleDate() async {
    // Animate circle appearing
    for (double scale = 0.0; scale <= 1.0; scale += 0.1) {
      if (!mounted) return;
      await Future.delayed(const Duration(milliseconds: 20));
      setState(() => _circleScale = scale);
    }
    setState(() => _circleScale = 1.0);
    HapticFeedback.mediumImpact();
  }

  Future<void> _showDetails() async {
    // Fade in details
    for (double opacity = 0.0; opacity <= 1.0; opacity += 0.1) {
      if (!mounted) return;
      await Future.delayed(const Duration(milliseconds: 30));
      setState(() => _detailsOpacity = opacity);
    }
    setState(() => _detailsOpacity = 1.0);
  }

  Future<void> _hideDetails() async {
    // Fade out details and circle
    for (double val = 1.0; val >= 0.0; val -= 0.15) {
      if (!mounted) return;
      await Future.delayed(const Duration(milliseconds: 25));
      setState(() {
        _detailsOpacity = val;
        _circleScale = val;
      });
    }
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
                        fontSize: 24,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    Text(
                      widget.headerLine2,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 48,
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
              child: Text(
                widget.summaryBadgeText,
                style: TextStyle(
                  color: widget.badgeColor,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
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
        // Progress indicator
        Opacity(
          opacity: _summaryAnimation.value,
          child: SizedBox(
            width: 32,
            height: 32,
            child: CustomPaint(
              painter: _CircularProgressPainter(
                progress: _summaryAnimation.value,
                strokeWidth: 3,
                backgroundColor: Colors.white.withOpacity(0.3),
                progressColor: Colors.white,
              ),
            ),
          ),
        ),
        const SizedBox(height: 20),
      ],
    );
  }

  Widget _buildSummaryDayItem(_MemorableDayData day, double progress) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Label with emoji
        Row(
          children: [
            Text(
              day.emoji,
              style: const TextStyle(fontSize: 24),
            ),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.2),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                day.label.toUpperCase(),
                style: TextStyle(
                  color: Colors.white.withOpacity(0.9),
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 6),
        // Title as big text
        Text(
          day.title,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 32,
            fontWeight: FontWeight.w700,
            height: 1.3,
          ),
        ),
        const SizedBox(height: 6),
        // Date below
        Text(
          day.dateStr,
          style: TextStyle(
            color: Colors.white.withOpacity(0.7),
            fontSize: 16,
            fontWeight: FontWeight.w500,
          ),
        ),
        // Description if available
        if (day.description.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(
            day.description,
            style: TextStyle(
              color: Colors.white.withOpacity(0.8),
              fontSize: 14,
              fontWeight: FontWeight.w400,
              height: 1.4,
            ),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ],
    );
  }

  Widget _buildCalendar(_MemorableDayData? currentDay) {
    final daysInMonth = _getDaysInMonth(_displayedMonth, 2025);
    final firstDayOfWeek = _getFirstDayOfWeek(_displayedMonth, 2025);

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.15),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          // Month header with navigation arrows
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.chevron_left,
                color: Colors.white.withOpacity(0.5),
                size: 24,
              ),
              const SizedBox(width: 12),
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 200),
                transitionBuilder: (child, animation) {
                  return SlideTransition(
                    position: Tween<Offset>(
                      begin: const Offset(0, 0.5),
                      end: Offset.zero,
                    ).animate(animation),
                    child: FadeTransition(opacity: animation, child: child),
                  );
                },
                child: Text(
                  '${_monthNames[_displayedMonth - 1]} 2025',
                  key: ValueKey(_displayedMonth),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Icon(
                Icons.chevron_right,
                color: Colors.white.withOpacity(0.5),
                size: 24,
              ),
            ],
          ),
          const SizedBox(height: 16),
          // Day headers
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: ['S', 'M', 'T', 'W', 'T', 'F', 'S']
                .map((d) => SizedBox(
                      width: 32,
                      child: Text(
                        d,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.6),
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ))
                .toList(),
          ),
          const SizedBox(height: 8),
          // Calendar grid
          _buildCalendarGrid(daysInMonth, firstDayOfWeek, currentDay),
        ],
      ),
    );
  }

  Widget _buildCalendarGrid(int daysInMonth, int firstDayOfWeek, _MemorableDayData? currentDay) {
    final targetDay = currentDay?.month == _displayedMonth ? currentDay?.day : null;

    List<Widget> rows = [];
    List<Widget> currentRow = [];

    // Add empty cells for days before the 1st
    for (int i = 0; i < firstDayOfWeek; i++) {
      currentRow.add(const SizedBox(width: 32, height: 32));
    }

    // Add day cells
    for (int day = 1; day <= daysInMonth; day++) {
      final isTarget = day == targetDay;

      currentRow.add(
        SizedBox(
          width: 32,
          height: 32,
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Circle highlight for target day
              if (isTarget && _circleScale > 0)
                Transform.scale(
                  scale: _circleScale,
                  child: Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: Colors.white,
                        width: 2.5,
                      ),
                      color: Colors.white.withOpacity(0.2),
                    ),
                  ),
                ),
              Text(
                '$day',
                style: TextStyle(
                  color: isTarget && _circleScale > 0.5 ? Colors.white : Colors.white.withOpacity(0.8),
                  fontSize: 14,
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
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: currentRow,
            ),
          ),
        );
        currentRow = [];
      }
    }

    // Add remaining days in the last row
    if (currentRow.isNotEmpty) {
      while (currentRow.length < 7) {
        currentRow.add(const SizedBox(width: 32, height: 32));
      }
      rows.add(
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: currentRow,
          ),
        ),
      );
    }

    return Column(children: rows);
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

  const _TypewriterEndPageAnimated({
    required this.badgeText,
    required this.badgeColor,
    required this.items,
    required this.isActive,
    this.showProgressRing = true,
  });

  @override
  State<_TypewriterEndPageAnimated> createState() => _TypewriterEndPageAnimatedState();
}

class _TypewriterEndPageAnimatedState extends State<_TypewriterEndPageAnimated> with TickerProviderStateMixin {
  late AnimationController _mainController;
  late Animation<double> _mainAnimation;
  late List<AnimationController> _typewriterControllers;
  late List<Animation<double>> _typewriterAnimations;

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

    // Create typewriter controllers for each item
    _typewriterControllers = List.generate(
      widget.items.length,
      (index) => AnimationController(
        duration: Duration(milliseconds: 50 * widget.items[index].value.length),
        vsync: this,
      ),
    );
    _typewriterAnimations =
        _typewriterControllers.map((c) => CurvedAnimation(parent: c, curve: Curves.linear)).toList();

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

    // Start typewriter for each item with stagger
    for (int i = 0; i < _typewriterControllers.length; i++) {
      await Future.delayed(Duration(milliseconds: 200 + i * 150));
      if (!mounted) return;
      _typewriterControllers[i].forward();
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
    for (final c in _typewriterControllers) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _mainAnimation,
      builder: (context, child) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 40),
            // Title badge
            Opacity(
              opacity: _mainAnimation.value,
              child: Transform.scale(
                scale: 0.5 + _mainAnimation.value * 0.5,
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
            const SizedBox(height: 24),
            // Items list with typewriter effect
            ...widget.items.asMap().entries.map((entry) {
              final index = entry.key;
              final item = entry.value;
              // Stagger the entry animation
              final delayedProgress = ((_mainAnimation.value - index * 0.1) / 0.7).clamp(0.0, 1.0);

              return Opacity(
                opacity: delayedProgress,
                child: Transform.translate(
                  offset: Offset(30 * (1 - delayedProgress), 0),
                  child: Padding(
                    padding: EdgeInsets.only(bottom: index < widget.items.length - 1 ? 28 : 0),
                    child: _buildTypewriterItem(item, index),
                  ),
                ),
              );
            }),
            const Spacer(),
            // Progress indicator (conditionally shown)
            if (widget.showProgressRing)
              Opacity(
                opacity: _mainAnimation.value,
                child: SizedBox(
                  width: 32,
                  height: 32,
                  child: CustomPaint(
                    painter: _CircularProgressPainter(
                      progress: _mainAnimation.value,
                      strokeWidth: 3,
                      backgroundColor: Colors.white.withOpacity(0.3),
                      progressColor: Colors.white,
                    ),
                  ),
                ),
              ),
            const SizedBox(height: 20),
          ],
        );
      },
    );
  }

  Widget _buildTypewriterItem(_TypewriterItem item, int index) {
    return AnimatedBuilder(
      animation: _typewriterAnimations[index],
      builder: (context, child) {
        final progress = _typewriterAnimations[index].value;
        final charCount = (progress * item.value.length).round();
        final displayedText = item.value.substring(0, charCount);

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Label with optional emoji
            Row(
              children: [
                if (item.emoji != null) ...[
                  Text(
                    item.emoji!,
                    style: const TextStyle(fontSize: 24),
                  ),
                  const SizedBox(width: 8),
                ],
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    item.label.toUpperCase(),
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.9),
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            // Value with typewriter effect
            Text(
              displayedText,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 32,
                fontWeight: FontWeight.w700,
                height: 1.3,
              ),
            ),
          ],
        );
      },
    );
  }
}
