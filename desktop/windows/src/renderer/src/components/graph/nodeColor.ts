// Maps a knowledge-graph node type to a hex color, following the Omi macOS
// desktop app's scheme (KnowledgeGraphNodeType.nsColor) with one deviation:
// "thing" is pink, not purple — purple is off-brand everywhere (INV-UI-1).
// The fixed user/center node is always white, like the macOS `isFixed` glow.
export function nodeColor(nodeType: string, isFixed: boolean): string {
  if (isFixed) return '#ffffff'
  switch (nodeType) {
    case 'person':
      return '#22d3d3' // cyan
    case 'thing':
      return '#ff375f' // pink (systemPink — de-purpled per INV-UI-1)
    case 'place':
      return '#00ff9e' // mint
    case 'organization':
      return '#ff9f0a' // orange
    case 'concept':
    default:
      return '#0a84ff' // blue (systemBlue)
  }
}
