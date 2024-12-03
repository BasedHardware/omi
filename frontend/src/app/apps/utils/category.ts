export const getCategoryDisplay = (category: string): string => {
  const categoryMap: Record<string, string> = {
    'social-and-relationships': 'Social & Relationships',
    'utilities-and-tools': 'Utilities & Tools',
    'productivity-and-organization': 'Productivity',
    'conversation-analysis': 'Conversation Insights',
    'education-and-learning': 'Learning & Education',
    financial: 'Finance',
    other: 'General',
    'emotional-and-mental-support': 'Mental Wellness',
    'safety-and-security': 'Security & Safety',
    'health-and-wellness': 'Health & Fitness',
    'personality-emulation': 'Persona & AI Chat',
    'shopping-and-commerce': 'Shopping',
    'news-and-information': 'News & Info',
    'entertainment-and-fun': 'Entertainment & Games',
  };
  return categoryMap[category] ?? category;
};
