import 'package:flutter/material.dart';

class ConversationIconStyle {
  final IconData icon;
  final Color foreground;
  final Color background;

  const ConversationIconStyle({required this.icon, required this.foreground, required this.background});
}

ConversationIconStyle getConversationIconStyle(String category, String emoji, String title) {
  final lc = category.toLowerCase();
  final lt = title.toLowerCase();

  // 1. Try category-based match
  if (lc.contains('meeting') || lc.contains('conference')) {
    return const ConversationIconStyle(
        icon: Icons.calendar_today_outlined, foreground: Color(0xFF60a5fa), background: Color(0xFF1e3a5f));
  } else if (lc.contains('fitness') || lc.contains('exercise') || lc.contains('workout')) {
    return const ConversationIconStyle(
        icon: Icons.fitness_center_outlined, foreground: Color(0xFF34d399), background: Color(0xFF064e3b));
  } else if (lc.contains('health') || lc.contains('medical')) {
    return const ConversationIconStyle(
        icon: Icons.favorite_outline, foreground: Color(0xFF34d399), background: Color(0xFF064e3b));
  } else if (lc.contains('finance') || lc.contains('money') || lc.contains('banking')) {
    return const ConversationIconStyle(
        icon: Icons.attach_money, foreground: Color(0xFFfb923c), background: Color(0xFF431407));
  } else if (lc.contains('shopping') || lc.contains('purchase')) {
    return const ConversationIconStyle(
        icon: Icons.shopping_bag_outlined, foreground: Color(0xFFfb923c), background: Color(0xFF431407));
  } else if (lc.contains('music')) {
    return const ConversationIconStyle(
        icon: Icons.music_note_outlined, foreground: Color(0xFFf472b6), background: Color(0xFF4a044e));
  } else if (lc.contains('sports') || lc.contains('game')) {
    return const ConversationIconStyle(
        icon: Icons.sports_outlined, foreground: Color(0xFFf472b6), background: Color(0xFF4a044e));
  } else if (lc.contains('entertainment') || lc.contains('fun') || lc.contains('movie')) {
    return const ConversationIconStyle(
        icon: Icons.movie_outlined, foreground: Color(0xFFf472b6), background: Color(0xFF4a044e));
  } else if (lc.contains('travel') || lc.contains('trip') || lc.contains('vacation')) {
    return const ConversationIconStyle(
        icon: Icons.flight_outlined, foreground: Color(0xFF22d3ee), background: Color(0xFF164e63));
  } else if (lc.contains('food') || lc.contains('restaurant') || lc.contains('dining')) {
    return const ConversationIconStyle(
        icon: Icons.restaurant_outlined, foreground: Color(0xFFfb923c), background: Color(0xFF431407));
  } else if (lc.contains('creative') || lc.contains('art')) {
    return const ConversationIconStyle(
        icon: Icons.palette_outlined, foreground: Color(0xFFf472b6), background: Color(0xFF4a044e));
  } else if (lc.contains('family')) {
    return const ConversationIconStyle(
        icon: Icons.people_outline, foreground: Color(0xFFa78bfa), background: Color(0xFF2e1065));
  }

  // 2. Title keyword matching — differentiates within broad categories
  final titleMatch = _matchTitleKeywords(lt);
  if (titleMatch != null) return titleMatch;

  // 3. Specific category matches (broad categories checked after title keywords)
  if (lc.contains('work') || lc.contains('business')) {
    return const ConversationIconStyle(
        icon: Icons.business_center_outlined, foreground: Color(0xFF60a5fa), background: Color(0xFF1e3a5f));
  } else if (lc.contains('project')) {
    return const ConversationIconStyle(
        icon: Icons.folder_outlined, foreground: Color(0xFF60a5fa), background: Color(0xFF1e3a5f));
  } else if (lc.contains('personal') || lc.contains('life')) {
    return const ConversationIconStyle(
        icon: Icons.person_outline, foreground: Color(0xFFa78bfa), background: Color(0xFF2e1065));
  } else if (lc.contains('education') || lc.contains('learning') || lc.contains('school')) {
    return const ConversationIconStyle(
        icon: Icons.school_outlined, foreground: Color(0xFF22d3ee), background: Color(0xFF164e63));
  } else if (lc.contains('technology') || lc.contains('tech') || lc.contains('coding')) {
    return const ConversationIconStyle(
        icon: Icons.computer_outlined, foreground: Color(0xFF22d3ee), background: Color(0xFF164e63));
  } else if (lc.contains('home') || lc.contains('house')) {
    return const ConversationIconStyle(
        icon: Icons.home_outlined, foreground: Color(0xFFa78bfa), background: Color(0xFF2e1065));
  } else if (lc.contains('task') || lc.contains('todo')) {
    return const ConversationIconStyle(
        icon: Icons.check_box_outlined, foreground: Color(0xFF60a5fa), background: Color(0xFF1e3a5f));
  } else if (lc.contains('idea') || lc.contains('brainstorm')) {
    return const ConversationIconStyle(
        icon: Icons.lightbulb_outline, foreground: Color(0xFFfbbf24), background: Color(0xFF422006));
  } else if (lc.contains('note')) {
    return const ConversationIconStyle(
        icon: Icons.note_outlined, foreground: Color(0xFFa78bfa), background: Color(0xFF2e1065));
  } else if (lc.contains('event')) {
    return const ConversationIconStyle(
        icon: Icons.event_outlined, foreground: Color(0xFF60a5fa), background: Color(0xFF1e3a5f));
  } else if (lc.contains('social') || lc.contains('friends')) {
    return const ConversationIconStyle(
        icon: Icons.people_outline, foreground: Color(0xFFf472b6), background: Color(0xFF4a044e));
  }

  // 4. Emoji fallback
  final emojiIcon = _emojiToIcon[emoji];
  if (emojiIcon != null) return emojiIcon;

  // 5. Hash-based diversification — visually distinct even for same category
  return _diverseStyles[title.hashCode.abs() % _diverseStyles.length];
}

ConversationIconStyle? _matchTitleKeywords(String title) {
  // Team / collaboration
  if (title.contains('team') || title.contains('standup') || title.contains('sync')) {
    return const ConversationIconStyle(
        icon: Icons.groups_outlined, foreground: Color(0xFF60a5fa), background: Color(0xFF1e3a5f));
  }
  // Planning / roadmap / strategy
  if (title.contains('roadmap') || title.contains('plan') || title.contains('strateg') || title.contains('priorit')) {
    return const ConversationIconStyle(
        icon: Icons.map_outlined, foreground: Color(0xFFfbbf24), background: Color(0xFF422006));
  }
  // Design / UI / UX
  if (title.contains('design') || title.contains('ui') || title.contains('ux') || title.contains('layout')) {
    return const ConversationIconStyle(
        icon: Icons.design_services_outlined, foreground: Color(0xFFf472b6), background: Color(0xFF4a044e));
  }
  // Notification / alert
  if (title.contains('notification') || title.contains('alert') || title.contains('push')) {
    return const ConversationIconStyle(
        icon: Icons.notifications_outlined, foreground: Color(0xFFfb923c), background: Color(0xFF431407));
  }
  // Automation / workflow / pipeline
  if (title.contains('automat') ||
      title.contains('workflow') ||
      title.contains('pipeline') ||
      title.contains('ci/cd')) {
    return const ConversationIconStyle(
        icon: Icons.settings_suggest_outlined, foreground: Color(0xFF34d399), background: Color(0xFF064e3b));
  }
  // Data / database / analytics
  if (title.contains('data') || title.contains('database') || title.contains('analytic') || title.contains('metric')) {
    return const ConversationIconStyle(
        icon: Icons.bar_chart_outlined, foreground: Color(0xFF22d3ee), background: Color(0xFF164e63));
  }
  // AI / ML / model
  if (title.contains(' ai ') ||
      title.contains('machine learn') ||
      title.contains('model') ||
      title.contains('gpt') ||
      title.contains('llm')) {
    return const ConversationIconStyle(
        icon: Icons.psychology_outlined, foreground: Color(0xFFa78bfa), background: Color(0xFF2e1065));
  }
  // Bug / fix / debug
  if (title.contains('bug') || title.contains('fix') || title.contains('debug') || title.contains('issue')) {
    return const ConversationIconStyle(
        icon: Icons.bug_report_outlined, foreground: Color(0xFFf87171), background: Color(0xFF450a0a));
  }
  // API / integration / endpoint
  if (title.contains('api') || title.contains('integrat') || title.contains('endpoint') || title.contains('webhook')) {
    return const ConversationIconStyle(
        icon: Icons.api_outlined, foreground: Color(0xFF34d399), background: Color(0xFF064e3b));
  }
  // Security / auth / permission
  if (title.contains('secur') || title.contains('auth') || title.contains('permiss') || title.contains('password')) {
    return const ConversationIconStyle(
        icon: Icons.shield_outlined, foreground: Color(0xFFfbbf24), background: Color(0xFF422006));
  }
  // Chat / messaging / conversation
  if (title.contains('chat') || title.contains('messag') || title.contains('conversation')) {
    return const ConversationIconStyle(
        icon: Icons.forum_outlined, foreground: Color(0xFF60a5fa), background: Color(0xFF1e3a5f));
  }
  // GPS / location / map
  if (title.contains('gps') || title.contains('location') || title.contains('map') || title.contains('geo')) {
    return const ConversationIconStyle(
        icon: Icons.location_on_outlined, foreground: Color(0xFF34d399), background: Color(0xFF064e3b));
  }
  // Inventory / stock / warehouse
  if (title.contains('inventor') ||
      title.contains('stock') ||
      title.contains('warehouse') ||
      title.contains('supply')) {
    return const ConversationIconStyle(
        icon: Icons.inventory_2_outlined, foreground: Color(0xFFfb923c), background: Color(0xFF431407));
  }
  // Performance / speed / optimize
  if (title.contains('perform') || title.contains('speed') || title.contains('optimi') || title.contains('cache')) {
    return const ConversationIconStyle(
        icon: Icons.speed_outlined, foreground: Color(0xFF22d3ee), background: Color(0xFF164e63));
  }
  // Review / feedback / retrospective
  if (title.contains('review') || title.contains('feedback') || title.contains('retro')) {
    return const ConversationIconStyle(
        icon: Icons.rate_review_outlined, foreground: Color(0xFFa78bfa), background: Color(0xFF2e1065));
  }
  // Launch / release / deploy
  if (title.contains('launch') || title.contains('release') || title.contains('deploy') || title.contains('ship')) {
    return const ConversationIconStyle(
        icon: Icons.rocket_launch_outlined, foreground: Color(0xFFf472b6), background: Color(0xFF4a044e));
  }
  return null;
}

const List<ConversationIconStyle> _diverseStyles = [
  ConversationIconStyle(icon: Icons.chat_bubble_outline, foreground: Color(0xFFa78bfa), background: Color(0xFF2e1065)),
  ConversationIconStyle(icon: Icons.lightbulb_outline, foreground: Color(0xFFfbbf24), background: Color(0xFF422006)),
  ConversationIconStyle(icon: Icons.explore_outlined, foreground: Color(0xFF22d3ee), background: Color(0xFF164e63)),
  ConversationIconStyle(
      icon: Icons.auto_awesome_outlined, foreground: Color(0xFFf472b6), background: Color(0xFF4a044e)),
  ConversationIconStyle(icon: Icons.insights_outlined, foreground: Color(0xFF34d399), background: Color(0xFF064e3b)),
  ConversationIconStyle(icon: Icons.hub_outlined, foreground: Color(0xFF60a5fa), background: Color(0xFF1e3a5f)),
  ConversationIconStyle(icon: Icons.extension_outlined, foreground: Color(0xFFfb923c), background: Color(0xFF431407)),
  ConversationIconStyle(icon: Icons.widgets_outlined, foreground: Color(0xFFa78bfa), background: Color(0xFF2e1065)),
  ConversationIconStyle(icon: Icons.bookmark_outline, foreground: Color(0xFF22d3ee), background: Color(0xFF164e63)),
  ConversationIconStyle(
      icon: Icons.pending_actions_outlined, foreground: Color(0xFFfbbf24), background: Color(0xFF422006)),
];

const Map<String, ConversationIconStyle> _emojiToIcon = {
  '🛠️':
      ConversationIconStyle(icon: Icons.build_outlined, foreground: Color(0xFFfb923c), background: Color(0xFF431407)),
  '💼': ConversationIconStyle(
      icon: Icons.business_center_outlined, foreground: Color(0xFF60a5fa), background: Color(0xFF1e3a5f)),
  '🏠': ConversationIconStyle(icon: Icons.home_outlined, foreground: Color(0xFFa78bfa), background: Color(0xFF2e1065)),
  '📚':
      ConversationIconStyle(icon: Icons.school_outlined, foreground: Color(0xFF22d3ee), background: Color(0xFF164e63)),
  '❤️':
      ConversationIconStyle(icon: Icons.favorite_outline, foreground: Color(0xFF34d399), background: Color(0xFF064e3b)),
  '🎮': ConversationIconStyle(
      icon: Icons.sports_esports_outlined, foreground: Color(0xFFf472b6), background: Color(0xFF4a044e)),
  '✈️':
      ConversationIconStyle(icon: Icons.flight_outlined, foreground: Color(0xFF22d3ee), background: Color(0xFF164e63)),
  '🛒': ConversationIconStyle(
      icon: Icons.shopping_bag_outlined, foreground: Color(0xFFfb923c), background: Color(0xFF431407)),
  '💰': ConversationIconStyle(icon: Icons.attach_money, foreground: Color(0xFFfb923c), background: Color(0xFF431407)),
  '🎵': ConversationIconStyle(
      icon: Icons.music_note_outlined, foreground: Color(0xFFf472b6), background: Color(0xFF4a044e)),
  '🎨':
      ConversationIconStyle(icon: Icons.palette_outlined, foreground: Color(0xFFf472b6), background: Color(0xFF4a044e)),
  '📝': ConversationIconStyle(icon: Icons.note_outlined, foreground: Color(0xFFa78bfa), background: Color(0xFF2e1065)),
  '🍔': ConversationIconStyle(
      icon: Icons.restaurant_outlined, foreground: Color(0xFFfb923c), background: Color(0xFF431407)),
  '🏆': ConversationIconStyle(
      icon: Icons.emoji_events_outlined, foreground: Color(0xFFfbbf24), background: Color(0xFF422006)),
  '📊': ConversationIconStyle(icon: Icons.bar_chart, foreground: Color(0xFF60a5fa), background: Color(0xFF1e3a5f)),
};
