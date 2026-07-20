import { auth } from './firebase'
import { streamAgentResponse } from './agentRuntime'

export async function callAgentLLM(prompt: string, conversationId = `helper-${crypto.randomUUID()}`): Promise<string> {
  const user = auth.currentUser
  const token = await user?.getIdToken()
  if (!user || !token) throw new Error('Sign in is required to use the Omi agent.')
  return streamAgentResponse({
    ownerId: user.uid,
    token,
    conversationId,
    prompt,
    onDelta: () => undefined
  })
}
