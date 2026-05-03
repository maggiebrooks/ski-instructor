/** Subtle info strip for demo deployments (no cross-session persistence yet). */
export default function DemoModeBanner() {
  return (
    <div
      role="status"
      style={{
        background: '#e8f4fc',
        border: '1px solid #b8d4ea',
        borderRadius: 8,
        padding: '10px 12px',
        marginBottom: 16,
        fontSize: 13,
        lineHeight: 1.45,
        color: '#3d5a70',
      }}
    >
      ℹ️ Demo mode — results are not saved between sessions. Full data persistence
      coming soon.
    </div>
  )
}
