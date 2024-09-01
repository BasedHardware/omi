export interface CommunityPlugin {
  id: string;
  name: string;
  author: string;
  description: string;
  prompt: string;
  image: string;
  memories: boolean;
  chat: boolean;
  _comment: string;
  capabilities: string[];
  memory_prompt: string;
  deleted: boolean;
}
