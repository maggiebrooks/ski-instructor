/** Subtle info strip for demo deployments (no cross-session persistence yet). */
export default function DemoModeBanner() {
  return (
    <div className="demo-banner" role="status">
      <span>
        Demo mode: results are not saved between server restarts. Full persistence
        coming soon.
      </span>
    </div>
  )
}
