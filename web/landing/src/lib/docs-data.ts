export interface DocEntry {
  slug: string;
  titleKey: string;
  descriptionKey: string;
  contentKey: string;
}

export interface NavGroupEntry {
  titleKey: string;
  items: (DocEntry | { titleKey: string; items: DocEntry[] })[];
}

export const docsNavStructure: NavGroupEntry[] = [
  {
    titleKey: 'buildApps',
    items: [
      { slug: 'introduction', titleKey: 'introTitle', descriptionKey: 'introDescription', contentKey: 'introContent' },
      { slug: 'prompt-based', titleKey: 'promptBasedTitle', descriptionKey: 'promptBasedDescription', contentKey: 'promptBasedContent' },
      { slug: 'integrations', titleKey: 'integrationsTitle', descriptionKey: 'integrationsDescription', contentKey: 'integrationsContent' },
      { slug: 'chat-tools', titleKey: 'chatToolsTitle', descriptionKey: 'chatToolsDescription', contentKey: 'chatToolsContent' },
      { slug: 'audio-streaming', titleKey: 'audioStreamingTitle', descriptionKey: 'audioStreamingDescription', contentKey: 'audioStreamingContent' },
      { slug: 'notifications', titleKey: 'notificationsTitle', descriptionKey: 'notificationsDescription', contentKey: 'notificationsContent' },
      { slug: 'oauth', titleKey: 'oauthTitle', descriptionKey: 'oauthDescription', contentKey: 'oauthContent' },
      { slug: 'submitting', titleKey: 'submittingTitle', descriptionKey: 'submittingDescription', contentKey: 'submittingContent' },
    ],
  },
];

export function getDocBySlug(slug: string): DocEntry | undefined {
  for (const group of docsNavStructure) {
    for (const item of group.items) {
      if ('slug' in item && item.slug === slug) return item;
      if ('items' in item) {
        const found = item.items.find((sub) => sub.slug === slug);
        if (found) return found;
      }
    }
  }
  return undefined;
}

export function getDocSlugs(): string[] {
  const slugs: string[] = [];
  for (const group of docsNavStructure) {
    for (const item of group.items) {
      if ('slug' in item) slugs.push(item.slug);
      if ('items' in item) {
        for (const sub of item.items) slugs.push(sub.slug);
      }
    }
  }
  return slugs;
}
