// Keyword→emoji lookup for goal cards, ported verbatim from the macOS app
// (`GoalsWidget.goalEmoji`, frozen v0.12.72). The goal's lowercased title is
// checked against each bucket top-to-bottom; the first bucket with ANY substring
// match wins, so ordering is load-bearing (e.g. "growth" resolves to 🚀 in the
// users bucket before the later grow→🌱 bucket). Falls back to 🎯.
//
// Shared primitive: both the Goals page and the Home goals widget import this so
// a goal renders the same glyph everywhere.

export const DEFAULT_GOAL_EMOJI = '🎯'

const GOAL_EMOJI_BUCKETS: ReadonlyArray<readonly [readonly string[], string]> = [
  [['revenue', 'money', 'income', 'profit', 'sales', '$', 'dollar', 'earn'], '💰'],
  [
    [
      'users',
      'customers',
      'clients',
      'subscribers',
      'followers',
      'growth',
      'million',
      '1m',
      '10k',
      '100k',
      'mrr',
      'arr'
    ],
    '🚀'
  ],
  [['startup', 'launch', 'business', 'company'], '🏆'],
  [['invest', 'stock', 'crypto', 'trading'], '📈'],
  [['workout', 'gym', 'exercise', 'lift', 'muscle', 'strength', 'pushup', 'pullup'], '💪'],
  [['run', 'marathon', 'jog', 'cardio', 'steps', 'walk', 'mile', 'km'], '🏃'],
  [['weight', 'lose', 'fat', 'diet', 'calories', 'kg', 'lbs', 'pounds'], '⚖️'],
  [['meditat', 'mindful', 'yoga', 'breath', 'calm', 'peace', 'zen'], '🧘'],
  [['sleep', 'rest', 'hours'], '😴'],
  [['water', 'hydrat', 'drink'], '💧'],
  [['health', 'wellness', 'healthy'], '❤️'],
  [['read', 'book', 'pages', 'chapter'], '📚'],
  [['learn', 'study', 'course', 'class', 'skill', 'certif'], '🎓'],
  [['code', 'program', 'develop', 'app', 'software', 'tech'], '💻'],
  [['language', 'spanish', 'french', 'chinese', 'english', 'german'], '🗣️'],
  [['write', 'blog', 'article', 'post', 'content', 'words'], '✍️'],
  [['video', 'youtube', 'tiktok', 'film'], '🎬'],
  [['music', 'song', 'piano', 'guitar', 'sing'], '🎵'],
  [['art', 'draw', 'paint', 'design', 'create'], '🎨'],
  [['photo', 'picture', 'camera'], '📸'],
  [['task', 'todo', 'complete', 'finish', 'done'], '✅'],
  [['habit', 'daily', 'streak', 'consistent', 'routine'], '🔥'],
  [['time', 'hour', 'minute', 'focus', 'pomodoro', 'productive'], '⏰'],
  [['project', 'ship', 'deliver', 'deadline', 'feature'], '🎯'],
  [['travel', 'trip', 'visit', 'country', 'city', 'vacation'], '✈️'],
  [['home', 'house', 'apartment', 'move', 'buy'], '🏠'],
  [['save', 'saving', 'budget', 'emergency fund'], '🏦'],
  [['friend', 'social', 'network', 'connect', 'meet', 'outreach'], '👥'],
  [['family', 'kids', 'parent'], '👨‍👩‍👧'],
  [['date', 'relationship', 'love'], '💕'],
  [['win', 'first', 'best', 'top', 'champion'], '🏆'],
  [['grow', 'improve', 'better', 'progress'], '🌱'],
  [['star', 'success', 'excellent'], '⭐']
]

export function goalEmoji(title: string): string {
  const t = title.toLowerCase()
  for (const [keywords, emoji] of GOAL_EMOJI_BUCKETS) {
    if (keywords.some((k) => t.includes(k))) return emoji
  }
  return DEFAULT_GOAL_EMOJI
}
