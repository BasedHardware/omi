import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
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
  int get _totalCards => 18;

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
              // Close button
              Align(
                alignment: Alignment.topRight,
                child: IconButton(
                  icon: const Icon(Icons.close, color: Colors.white, size: 28),
                  onPressed: () => Navigator.pop(context),
                ),
              ),
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
              Align(
                alignment: Alignment.topRight,
                child: IconButton(
                  icon: const Icon(Icons.close, color: Colors.white, size: 28),
                  onPressed: () => Navigator.pop(context),
                ),
              ),
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
              Align(
                alignment: Alignment.topRight,
                child: IconButton(
                  icon: const Icon(Icons.close, color: Colors.white, size: 28),
                  onPressed: () => Navigator.pop(context),
                ),
              ),
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
          child: Column(
            children: [
              // Close button
              Align(
                alignment: Alignment.topRight,
                child: IconButton(
                  icon: Icon(
                    Icons.close,
                    color: isDark ? Colors.white : Colors.black87,
                    size: 28,
                  ),
                  onPressed: () => Navigator.pop(context),
                ),
              ),
              // Content
              Expanded(child: child),
            ],
          ),
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
      _buildMostHatedCard(),
      _buildObsessionsCard(),
      _buildMovieRecsCard(),
      _buildStruggleCard(),
      _buildPersonalWinCard(),
      _buildProfessionalWinCard(),
      _buildDecisionStyleCard(),
      _buildSignaturePhraseCard(),
      _buildWhatMatteredMostCard(),
      _buildShareCard(),
    ];
  }

  Widget _buildIntroCard() {
    final totalHours = (_result?['total_time_hours'] ?? 0.0) as num;

    return _buildCardBase(
      backgroundColor: WrappedColors.blue,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          const Text(
            "Let's hit rewind on your",
            style: TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w400,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            '2025',
            style: TextStyle(
              color: Colors.white,
              fontSize: 120,
              fontWeight: FontWeight.w900,
              height: 0.9,
            ),
          ),
          const Spacer(),
          Text(
            'Swipe up to begin',
            style: TextStyle(
              color: Colors.white.withOpacity(0.7),
              fontSize: 16,
            ),
          ),
          const SizedBox(height: 8),
          Icon(
            Icons.keyboard_arrow_up,
            color: Colors.white.withOpacity(0.7),
            size: 32,
          ),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  Widget _buildYearInNumbersCard() {
    final totalHours = (_result?['total_time_hours'] ?? 0.0) as num;
    final totalConvs = _result?['total_conversations'] ?? 0;
    final mostActive = _result?['most_active_month'];

    return _buildCardBase(
      backgroundColor: WrappedColors.mint,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          const Text(
            'YOUR YEAR IN NUMBERS',
            style: TextStyle(
              color: Colors.white70,
              fontSize: 14,
              fontWeight: FontWeight.w700,
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 32),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              Column(
                children: [
                  Text(
                    '${totalHours.toStringAsFixed(0)}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 72,
                      fontWeight: FontWeight.w900,
                      height: 0.9,
                    ),
                  ),
                  const Text(
                    'hours',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
              Container(
                width: 2,
                height: 80,
                color: Colors.white.withOpacity(0.3),
              ),
              Column(
                children: [
                  Text(
                    '$totalConvs',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 72,
                      fontWeight: FontWeight.w900,
                      height: 0.9,
                    ),
                  ),
                  const Text(
                    'convos',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ],
          ),
          const Spacer(),
          if (mostActive != null) ...[
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.2),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                '${mostActive['name']} was your busiest month',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(height: 40),
          ],
        ],
      ),
    );
  }

  Widget _buildTopCategoryCard() {
    final dominant = _result?['dominant_category'] ?? 'other';
    final topCategories = (_result?['top_categories'] as List?)?.take(3).toList() ?? [];

    return _buildCardBase(
      backgroundColor: WrappedColors.lightBlue,
      isDark: false,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          const Text(
            'You talked\nmost about',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.black54,
              fontSize: 24,
              fontWeight: FontWeight.w500,
              height: 1.2,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            _formatCategory(dominant),
            style: const TextStyle(
              color: Colors.black87,
              fontSize: 56,
              fontWeight: FontWeight.w900,
            ),
          ),
          const Spacer(),
          if (topCategories.length > 1) ...[
            Wrap(
              alignment: WrapAlignment.center,
              spacing: 12,
              children: topCategories.skip(1).map<Widget>((cat) {
                return Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  decoration: BoxDecoration(
                    color: Colors.black.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(30),
                  ),
                  child: Text(
                    _formatCategory(cat),
                    style: const TextStyle(
                      color: Colors.black87,
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                );
              }).toList(),
            ),
            const SizedBox(height: 40),
          ],
        ],
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

  Widget _buildActionsCard() {
    final total = _result?['total_action_items'] ?? 0;
    final completed = _result?['completed_action_items'] ?? 0;
    final rate = ((_result?['action_items_completion_rate'] ?? 0.0) * 100).toInt();

    return _buildCardBase(
      backgroundColor: WrappedColors.indigo,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          Text(
            '$total',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 140,
              fontWeight: FontWeight.w900,
              height: 0.9,
            ),
          ),
          const Text(
            'action items',
            style: TextStyle(
              color: Colors.white,
              fontSize: 36,
              fontWeight: FontWeight.w700,
            ),
          ),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 20),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(24),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  '$rate%',
                  style: const TextStyle(
                    color: WrappedColors.indigo,
                    fontSize: 36,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(width: 12),
                const Text(
                  'completed',
                  style: TextStyle(
                    color: WrappedColors.indigo,
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildMemorableDaysCard() {
    final days = _result?['memorable_days'] as Map<String, dynamic>?;
    final funDay = days?['most_fun_day'] as Map<String, dynamic>?;
    final productiveDay = days?['most_productive_day'] as Map<String, dynamic>?;
    final stressfulDay = days?['most_stressful_day'] as Map<String, dynamic>?;

    return _buildCardBase(
      backgroundColor: WrappedColors.teal,
      child: Center(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text(
                  '📅',
                  style: TextStyle(fontSize: 64),
                ),
                const SizedBox(height: 20),
                const Text(
                  'YOUR TOP DAYS',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 2,
                  ),
                ),
                const SizedBox(height: 24),
                // Most Fun Day
                _buildDayItem(
                  emoji: funDay?['emoji'] ?? '🎉',
                  label: 'Most Fun',
                  title: funDay?['title'] ?? 'A Great Day',
                  date: funDay?['date'] ?? '',
                ),
                const SizedBox(height: 20),
                // Most Productive Day
                _buildDayItem(
                  emoji: productiveDay?['emoji'] ?? '💪',
                  label: 'Most Productive',
                  title: productiveDay?['title'] ?? 'Getting Things Done',
                  date: productiveDay?['date'] ?? '',
                ),
                const SizedBox(height: 20),
                // Most Stressful Day
                _buildDayItem(
                  emoji: stressfulDay?['emoji'] ?? '😤',
                  label: 'Most Intense',
                  title: stressfulDay?['title'] ?? 'A Challenging Day',
                  date: stressfulDay?['date'] ?? '',
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildDayItem({
    required String emoji,
    required String label,
    required String title,
    required String date,
  }) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.15),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          Text(emoji, style: const TextStyle(fontSize: 32)),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label.toUpperCase(),
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.7),
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                if (date.isNotEmpty) ...[
                  Text(
                    date,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.6),
                      fontSize: 13,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFunniestEventCard() {
    final event = _result?['funniest_event'] as Map<String, dynamic>?;
    final emoji = event?['emoji'] ?? '😂';
    final title = event?['title'] ?? 'A Hilarious Moment';
    final story = event?['story'] ?? 'You had some funny moments this year!';
    final date = event?['date'] ?? '';

    return _buildCardBase(
      backgroundColor: WrappedColors.yellow,
      child: Center(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  emoji,
                  style: const TextStyle(fontSize: 64),
                ),
                const SizedBox(height: 20),
                const Text(
                  'FUNNIEST MOMENT',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 2,
                  ),
                ),
                const SizedBox(height: 12),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text(
                    title,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 28,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Container(
                  margin: const EdgeInsets.symmetric(horizontal: 16),
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Text(
                    story,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                      height: 1.4,
                    ),
                  ),
                ),
                if (date.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(
                    date,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.7),
                      fontSize: 14,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildEmbarrassingEventCard() {
    final event = _result?['most_embarrassing_event'] as Map<String, dynamic>?;
    final emoji = event?['emoji'] ?? '😅';
    final title = event?['title'] ?? 'That Awkward Moment';
    final story = event?['story'] ?? "We've all been there - you handled it like a champ!";
    final date = event?['date'] ?? '';

    return _buildCardBase(
      backgroundColor: WrappedColors.pink,
      child: Center(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  emoji,
                  style: const TextStyle(fontSize: 64),
                ),
                const SizedBox(height: 20),
                const Text(
                  'MOST CRINGE MOMENT',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 2,
                  ),
                ),
                const SizedBox(height: 12),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text(
                    title,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 28,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Container(
                  margin: const EdgeInsets.symmetric(horizontal: 16),
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Text(
                    story,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                      height: 1.4,
                    ),
                  ),
                ),
                if (date.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(
                    date,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.7),
                      fontSize: 14,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildDecisionStyleCard() {
    final style = _result?['decision_style'];
    final name = style?['name'] ?? 'Thinker';
    final description = style?['description'] ?? 'You process thoughtfully.';

    return _buildCardBase(
      backgroundColor: WrappedColors.lightBlue,
      isDark: false,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          // Abstract geometric badge
          Container(
            width: 200,
            height: 200,
            decoration: BoxDecoration(
              color: WrappedColors.blue,
              borderRadius: BorderRadius.circular(40),
            ),
            child: Stack(
              alignment: Alignment.center,
              children: [
                Container(
                  width: 140,
                  height: 140,
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.3),
                    shape: BoxShape.circle,
                  ),
                ),
                Container(
                  width: 80,
                  height: 80,
                  decoration: BoxDecoration(
                    color: WrappedColors.coral,
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
                Container(
                  width: 40,
                  height: 40,
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 32),
          Text(
            name,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.black87,
              fontSize: 40,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Text(
              description,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.black54,
                fontSize: 20,
                fontWeight: FontWeight.w500,
                height: 1.4,
              ),
            ),
          ),
          const Spacer(),
        ],
      ),
    );
  }

  Widget _buildSignaturePhraseCard() {
    final phrase = _result?['signature_phrase'];
    final phraseText = phrase?['phrase'] ?? 'right';
    final count = phrase?['count'] ?? 0;

    return _buildCardBase(
      backgroundColor: WrappedColors.yellow,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          const Text(
            'You said',
            style: TextStyle(
              color: Colors.white,
              fontSize: 24,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            '"$phraseText"',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 52,
              fontWeight: FontWeight.w900,
              fontStyle: FontStyle.italic,
            ),
          ),
          const SizedBox(height: 24),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.3),
              borderRadius: BorderRadius.circular(30),
            ),
            child: Text(
              '$count times',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 24,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          const Spacer(),
        ],
      ),
    );
  }

  Widget _buildFavoritesCard() {
    final favorites = _result?['favorites'] as Map<String, dynamic>?;
    final word = favorites?['word'] ?? 'Amazing';
    final person = favorites?['person'] ?? 'Someone special';
    final food = favorites?['food'] ?? 'Coffee';

    return _buildCardBase(
      backgroundColor: const Color(0xFFFF6B9D),
      child: Center(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text(
                  'favorites',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 48,
                    fontWeight: FontWeight.w900,
                    fontStyle: FontStyle.italic,
                  ),
                ),
                const SizedBox(height: 40),
                _buildFavItem('WORD', word),
                const SizedBox(height: 28),
                _buildFavItem('PERSON', person),
                const SizedBox(height: 28),
                _buildFavItem('FOOD', food),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFavItem(String label, String value) {
    return Column(
      children: [
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.6),
            fontSize: 12,
            fontWeight: FontWeight.w700,
            letterSpacing: 3,
          ),
        ),
        const SizedBox(height: 6),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Text(
            value,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 32,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildMostHatedCard() {
    final hated = _result?['most_hated'] as Map<String, dynamic>?;
    final word = hated?['word'] ?? 'Meetings';
    final person = hated?['person'] ?? 'That one person';
    final food = hated?['food'] ?? 'Cold coffee';

    return _buildCardBase(
      backgroundColor: const Color(0xFF1a1a1a),
      child: Center(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text(
                  'most hated',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 48,
                    fontWeight: FontWeight.w900,
                    fontStyle: FontStyle.italic,
                  ),
                ),
                const SizedBox(height: 40),
                _buildHatedItem('WORD', word),
                const SizedBox(height: 28),
                _buildHatedItem('PERSON', person),
                const SizedBox(height: 28),
                _buildHatedItem('FOOD', food),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHatedItem(String label, String value) {
    return Column(
      children: [
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.5),
            fontSize: 12,
            fontWeight: FontWeight.w700,
            letterSpacing: 3,
          ),
        ),
        const SizedBox(height: 6),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Text(
            value,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 32,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildObsessionsCard() {
    final obsessions = _result?['obsessions'] as Map<String, dynamic>?;
    final show = obsessions?['show'] ?? 'Not mentioned';
    final movie = obsessions?['movie'] ?? 'Not mentioned';
    final book = obsessions?['book'] ?? 'Not mentioned';
    final celebrity = obsessions?['celebrity'] ?? 'Not mentioned';

    return _buildCardBase(
      backgroundColor: WrappedColors.orange,
      child: Center(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  "couldn't stop\ntalking about",
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.9),
                    fontSize: 28,
                    fontWeight: FontWeight.w900,
                    fontStyle: FontStyle.italic,
                    height: 1.1,
                  ),
                ),
                const SizedBox(height: 32),
                _buildObsessionItem('SHOW', show),
                const SizedBox(height: 20),
                _buildObsessionItem('MOVIE', movie),
                const SizedBox(height: 20),
                _buildObsessionItem('BOOK', book),
                const SizedBox(height: 20),
                _buildObsessionItem('CELEBRITY', celebrity),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildObsessionItem(String label, String value) {
    return Column(
      children: [
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.6),
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 2,
          ),
        ),
        const SizedBox(height: 4),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: Text(
            value,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 24,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildMovieRecsCard() {
    final movies = (_result?['movie_recommendations'] as List?)?.cast<String>() ?? [];

    return _buildCardBase(
      backgroundColor: const Color(0xFF1a0a2e),
      child: Center(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 20),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text(
                  '🎬',
                  style: TextStyle(fontSize: 48),
                ),
                const SizedBox(height: 12),
                const Text(
                  'your movie recs\nto friends',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.w900,
                    fontStyle: FontStyle.italic,
                    height: 1.1,
                  ),
                ),
                const SizedBox(height: 28),
                ...movies.asMap().entries.map((entry) {
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 24),
                    child: Row(
                      children: [
                        Text(
                          '${entry.key + 1}.',
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.5),
                            fontSize: 20,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            entry.value,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 20,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ],
                    ),
                  );
                }),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStruggleCard() {
    final struggle = _result?['struggle'] as Map<String, dynamic>?;
    final title = struggle?['title'] ?? 'The Hard Part';
    final description = struggle?['description'] ?? 'You pushed through challenges this year.';

    return _buildCardBase(
      backgroundColor: const Color(0xFF2d4a3e),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          const Text(
            '💪',
            style: TextStyle(fontSize: 56),
          ),
          const SizedBox(height: 16),
          const Text(
            'BIGGEST STRUGGLE',
            style: TextStyle(
              color: Colors.white70,
              fontSize: 14,
              fontWeight: FontWeight.w700,
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 36,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Text(
              description,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white.withOpacity(0.8),
                fontSize: 18,
                height: 1.4,
              ),
            ),
          ),
          const Spacer(),
        ],
      ),
    );
  }

  Widget _buildPersonalWinCard() {
    final win = _result?['personal_win'] as Map<String, dynamic>?;
    final title = win?['title'] ?? 'Personal Growth';
    final description = win?['description'] ?? 'You achieved something meaningful.';

    return _buildCardBase(
      backgroundColor: WrappedColors.mint,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          const Text(
            '🏆',
            style: TextStyle(fontSize: 56),
          ),
          const SizedBox(height: 16),
          const Text(
            'BIGGEST PERSONAL WIN',
            style: TextStyle(
              color: Colors.white70,
              fontSize: 14,
              fontWeight: FontWeight.w700,
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 36,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Text(
              description,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white.withOpacity(0.8),
                fontSize: 18,
                height: 1.4,
              ),
            ),
          ),
          const Spacer(),
        ],
      ),
    );
  }

  Widget _buildProfessionalWinCard() {
    final win = _result?['professional_win'] as Map<String, dynamic>?;
    final title = win?['title'] ?? 'Career Growth';
    final description = win?['description'] ?? 'You made progress in your professional life.';

    return _buildCardBase(
      backgroundColor: WrappedColors.blue,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          const Text(
            '💼',
            style: TextStyle(fontSize: 56),
          ),
          const SizedBox(height: 16),
          const Text(
            'BIGGEST PROFESSIONAL WIN',
            style: TextStyle(
              color: Colors.white70,
              fontSize: 14,
              fontWeight: FontWeight.w700,
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 36,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
          const SizedBox(height: 16),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Text(
              description,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white.withOpacity(0.8),
                fontSize: 18,
                height: 1.4,
              ),
            ),
          ),
          const Spacer(),
        ],
      ),
    );
  }

  Widget _buildWhatMatteredMostCard() {
    final data = _result?['what_mattered_most'] as Map<String, dynamic>?;
    final word = data?['word'] ?? 'Growth';
    final reason = data?['reason'] ?? 'This theme appeared throughout your year.';

    return _buildCardBase(
      backgroundColor: WrappedColors.purple,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Spacer(),
          const Text(
            '💜',
            style: TextStyle(fontSize: 64),
          ),
          const SizedBox(height: 24),
          const Text(
            'WHAT MATTERED MOST',
            style: TextStyle(
              color: Colors.white70,
              fontSize: 14,
              fontWeight: FontWeight.w700,
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            word,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 72,
              fontWeight: FontWeight.w900,
            ),
          ),
          const Spacer(),
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 16),
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.15),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(
              reason,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w500,
                height: 1.4,
              ),
            ),
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildShareCard() {
    final totalHours = _result?['total_time_hours'] ?? 0.0;
    final totalConvs = _result?['total_conversations'] ?? 0;
    final totalActions = _result?['total_action_items'] ?? 0;

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
              fontSize: 40,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'Share your 2025 journey',
            style: TextStyle(
              color: Colors.white.withOpacity(0.8),
              fontSize: 20,
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
