type SignWritingViewProps = {
  swr: string
}

export function SignWritingView({ swr }: SignWritingViewProps) {
  if (!swr) return null

  // Split SWR string into individual symbols for stylized rendering
  const symbols = swr.split(' ')

  return (
    <div style={{ 
      display: 'flex', 
      flexWrap: 'wrap', 
      gap: '8px', 
      justifyContent: 'center', 
      alignItems: 'center',
      padding: '10px',
      fontFamily: 'monospace',
      fontSize: '14px',
      color: '#00ffcc',
      textShadow: '0 0 8px rgba(0, 255, 204, 0.5)'
    }}>
      {symbols.map((symbol, i) => (
        <span key={i} style={{ 
          padding: '4px 8px', 
          border: '1px solid rgba(0, 255, 204, 0.3)', 
          borderRadius: '4px',
          background: 'rgba(0, 255, 204, 0.1)',
          cursor: 'default'
        }}>
          {symbol}
        </span>
      ))}
    </div>
  )
}
