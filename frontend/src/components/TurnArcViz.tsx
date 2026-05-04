import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

/** Matches `direction` strings from `features/modules/pelvis_turn_module.py`. */
export type TurnDirection = 'left' | 'right'

/** One turn entry inside `report.runs[].per_turn` (pipeline + worker confidence). */
export interface PerTurnReportEntry {
  turn_id: number
  direction: TurnDirection
  duration_s?: number
  speed_at_apex_kmh: number
  pelvis_turn_angle_deg: number
  /** From pelvis IMU physics; null when speed/gyro too low to estimate. */
  pelvis_turn_radius_m: number | null
  confidence?: number | null
  time_s?: number
  pelvis_peak_rotation_rate?: number
  pelvis_symmetry?: number
  pelvis_max_roll_angle_deg?: number
  pelvis_peak_g_force?: number
  sensor_source?: string
}

/** One skiing run from `transformations/process_session.detect_turns_by_run` (stored in report). */
export interface RunResult {
  run_id: number
  start_s: number
  end_s: number
  duration_s: number
  vertical_drop_m: number
  num_turns: number
  avg_speed_ms?: number
  max_speed_ms?: number
  max_speed_kmh?: number
  mean_accel_mag?: number
  max_accel_mag?: number
  avg_turn_angle_deg?: number
  avg_turn_radius_m?: number | null
  avg_edge_angle_deg?: number
  avg_speed_at_apex_kmh?: number
  avg_symmetry?: number
  turns_left?: number
  turns_right?: number
  per_turn: PerTurnReportEntry[]
}

export type TurnArcVizProps = {
  runs: RunResult[]
  width?: number
  height?: number
}

type Pt = { x: number; y: number }

function cubicBezierPoint(t: number, p0: Pt, p1: Pt, p2: Pt, p3: Pt): Pt {
  const mt = 1 - t
  const a = mt * mt * mt
  const b = 3 * mt * mt * t
  const c = 3 * mt * t * t
  const d = t * t * t
  return {
    x: a * p0.x + b * p1.x + c * p2.x + d * p3.x,
    y: a * p0.y + b * p1.y + c * p2.y + d * p3.y,
  }
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n))
}

function strokeWidthFromSpeed(kmh: number | undefined): number {
  const s = kmh != null && Number.isFinite(kmh) ? kmh : 20
  return 2 + clamp((s - 10) / 40, 0, 1) * 3
}

function opacityFromConfidence(conf: number | null | undefined): number {
  if (conf == null || !Number.isFinite(conf)) {
    return 0.72
  }
  return 0.3 + clamp(conf, 0, 1) * 0.7
}

function lateralFromRadius(
  radiusM: number | null,
  angleDeg: number,
  colInnerW: number,
  dir: 1 | -1,
): number {
  const lateralMax = colInnerW * 0.42
  const rEff = radiusM == null ? 12 : clamp(radiusM, 3, 120)
  const angleBoost = clamp(Math.abs(angleDeg) / 45, 0.6, 1.4)
  const mag = lateralMax * Math.sqrt(12 / rEff) * angleBoost
  return dir * clamp(mag, 4, lateralMax)
}

type ArcGeom = {
  d: string
  apex: Pt
}

function buildArc(
  cx: number,
  y0: number,
  y1: number,
  direction: TurnDirection,
  radiusM: number | null,
  angleDeg: number,
  colInnerW: number,
): ArcGeom {
  const dir: 1 | -1 = direction === 'right' ? 1 : -1
  const lateral = lateralFromRadius(radiusM, angleDeg, colInnerW, dir)
  const h = y1 - y0
  const p0: Pt = { x: cx, y: y0 }
  const p3: Pt = { x: cx, y: y1 }
  const p1: Pt = { x: cx + lateral * 0.62, y: y0 + h * 0.32 }
  const p2: Pt = { x: cx + lateral * 0.62, y: y0 + h * 0.68 }
  const d = `M ${p0.x} ${p0.y} C ${p1.x} ${p1.y} ${p2.x} ${p2.y} ${p3.x} ${p3.y}`
  const apex = cubicBezierPoint(0.5, p0, p1, p2, p3)
  return { d, apex }
}

type TooltipState = {
  clientX: number
  clientY: number
  runLabel: string
  turn: PerTurnReportEntry
}

export default function TurnArcViz({ runs, width = 600, height = 400 }: TurnArcVizProps) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [containerW, setContainerW] = useState<number | null>(null)
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [hoverKey, setHoverKey] = useState<string | null>(null)
  const hoverKeyRef = useRef<string | null>(null)

  useEffect(() => {
    const el = wrapRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width
      if (w && w > 0) setContainerW(w)
    })
    ro.observe(el)
    setContainerW(el.getBoundingClientRect().width)
    return () => ro.disconnect()
  }, [])

  const runsWithTurns = useMemo(
    () => runs.filter((r) => Array.isArray(r.per_turn) && r.per_turn.length > 0),
    [runs],
  )

  const narrow = (containerW ?? width) < 600
  const maxRuns = narrow ? 1 : 4
  const displayRuns = runsWithTurns.slice(0, maxRuns)
  const truncated = runsWithTurns.length > displayRuns.length

  const pad = 14
  const labelH = 20
  const colGap = 10

  const arcsFlat = useMemo(() => {
    const list: {
      key: string
      runIdx: number
      runLabel: string
      turn: PerTurnReportEntry
      geom: ArcGeom
      strokeW: number
      opacity: number
      stroke: string
      globalIdx: number
    }[] = []
    if (displayRuns.length === 0) return list

    const nCol = displayRuns.length
    const innerW = width - pad * 2 - colGap * (nCol - 1)
    const colW = innerW / nCol
    let g = 0

    displayRuns.forEach((run, runIdx) => {
      const cx = pad + runIdx * (colW + colGap) + colW / 2
      const turns = run.per_turn
      const T = turns.length
      const contentTop = pad + labelH
      const contentBot = height - pad
      const contentH = contentBot - contentTop

      turns.forEach((turn, ti) => {
        const y0 = contentTop + (ti / T) * contentH
        const y1 = contentTop + ((ti + 1) / T) * contentH
        const geom = buildArc(
          cx,
          y0,
          y1,
          turn.direction,
          turn.pelvis_turn_radius_m,
          turn.pelvis_turn_angle_deg,
          colW,
        )
        const nullRadius = turn.pelvis_turn_radius_m == null
        const baseOp = nullRadius ? 0.3 : opacityFromConfidence(turn.confidence)
        list.push({
          key: `${run.run_id}-${turn.turn_id}-${ti}`,
          runIdx,
          runLabel: `Run ${runIdx + 1}`,
          turn,
          geom,
          strokeW: strokeWidthFromSpeed(turn.speed_at_apex_kmh),
          opacity: baseOp,
          stroke:
            turn.direction === 'left'
              ? 'var(--color-left-turn)'
              : 'var(--color-right-turn)',
          globalIdx: g++,
        })
      })
    })
    return list
  }, [colGap, displayRuns, height, pad, labelH, width])

  const prefersReducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  const clearHover = useCallback(() => {
    hoverKeyRef.current = null
    setHoverKey(null)
    setTooltip(null)
  }, [])

  if (displayRuns.length === 0) {
    return (
      <div className="turn-arc-viz-empty" ref={wrapRef}>
        <p className="turn-arc-viz-empty-text">No turns to visualize for this session.</p>
      </div>
    )
  }

  return (
    <div className="turn-arc-viz-wrap" ref={wrapRef}>
      <svg
        className="turn-arc-viz-svg"
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height="auto"
        role="img"
        aria-label="Turn arcs by run"
      >
        <rect
          x={0}
          y={0}
          width={width}
          height={height}
          fill="var(--color-surface)"
          rx={8}
        />

        {displayRuns.map((run, runIdx) => {
          const nCol = displayRuns.length
          const innerW = width - pad * 2 - colGap * (nCol - 1)
          const colW = innerW / nCol
          const originX = pad + runIdx * (colW + colGap)
          const cx = originX + colW / 2
          const contentTop = pad + labelH
          const contentBot = height - pad
          return (
            <g key={run.run_id}>
              <text
                x={originX + colW / 2}
                y={pad + 13}
                textAnchor="middle"
                className="turn-arc-run-label"
              >
                Run {runIdx + 1}
              </text>
              <line
                x1={cx}
                y1={contentTop}
                x2={cx}
                y2={contentBot}
                className="turn-arc-fall-line"
              />
            </g>
          )
        })}

        {arcsFlat.map((a) => {
          const isHover = hoverKey === a.key
          return (
            <g
              key={a.key}
              className="turn-arc-hit"
              style={{
                cursor: 'default',
                filter: isHover ? 'brightness(1.3)' : undefined,
              }}
              onMouseEnter={(e) => {
                hoverKeyRef.current = a.key
                setHoverKey(a.key)
                setTooltip({
                  clientX: e.clientX,
                  clientY: e.clientY,
                  runLabel: a.runLabel,
                  turn: a.turn,
                })
              }}
              onMouseMove={(e) => {
                if (hoverKeyRef.current !== a.key) return
                setTooltip({
                  clientX: e.clientX,
                  clientY: e.clientY,
                  runLabel: a.runLabel,
                  turn: a.turn,
                })
              }}
              onMouseLeave={clearHover}
            >
              <path
                className="turn-arc-stroke"
                d={a.geom.d}
                fill="none"
                stroke={a.stroke}
                strokeWidth={a.strokeW}
                strokeLinecap="round"
                strokeLinejoin="round"
                pathLength={1}
                strokeOpacity={a.opacity}
                vectorEffect="non-scaling-stroke"
                style={
                  prefersReducedMotion
                    ? { strokeDasharray: 1, strokeDashoffset: 0 }
                    : {
                        strokeDasharray: 1,
                        strokeDashoffset: 1,
                        animation: `turn-arc-draw 0.4s ease forwards`,
                        animationDelay: `${a.globalIdx * 80}ms`,
                      }
                }
              />
              <circle
                className="turn-arc-apex"
                cx={a.geom.apex.x}
                cy={a.geom.apex.y}
                r={3.2}
                fill={a.stroke}
                fillOpacity={a.opacity}
                pointerEvents="none"
              />
            </g>
          )
        })}
      </svg>

      {truncated && (
        <p className="turn-arc-truncated-note">Showing first {maxRuns} runs</p>
      )}

      {tooltip && (
        <div
          className="turn-arc-tooltip"
          style={{
            position: 'fixed',
            left: Math.min(tooltip.clientX + 14, typeof window !== 'undefined' ? window.innerWidth - 220 : 0),
            top: Math.min(tooltip.clientY + 14, typeof window !== 'undefined' ? window.innerHeight - 160 : 0),
            zIndex: 50,
          }}
          role="tooltip"
        >
          <div className="turn-arc-tooltip-title">
            {tooltip.runLabel} · Turn {tooltip.turn.turn_id} ({tooltip.turn.direction})
          </div>
          <div className="turn-arc-tooltip-row">
            Radius:{' '}
            {tooltip.turn.pelvis_turn_radius_m == null
              ? '—'
              : `${tooltip.turn.pelvis_turn_radius_m} m`}
          </div>
          <div className="turn-arc-tooltip-row">
            Speed: {tooltip.turn.speed_at_apex_kmh} km/h
          </div>
          <div className="turn-arc-tooltip-row">
            Confidence:{' '}
            {tooltip.turn.confidence != null && Number.isFinite(tooltip.turn.confidence)
              ? `${Math.round(tooltip.turn.confidence * 100)}%`
              : '—'}
          </div>
        </div>
      )}
    </div>
  )
}
