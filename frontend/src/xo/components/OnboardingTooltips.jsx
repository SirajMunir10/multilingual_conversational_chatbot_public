import XoIcon from './XoIcon'

export default function OnboardingTooltips({ isOpen = true, onClose }) {
  if (!isOpen) return null
  return (
    <div className="onboarding-tips-container">
      <div className="tips-header">
        <div className="tips-title">
          <span className="tip-icon"><XoIcon name="bulb" size={16} /></span>
          <h4>XO Feature Tips &amp; Guide</h4>
        </div>
        <button
          className="tips-close-btn"
          onClick={onClose}
          aria-label="Close feature tips"
          title="Dismiss tips"
          data-tooltip="Dismiss tips"
          data-tooltip-pos="left"
        ><XoIcon name="close" size={16} /></button>
      </div>

      <div className="tips-grid">
        <div className="tip-item">
          <span className="tip-icon"><XoIcon name="mic" size={16} /></span>
          <div>
            <strong>Voice Interaction:</strong>
            <p>Tap the microphone to speak naturally in any of the 15 supported languages.</p>
          </div>
        </div>

        <div className="tip-item">
          <span className="tip-icon"><XoIcon name="globe" size={16} /></span>
          <div>
            <strong>Auto Language Detect:</strong>
            <p>Type in any supported language, or switch with the language button — your chat history stays.</p>
          </div>
        </div>

        <div className="tip-item">
          <span className="tip-icon"><XoIcon name="pin" size={16} /></span>
          <div>
            <strong>Property Search:</strong>
            <p>Try: <em>&quot;Show 2 bedroom apartments in Downtown under 3 million&quot;</em>.</p>
          </div>
        </div>

        <div className="tip-item">
          <span className="tip-icon"><XoIcon name="calculator" size={16} /></span>
          <div>
            <strong>Mortgage Estimates:</strong>
            <p>Try: <em>&quot;What can I afford with a 40k monthly salary?&quot;</em></p>
          </div>
        </div>

        <div className="tip-item">
          <span className="tip-icon"><XoIcon name="headset" size={16} /></span>
          <div>
            <strong>Human Agent Handoff:</strong>
            <p>Tap &apos;Advisor&apos; anytime to request a callback from XOTO&apos;s team.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
