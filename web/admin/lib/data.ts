import { App, AppCategory, AppStatus, AppCapability, DashboardStats, PopularApp } from "./types";

export const mockApps: App[] = [
  {
    id: "1",
    name: "Lie Detector Pro",
    author: "Damien Ietto",
    category: "Conversation Analysis",
    status: "public",
    capabilities: ["chat"],
    installs: 466,
    usage: 24499,
    earnings: 245,
    created: "2023-11-15",
    icon: "/app-icons/lie-detector.png"
  },
  {
    id: "2",
    name: "Mm",
    author: "elmush",
    category: "Education And Learning",
    status: "public",
    capabilities: ["proactive", "integration"],
    installs: 50,
    usage: 0,
    earnings: 0,
    created: "2023-12-01",
    icon: "/app-icons/mm.png"
  },
  {
    id: "3",
    name: "Google Calendar",
    author: "@ashwin.io",
    category: "Productivity And Organization",
    status: "public",
    capabilities: ["integration"],
    installs: 175,
    usage: 28201,
    earnings: 564,
    created: "2023-12-05",
    icon: "/app-icons/google-calendar.png"
  },
  {
    id: "4",
    name: "Google Drive",
    author: "@ashwin.in",
    category: "Productivity And Organization",
    status: "public",
    capabilities: ["integration"],
    installs: 556,
    usage: 44570,
    earnings: 891,
    created: "2023-12-10",
    icon: "/app-icons/google-drive.png"
  },
  {
    id: "5",
    name: "Reflect Notes",
    author: "@ashwin.in",
    category: "Productivity And Organization",
    status: "public",
    capabilities: ["integration"],
    installs: 30,
    usage: 7475,
    earnings: 150,
    created: "2023-12-15",
    icon: "/app-icons/reflect-notes.png"
  },
  {
    id: "6",
    name: "GandalfLLM",
    author: "findrifin",
    category: "Personality Emulation",
    status: "public",
    capabilities: ["chat", "persona"],
    installs: 6,
    usage: 35,
    earnings: 0,
    created: "2024-11-11",
    icon: "/app-icons/gandalf.png"
  },
  {
    id: "7",
    name: "Choice Path",
    author: "Posseled",
    category: "Entertainment And Fun",
    status: "public",
    capabilities: ["chat"],
    installs: 18,
    usage: 3,
    earnings: 0,
    created: "2024-12-11",
    icon: "/app-icons/choice-path.png"
  },
  {
    id: "8",
    name: "Mind Mate",
    author: "Jeddy",
    category: "Emotional And Mental Support",
    status: "public",
    capabilities: ["chat", "persona"],
    installs: 64,
    usage: 6320,
    earnings: 63,
    created: "2024-12-11",
    icon: "/app-icons/mind-mate.png"
  },
  {
    id: "9",
    name: "Civilized Conversations",
    author: "Jeddy",
    category: "Communication Improvement",
    status: "public",
    capabilities: ["chat", "persona"],
    installs: 93,
    usage: 6437,
    earnings: 64,
    created: "2024-12-11",
    icon: "/app-icons/civilized-conversations.png"
  },
  {
    id: "10",
    name: "Question Recall",
    author: "Tony Chang",
    category: "Utilities And Tools",
    status: "public",
    capabilities: ["memory"],
    installs: 28,
    usage: 4778,
    earnings: 48,
    created: "2024-01-14",
    icon: "/app-icons/question-recall.png"
  },
];

export const dashboardStats: DashboardStats = {
  totalApps: 5340,
  approvedApps: 2728,
  inReviewApps: 96,
  paidApps: 29,
  publicApps: 2790,
  privateApps: 2550,
  earnings: 12444,
  usage: 1110100,
  installs: 22537,
  categories: {
    memory: 374,
    chat: 303,
    proactive: 158,
    integration: 228,
    persona: 4743,
  }
};

// Functions to simulate API endpoints
export async function getApps(): Promise<App[]> {
  return mockApps;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  return dashboardStats;
}

export function getStatusColor(status: AppStatus): string {
  switch (status) {
    case 'public':
      return 'bg-green-500';
    case 'private':
      return 'bg-blue-500';
    case 'in-review':
      return 'bg-yellow-500';
    case 'rejected':
      return 'bg-red-500';
    default:
      return 'bg-gray-500';
  }
}

export function getCapabilityIcon(capability: AppCapability): string {
  switch (capability) {
    case 'memory':
      return '🧠';
    case 'chat':
      return '💬';
    case 'proactive':
      return '⚡';
    case 'integration':
      return '🔄';
    case 'persona':
      return '👤';
    default:
      return '📱';
  }
}