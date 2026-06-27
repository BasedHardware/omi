export type CloudConversation = {
  id: string
  // Backend processing state. Only 'completed' conversations are eligible for
  // retention — a 'processing' one's transcript_segments may still be empty/partial.
  status?: string
  transcript_segments?: { text: string }[]
}
