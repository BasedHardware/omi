// Maps a knowledge-graph node type to a hex color, matching the Omi macOS
// desktop app (KnowledgeGraphNodeType.nsColor). The fixed user/center node is
// always white, like the macOS `isFixed` glow.
export function nodeColor(nodeType: string, isFixed: boolean): string {
  if (isFixed) return '#ffffff'
  switch (nodeType) {
    case 'person':
      return '#22d3d3' // cyan
    case 'thing':
      return '#a855f7' // purple
    case 'place':
      return '#00ff9e' // mint
    case 'organization':
      return '#ff9f0a' // orange
    case 'concept':
    default:
      return '#0a84ff' // blue (systemBlue)
  }
}
