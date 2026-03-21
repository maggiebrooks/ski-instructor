const STAGES = ['processing', 'analyzing', 'generating_plots', 'complete']

const LABELS: Record<string, string> = {
  processing: 'Processing sensor data',
  analyzing: 'Analyzing turns',
  generating_plots: 'Generating plots',
  complete: 'Complete',
}

export default function Progress({ stage }: { stage: string }) {
  const currentIdx = STAGES.indexOf(stage)

  return (
    <div style={{ margin: '24px 0' }}>
      {STAGES.map((s, i) => {
        const done = i < currentIdx
        const active = s === stage && stage !== 'complete'
        return (
          <div
            key={s}
            style={{
              padding: '6px 0',
              opacity: done || active ? 1 : 0.4,
              fontWeight: active ? 700 : 400,
            }}
          >
            {done ? '✓ ' : active ? '▶ ' : '  '}
            {LABELS[s] || s}
          </div>
        )
      })}
    </div>
  )
}
