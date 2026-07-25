import { useNavigate } from 'react-router-dom'
import { useMemories } from '../hooks/useMemories'
import { useMemoryGraph } from '../hooks/useMemoryGraph'
import { KnowledgeGraphViewer } from '../components/graph/KnowledgeGraphViewer'

// Full-screen interactive brain-map route. Reached from the "expand" affordance
// on the Memories tab's inline Brain Map card. It reuses the EXACT data path that
// card uses — useMemories -> useMemoryGraph — so the full-screen scene shows the
// same graph (onboarding floor + server KG scoped to your current memories),
// centered on the same "you" node. The only difference from the card is that
// BrainGraph is mounted `interactive` here (OrbitControls: pan/zoom/rotate).
export function KnowledgeGraph(): React.JSX.Element {
  const navigate = useNavigate()
  const { memories } = useMemories()
  const { graph, centerNodeId, rebuild, rebuilding } = useMemoryGraph(memories)

  return (
    <KnowledgeGraphViewer
      graph={graph}
      centerNodeId={centerNodeId}
      rebuild={rebuild}
      rebuilding={rebuilding}
      onClose={() => navigate('/memories')}
    />
  )
}
