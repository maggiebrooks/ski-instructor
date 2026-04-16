/** Canonical pipeline order (new + terminal). */
const ORDERED_STAGES = [
  'queued',
  'parsing_sensor_data',
  'running_pipeline',
  'generating_report',
  'generating_plots',
  'complete',
] as const

/** Map legacy progress_stage values to a canonical step for ordering. */
const LEGACY_STAGE_MAP: Record<string, (typeof ORDERED_STAGES)[number]> = {
  processing: 'parsing_sensor_data',
  analyzing: 'generating_report',
}

const progressMap: Record<string, string> = {
  queued: 'Upload received',
  parsing_sensor_data: 'Reading your ski data',
  running_pipeline: 'Analyzing your turns',
  generating_report: 'Building your insights',
  generating_plots: 'Creating visuals',
  complete: 'Done 🎉',
  processing: 'Reading your ski data',
  analyzing: 'Building your insights',
}

function canonicalStage(stage: string): string {
  return LEGACY_STAGE_MAP[stage] ?? stage
}

function stageIndex(stage: string): number {
  const key = canonicalStage(stage)
  const idx = ORDERED_STAGES.indexOf(key as (typeof ORDERED_STAGES)[number])
  return idx >= 0 ? idx : 0
}

export default function Progress({ stage }: { stage: string }) {
  const currentIdx = stageIndex(stage)

  return (
    <div style={{ margin: '24px 0' }}>
      {ORDERED_STAGES.map((s, i) => {
        const done = i < currentIdx
        const active = canonicalStage(stage) === s && s !== 'complete'
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
            {progressMap[s] || 'Processing…'}
          </div>
        )
      })}
    </div>
  )
}
