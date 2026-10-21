'use client'
// The XO app runs only in the browser (microphone, audio and storage do not exist on the server),
// so it is loaded client-side, exactly like the previous single-page app.
import dynamic from 'next/dynamic'

const App = dynamic(() => import('@/shell/App'), { ssr: false })

export default function Page() {
  return <App />
}
