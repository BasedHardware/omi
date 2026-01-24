import 'package:flutter/material.dart';
import 'package:omi/utils/l10n_extensions.dart';

// Bold color palette - matching wrapped_2025_page.dart
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

/// Base frame for all 9:16 share templates (1080x1920)
class WrappedShareFrame extends StatelessWidget {
  final Color backgroundColor;
  final Widget child;
  final bool showBranding;

  const WrappedShareFrame({
    super.key,
    required this.backgroundColor,
    required this.child,
    this.showBranding = true,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 1080,
      height: 1920,
      color: backgroundColor,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 80, vertical: 100),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(child: child),
            if (showBranding) ...[
              const SizedBox(height: 40),
              Center(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(30),
                  ),
                  child: const Text(
                    'omi.me/wrapped',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 28,
                      fontWeight: FontWeight.w600,
                      decoration: TextDecoration.none,
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
}

/// Badge widget used across templates
class ShareBadge extends StatelessWidget {
  final String text;
  final Color badgeColor;
  final String? emoji;

  const ShareBadge({
    super.key,
    required this.text,
    required this.badgeColor,
    this.emoji,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(30),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (emoji != null) ...[
            Text(
              emoji!,
              style: const TextStyle(fontSize: 28, decoration: TextDecoration.none),
            ),
            const SizedBox(width: 10),
          ],
          Text(
            text,
            style: TextStyle(
              color: badgeColor,
              fontSize: 28,
              fontWeight: FontWeight.w700,
              decoration: TextDecoration.none,
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================
// YEAR IN NUMBERS TEMPLATE
// ============================================================
class YearInNumbersShareTemplate extends StatelessWidget {
  final int totalMinutes;
  final int totalConvs;
  final int daysActive;
  final double percentile;

  const YearInNumbersShareTemplate({
    super.key,
    required this.totalMinutes,
    required this.totalConvs,
    required this.daysActive,
    required this.percentile,
  });

  String _formatNumber(int num) {
    if (num >= 1000) {
      return '${(num / 1000).toStringAsFixed(1)}k';
    }
    return num.toString();
  }

  @override
  Widget build(BuildContext context) {
    return WrappedShareFrame(
      backgroundColor: WrappedColors.mint,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ShareBadge(
            text: context.l10n.wrappedTopPercentUser(percentile.toString()),
            badgeColor: WrappedColors.mint,
          ),
          const SizedBox(height: 80),
          _buildStat(_formatNumber(totalMinutes), context.l10n.wrappedMinutes),
          const SizedBox(height: 60),
          _buildStat(_formatNumber(totalConvs), context.l10n.wrappedConversations),
          const SizedBox(height: 60),
          _buildStat(_formatNumber(daysActive), context.l10n.wrappedDaysActive),
        ],
      ),
    );
  }

  Widget _buildStat(String value, String label) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 140,
            fontWeight: FontWeight.w900,
            height: 0.9,
            decoration: TextDecoration.none,
          ),
        ),
        Text(
          label,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 48,
            fontWeight: FontWeight.w600,
            decoration: TextDecoration.none,
          ),
        ),
      ],
    );
  }
}

// ============================================================
// TOP CATEGORY TEMPLATE
// ============================================================
class TopCategoryShareTemplate extends StatelessWidget {
  final List<Map<String, dynamic>> categories; // [{name, percentage, color}]

  const TopCategoryShareTemplate({
    super.key,
    required this.categories,
  });

  @override
  Widget build(BuildContext context) {
    return WrappedShareFrame(
      backgroundColor: WrappedColors.mint,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ShareBadge(
            text: context.l10n.wrappedYouTalkedAbout,
            badgeColor: const Color(0xFF2A9D8F),
          ),
          const SizedBox(height: 60),
          // Mini pie chart representation
          SizedBox(
            width: 280,
            height: 280,
            child: CustomPaint(
              painter: _SimplePieChartPainter(categories: categories),
            ),
          ),
          const SizedBox(height: 60),
          // Category list
          ...categories.take(5).map((cat) {
            final isFirst = categories.indexOf(cat) == 0;
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 16),
              child: Row(
                children: [
                  Container(
                    width: isFirst ? 36 : 28,
                    height: isFirst ? 36 : 28,
                    decoration: BoxDecoration(
                      color: cat['color'] as Color,
                      borderRadius: BorderRadius.circular(6),
                    ),
                  ),
                  const SizedBox(width: 20),
                  Expanded(
                    child: Text(
                      '${cat['name']} · ${cat['percentage']}%',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: isFirst ? 44 : 36,
                        fontWeight: isFirst ? FontWeight.w800 : FontWeight.w600,
                        decoration: TextDecoration.none,
                      ),
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

class _SimplePieChartPainter extends CustomPainter {
  final List<Map<String, dynamic>> categories;

  _SimplePieChartPainter({required this.categories});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;

    double startAngle = -90 * (3.14159 / 180);
    final total = categories.fold<int>(0, (sum, c) => sum + (c['percentage'] as int));

    for (final cat in categories) {
      final sweepAngle = (cat['percentage'] as int) / total * 2 * 3.14159;
      final paint = Paint()
        ..color = cat['color'] as Color
        ..style = PaintingStyle.fill;

      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        startAngle,
        sweepAngle,
        true,
        paint,
      );
      startAngle += sweepAngle;
    }

    // Center hole
    canvas.drawCircle(
      center,
      radius * 0.5,
      Paint()..color = WrappedColors.mint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// ============================================================
// ACTIONS TEMPLATE
// ============================================================
class ActionsShareTemplate extends StatelessWidget {
  final int totalTasks;
  final int completedTasks;
  final int completionRate;

  const ActionsShareTemplate({
    super.key,
    required this.totalTasks,
    required this.completedTasks,
    required this.completionRate,
  });

  @override
  Widget build(BuildContext context) {
    return WrappedShareFrame(
      backgroundColor: WrappedColors.indigo,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ShareBadge(
            text: context.l10n.wrappedActionItems,
            badgeColor: WrappedColors.indigo,
            emoji: '✓',
          ),
          const SizedBox(height: 80),
          Text(
            '$totalTasks',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 180,
              fontWeight: FontWeight.w900,
              height: 0.9,
              decoration: TextDecoration.none,
            ),
          ),
          Text(
            context.l10n.wrappedTasksCreated,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 48,
              fontWeight: FontWeight.w600,
              decoration: TextDecoration.none,
            ),
          ),
          const SizedBox(height: 80),
          Text(
            '$completedTasks',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 140,
              fontWeight: FontWeight.w900,
              height: 0.9,
              decoration: TextDecoration.none,
            ),
          ),
          Text(
            context.l10n.wrappedCompleted,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 48,
              fontWeight: FontWeight.w600,
              decoration: TextDecoration.none,
            ),
          ),
          const Spacer(),
          // Completion rate badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
            decoration: BoxDecoration(
              color: const Color(0xFF4CAF50),
              borderRadius: BorderRadius.circular(40),
            ),
            child: Text(
              context.l10n.wrappedCompletionRate(completionRate.toString()),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 36,
                fontWeight: FontWeight.w700,
                decoration: TextDecoration.none,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================
// MEMORABLE DAYS TEMPLATE
// ============================================================
class MemorableDaysShareTemplate extends StatelessWidget {
  final List<Map<String, dynamic>> days; // [{emoji, label, title, description, dateStr}]
  final String headerLine1;
  final String headerLine2;
  final String badgeText;
  final Color badgeColor;

  const MemorableDaysShareTemplate({
    super.key,
    required this.days,
    this.headerLine1 = 'Your',
    this.headerLine2 = 'Top Days',
    this.badgeText = 'Your Top Days',
    this.badgeColor = WrappedColors.teal,
  });

  @override
  Widget build(BuildContext context) {
    return WrappedShareFrame(
      backgroundColor: badgeColor,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ShareBadge(
            text: badgeText,
            badgeColor: badgeColor,
          ),
          const SizedBox(height: 50),
          ...days.take(3).map((day) => _buildDayItem(day)),
        ],
      ),
    );
  }

  Widget _buildDayItem(Map<String, dynamic> day) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                day['emoji'] ?? '📅',
                style: const TextStyle(fontSize: 32, decoration: TextDecoration.none),
              ),
              const SizedBox(width: 12),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Text(
                  day['label'] ?? '',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                    decoration: TextDecoration.none,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Text(
                '· ${day['dateStr'] ?? ''}',
                style: TextStyle(
                  color: Colors.white.withOpacity(0.7),
                  fontSize: 22,
                  fontWeight: FontWeight.w500,
                  decoration: TextDecoration.none,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            day['title'] ?? '',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 36,
              fontWeight: FontWeight.w700,
              decoration: TextDecoration.none,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            day['description'] ?? '',
            style: TextStyle(
              color: Colors.white.withOpacity(0.8),
              fontSize: 24,
              fontWeight: FontWeight.w400,
              decoration: TextDecoration.none,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

// ============================================================
// BEST MOMENTS TEMPLATE (Funniest + Cringe)
// ============================================================
class BestMomentsShareTemplate extends StatelessWidget {
  final List<Map<String, dynamic>> moments; // [{emoji, label, title, description, dateStr}]

  const BestMomentsShareTemplate({
    super.key,
    required this.moments,
  });

  @override
  Widget build(BuildContext context) {
    return MemorableDaysShareTemplate(
      days: moments,
      headerLine1: 'Best',
      headerLine2: 'Moments',
      badgeText: context.l10n.wrappedBestMoments,
      badgeColor: WrappedColors.coral,
    );
  }
}

// ============================================================
// MY BUDDIES TEMPLATE
// ============================================================
class MyBuddiesShareTemplate extends StatelessWidget {
  final List<Map<String, dynamic>> buddies; // [{name, relationship, context, emoji}]

  const MyBuddiesShareTemplate({
    super.key,
    required this.buddies,
  });

  @override
  Widget build(BuildContext context) {
    return WrappedShareFrame(
      backgroundColor: const Color(0xFF6B5B95),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ShareBadge(
            text: context.l10n.wrappedMyBuddies,
            badgeColor: const Color(0xFF6B5B95),
            emoji: '👥',
          ),
          const SizedBox(height: 50),
          ...buddies.take(5).toList().asMap().entries.map((entry) => _buildBuddyItem(entry.key, entry.value)),
        ],
      ),
    );
  }

  Widget _buildBuddyItem(int index, Map<String, dynamic> buddy) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 32),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.2),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Text(
                '${index + 1}',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                  decoration: TextDecoration.none,
                ),
              ),
            ),
          ),
          const SizedBox(width: 16),
          Text(
            buddy['emoji'] ?? '👋',
            style: const TextStyle(fontSize: 44, decoration: TextDecoration.none),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  buddy['name'] ?? '',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 32,
                    fontWeight: FontWeight.w700,
                    decoration: TextDecoration.none,
                  ),
                ),
                Text(
                  buddy['relationship'] ?? '',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.7),
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                    decoration: TextDecoration.none,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  buddy['context'] ?? '',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.6),
                    fontSize: 22,
                    fontStyle: FontStyle.italic,
                    decoration: TextDecoration.none,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================
// OBSESSIONS TEMPLATE
// ============================================================
class ObsessionsShareTemplate extends StatelessWidget {
  final String show;
  final String movie;
  final String book;
  final String celebrity;
  final String food;

  const ObsessionsShareTemplate({
    super.key,
    required this.show,
    required this.movie,
    required this.book,
    required this.celebrity,
    required this.food,
  });

  @override
  Widget build(BuildContext context) {
    return WrappedShareFrame(
      backgroundColor: WrappedColors.coral,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ShareBadge(
            text: context.l10n.wrappedCouldntStopTalkingAbout,
            badgeColor: WrappedColors.coral,
          ),
          const SizedBox(height: 50),
          _buildItem('📺', context.l10n.wrappedShow, show),
          _buildItem('🎬', context.l10n.wrappedMovie, movie),
          _buildItem('📚', context.l10n.wrappedBook, book),
          _buildItem('⭐', context.l10n.wrappedCelebrity, celebrity),
          _buildItem('🍕', context.l10n.wrappedFood, food),
        ],
      ),
    );
  }

  Widget _buildItem(String emoji, String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 36),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                emoji,
                style: const TextStyle(fontSize: 36, decoration: TextDecoration.none),
              ),
              const SizedBox(width: 12),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Text(
                  label,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.9),
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1,
                    decoration: TextDecoration.none,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 40,
              fontWeight: FontWeight.w700,
              decoration: TextDecoration.none,
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================
// MOVIE RECS TEMPLATE
// ============================================================
class MovieRecsShareTemplate extends StatelessWidget {
  final List<String> movies;

  const MovieRecsShareTemplate({
    super.key,
    required this.movies,
  });

  @override
  Widget build(BuildContext context) {
    return WrappedShareFrame(
      backgroundColor: const Color(0xFF1a0a2e),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ShareBadge(
            text: context.l10n.wrappedMovieRecs,
            badgeColor: const Color(0xFF1a0a2e),
            emoji: '🎬',
          ),
          const SizedBox(height: 50),
          ...movies.take(5).toList().asMap().entries.map((entry) => _buildMovieItem(entry.key, entry.value)),
        ],
      ),
    );
  }

  Widget _buildMovieItem(int index, String movie) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 36),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 50,
            height: 50,
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Center(
              child: Text(
                '#${index + 1}',
                style: TextStyle(
                  color: Colors.white.withOpacity(0.9),
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  decoration: TextDecoration.none,
                ),
              ),
            ),
          ),
          const SizedBox(width: 20),
          Expanded(
            child: Text(
              movie,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 36,
                fontWeight: FontWeight.w600,
                decoration: TextDecoration.none,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================
// STRUGGLE TEMPLATE
// ============================================================
class StruggleShareTemplate extends StatelessWidget {
  final String title;

  const StruggleShareTemplate({
    super.key,
    required this.title,
  });

  @override
  Widget build(BuildContext context) {
    return WrappedShareFrame(
      backgroundColor: const Color(0xFF2d4a3e),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '😤',
            style: TextStyle(fontSize: 100, decoration: TextDecoration.none),
          ),
          const SizedBox(height: 40),
          Text(
            context.l10n.wrappedBiggest,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 48,
              fontWeight: FontWeight.w400,
              decoration: TextDecoration.none,
            ),
          ),
          Text(
            context.l10n.wrappedStruggle,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 100,
              fontWeight: FontWeight.w900,
              height: 1.0,
              decoration: TextDecoration.none,
            ),
          ),
          const SizedBox(height: 60),
          Text(
            '"$title"',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 44,
              fontWeight: FontWeight.w600,
              fontStyle: FontStyle.italic,
              height: 1.4,
              decoration: TextDecoration.none,
            ),
          ),
          const Spacer(),
          Text(
            context.l10n.wrappedButYouPushedThrough,
            style: TextStyle(
              color: Colors.white.withOpacity(0.7),
              fontSize: 32,
              fontWeight: FontWeight.w500,
              decoration: TextDecoration.none,
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================
// BIGGEST WIN TEMPLATE
// ============================================================
class BiggestWinShareTemplate extends StatelessWidget {
  final String title;

  const BiggestWinShareTemplate({
    super.key,
    required this.title,
  });

  @override
  Widget build(BuildContext context) {
    return WrappedShareFrame(
      backgroundColor: WrappedColors.mint,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '🏆',
            style: TextStyle(fontSize: 100, decoration: TextDecoration.none),
          ),
          const SizedBox(height: 40),
          Text(
            context.l10n.wrappedBiggest,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 48,
              fontWeight: FontWeight.w400,
              decoration: TextDecoration.none,
            ),
          ),
          Text(
            context.l10n.wrappedWin,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 100,
              fontWeight: FontWeight.w900,
              height: 1.0,
              decoration: TextDecoration.none,
            ),
          ),
          const SizedBox(height: 60),
          Text(
            '"$title"',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 44,
              fontWeight: FontWeight.w600,
              fontStyle: FontStyle.italic,
              height: 1.4,
              decoration: TextDecoration.none,
            ),
          ),
          const Spacer(),
          Text(
            context.l10n.wrappedYouDidIt,
            style: TextStyle(
              color: Colors.white.withOpacity(0.7),
              fontSize: 32,
              fontWeight: FontWeight.w500,
              decoration: TextDecoration.none,
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================
// TOP PHRASES TEMPLATE
// ============================================================
class TopPhrasesShareTemplate extends StatelessWidget {
  final List<String> phrases;

  const TopPhrasesShareTemplate({
    super.key,
    required this.phrases,
  });

  @override
  Widget build(BuildContext context) {
    return WrappedShareFrame(
      backgroundColor: WrappedColors.orange,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ShareBadge(
            text: context.l10n.wrappedTopPhrases,
            badgeColor: WrappedColors.orange,
            emoji: '💬',
          ),
          const SizedBox(height: 50),
          ...phrases.take(5).toList().asMap().entries.map((entry) => _buildPhraseItem(entry.key, entry.value)),
        ],
      ),
    );
  }

  Widget _buildPhraseItem(int index, String phrase) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 32),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 50,
            height: 50,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  Colors.white.withOpacity(0.3),
                  Colors.white.withOpacity(0.1),
                ],
              ),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Text(
                '${index + 1}',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 26,
                  fontWeight: FontWeight.w700,
                  decoration: TextDecoration.none,
                ),
              ),
            ),
          ),
          const SizedBox(width: 20),
          Expanded(
            child: Text(
              '"$phrase"',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 36,
                fontWeight: FontWeight.w600,
                fontStyle: FontStyle.italic,
                height: 1.3,
                decoration: TextDecoration.none,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================
// FINAL COLLAGE SUMMARY TEMPLATE (Dense, max-info)
// ============================================================
class FinalCollageShareTemplate extends StatelessWidget {
  // Year in Numbers
  final int totalMinutes;
  final int totalConvs;
  final int daysActive;
  final double percentile;

  // Categories (top 3)
  final List<Map<String, dynamic>> topCategories;

  // Top Days (top 3)
  final List<Map<String, dynamic>> topDays;

  // Best Moments (funniest + cringe)
  final List<Map<String, dynamic>> bestMoments;

  // My Buddies (top 4)
  final List<Map<String, dynamic>> buddies;

  // Obsessions
  final String show;
  final String movie;
  final String food;
  final String celebrity;

  // Top Phrases (top 3)
  final List<String> topPhrases;

  // Struggle + Win
  final String struggle;
  final String biggestWin;

  const FinalCollageShareTemplate({
    super.key,
    required this.totalMinutes,
    required this.totalConvs,
    required this.daysActive,
    required this.percentile,
    required this.topCategories,
    required this.topDays,
    required this.bestMoments,
    required this.buddies,
    required this.show,
    required this.movie,
    required this.food,
    required this.celebrity,
    required this.topPhrases,
    required this.struggle,
    required this.biggestWin,
  });

  String _formatNumber(int num) {
    if (num >= 1000) {
      return '${(num / 1000).toStringAsFixed(1)}k';
    }
    return num.toString();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 1080,
      height: 1920,
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFF0A1628),
            Color(0xFF1a2744),
            Color(0xFF0A1628),
          ],
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 50, vertical: 70),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Row(
              children: [
                ShaderMask(
                  shaderCallback: (bounds) => const LinearGradient(
                    colors: [Color(0xFF4ECDC4), Color(0xFF44A08D)],
                  ).createShader(bounds),
                  child: const Text(
                    '2025',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 80,
                      fontWeight: FontWeight.w900,
                      decoration: TextDecoration.none,
                    ),
                  ),
                ),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    context.l10n.wrappedTopPercentUser(percentile.toString()),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.w700,
                      decoration: TextDecoration.none,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 30),

            // Stats Row
            _buildStatsRow(context),
            const SizedBox(height: 30),

            // Buddies + Obsessions Row (same height)
            IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(child: _buildBuddiesTile(context)),
                  const SizedBox(width: 20),
                  Expanded(child: _buildObsessionsTile(context)),
                ],
              ),
            ),
            const SizedBox(height: 20),

            // Struggle + Win Row (same height)
            IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(child: _buildStruggleTile(context)),
                  const SizedBox(width: 20),
                  Expanded(child: _buildWinTile(context)),
                ],
              ),
            ),
            const SizedBox(height: 20),

            // Top Phrases (vertical)
            _buildPhrasesTile(context),

            const Spacer(),

            // Branding
            Center(
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(30),
                ),
                child: const Text(
                  'omi.me/wrapped',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.w600,
                    decoration: TextDecoration.none,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatsRow(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: WrappedColors.mint,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _buildStatItem(_formatNumber(totalMinutes), context.l10n.wrappedMins),
          _buildStatItem(_formatNumber(totalConvs), context.l10n.wrappedConvos),
          _buildStatItem(_formatNumber(daysActive), context.l10n.wrappedDays),
        ],
      ),
    );
  }

  Widget _buildStatItem(String value, String label) {
    return Column(
      children: [
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 52,
            fontWeight: FontWeight.w900,
            decoration: TextDecoration.none,
          ),
        ),
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.8),
            fontSize: 20,
            fontWeight: FontWeight.w500,
            decoration: TextDecoration.none,
          ),
        ),
      ],
    );
  }

  Widget _buildTile({required String title, required Color color, required Widget content}) {
    return Container(
      padding: const EdgeInsets.all(24), // More padding
      decoration: BoxDecoration(
        color: color, // Opaque
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: Colors.white, // White text on colored bg
              fontSize: 20, // Bigger
              fontWeight: FontWeight.w800,
              decoration: TextDecoration.none,
            ),
          ),
          const SizedBox(height: 16),
          content,
        ],
      ),
    );
  }

  Widget _buildBuddiesTile(BuildContext context) {
    return _buildTile(
      title: context.l10n.wrappedMyBuddiesLabel,
      color: const Color(0xFF6B5B95),
      content: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: buddies.take(4).toList().asMap().entries.map((entry) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              children: [
                Text(
                  entry.value['emoji'] ?? '👋',
                  style: const TextStyle(fontSize: 24, decoration: TextDecoration.none),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    entry.value['name'] ?? '',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.w600,
                      decoration: TextDecoration.none,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildObsessionsTile(BuildContext context) {
    return _buildTile(
      title: context.l10n.wrappedObsessionsLabel,
      color: WrappedColors.coral,
      content: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildObsessionItem('📺', show),
          _buildObsessionItem('🎬', movie),
          _buildObsessionItem('🍕', food),
          _buildObsessionItem('⭐', celebrity),
        ],
      ),
    );
  }

  Widget _buildObsessionItem(String emoji, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Text(
            emoji,
            style: const TextStyle(fontSize: 22, decoration: TextDecoration.none),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.w600,
                decoration: TextDecoration.none,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStruggleTile(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF2d4a3e),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text('😤', style: TextStyle(fontSize: 28, decoration: TextDecoration.none)),
              const SizedBox(width: 12),
              Text(
                context.l10n.wrappedStruggleLabel,
                style: const TextStyle(
                  color: Colors.white70,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  decoration: TextDecoration.none,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            struggle,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w600,
              decoration: TextDecoration.none,
            ),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }

  Widget _buildWinTile(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: WrappedColors.mint,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text('🏆', style: TextStyle(fontSize: 28, decoration: TextDecoration.none)),
              const SizedBox(width: 12),
              Text(
                context.l10n.wrappedWinLabel,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  decoration: TextDecoration.none,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            biggestWin,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w600,
              decoration: TextDecoration.none,
            ),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }

  Widget _buildPhrasesTile(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: _buildTile(
        title: context.l10n.wrappedTopPhrasesLabel,
        color: WrappedColors.orange,
        content: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: topPhrases.take(3).toList().asMap().entries.map((entry) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(
                '"${entry.value}"',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.w600,
                  fontStyle: FontStyle.italic,
                  decoration: TextDecoration.none,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            );
          }).toList(),
        ),
      ),
    );
  }
}
