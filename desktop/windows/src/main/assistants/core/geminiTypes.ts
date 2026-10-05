/** One function call the model made, as decoded from a response part. */
export type ToolCall = {
  name: string
  args: Record<string, unknown>
  /** Opaque thinking signature — echoed back verbatim on the model turn so the
   *  thinking model keeps its chain across the tool round-trip. */
  thoughtSignature?: string
}

/** A single Gemini `tool` (one entry in the request's `tools` array). */
export type GeminiTool = { function_declarations: FunctionDeclaration[] }
type FunctionDeclaration = {
  name: string
  description: string
  parameters: {
    type: 'object'
    properties: Record<string, PropertySpec>
    required: string[]
  }
}
type PropertySpec = { type: string; description: string; enum?: string[] }
