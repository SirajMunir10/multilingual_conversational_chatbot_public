// Root layout: same document head as the Vue index.html (title, icon, phone viewport, fonts).
// Stylesheets load in the order Vue injected them: global styles first, then each component's styles.
import '@/styles/main.css'
import '@/shell/styles/header-nav.css'
import '@/xo/styles/xo-icon.css'
import '@/xo/styles/mortgage-card.css'
import '@/xo/styles/handoff-card.css'
import '@/xo/styles/message-item.css'
import '@/xo/styles/onboarding-tooltips.css'
import '@/xo/styles/voice-orb.css'
import '@/xo/styles/uae-skyline.css'
import '@/xo/styles/chat-widget.css'
import '@/shell/styles/widget-view.css'
import '@/shell/styles/admin-view.css'
import '@/shell/styles/app.css'

export const metadata = {
  title: 'XO — XOTO Assistant',
  icons: { icon: { url: '/xo-mascot.png', type: 'image/png' } },
  // Written out by name: Next's appleWebApp.capable emits only the non-Apple tag, and iOS needs the Apple one.
  other: {
    'mobile-web-app-capable': 'yes',
    'apple-mobile-web-app-capable': 'yes',
    'apple-mobile-web-app-status-bar-style': 'black-translucent'
  }
}

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  interactiveWidget: 'resizes-content'
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        {/* Google Fonts: Outfit for headings, Inter for UI, Cairo for Arabic */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
      </head>
      <body>
        <div id="app">{children}</div>
      </body>
    </html>
  )
}
