/** Portfolio / preview strip — intentional framing, not an error state. */
type DemoModeBannerProps = {
  context?: 'upload' | 'session'
}

export default function DemoModeBanner({ context = 'upload' }: DemoModeBannerProps) {
  const message =
    context === 'session'
      ? "Early Preview — This is a demo of Ski Recorder. Head to the home page to try the analysis pipeline with a sample session. iOS app and full persistence coming winter 2026–2027."
      : 'Early Preview — This is a demo of Ski Recorder. Use the sample session below to explore the full analysis pipeline. iOS app and full data persistence coming winter 2026–2027.'

  return (
    <div className="demo-banner demo-banner--preview" role="status">
      <p className="demo-banner__text">{message}</p>
    </div>
  )
}
