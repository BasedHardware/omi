/** Cloud conversation delete. The server default is still cascade=false, so a
 *  client that omits the flag leaves the recording's memories in chat and export.
 *  Mobile and macOS already send true. */
export function cloudConversationDeletePath(id: string): string {
  return `/v1/conversations/${id}?cascade=true`
}
