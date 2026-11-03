// Decorative Dubai skyline (Burj Al Arab, Museum of the Future, Burj Khalifa, Emirates Towers, Dubai Frame),
// with a living sky: sparkles, stars and lit windows. All motion is CSS (styles/uae-skyline.css), animating only
// opacity and transform, so it costs almost nothing and stops while the chat is closed.

// Same positions on every render (no layout jumps); a tiny seeded generator spreads them naturally.
function seeded(seed) {
  let s = seed
  return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646 }
}
const rand = seeded(11)
// Stars and sparkles stay in the upper sky, clear of the greeting text and the towers.
// Few animated elements keep the cost near zero: the stars are drawn as gradients on three layers and the windows sit
// in three groups, and each layer or group twinkles on its own rhythm.
const GROUPS = [{ delay: 0, duration: 3.4 }, { delay: 1.3, duration: 4.6 }, { delay: 2.6, duration: 5.8 }]
const STAR_LAYERS = GROUPS.map((timing) => ({
  ...timing,
  image: Array.from({ length: 8 }, () => {
    const radius = (1.6 + rand() * 1.6).toFixed(1)
    return `radial-gradient(circle ${radius}px at ${(rand() * 100).toFixed(1)}% ${(rand() * 34).toFixed(1)}%, #fff 0 35%, rgba(255, 255, 255, 0) 100%)`
  }).join(', ')
}))
const SPARKLES = Array.from({ length: 7 }, () => ({ x: 6 + rand() * 88, y: 4 + rand() * 28, size: 7 + rand() * 6, delay: rand() * 9, duration: 6 + rand() * 4 }))
// Windows on the towers, in the skyline's own coordinates (viewBox 480 x 200), one list per group
const WINDOW_GROUPS = [
  [[270, 170], [276, 104], [305, 166], [380, 130], [408, 176]],
  [[274, 142], [284, 122], [357, 142], [402, 142]],
  [[278, 72], [287, 160], [360, 176], [386, 162]]
]

const timing = (item) => ({ animationDelay: `-${item.delay.toFixed(2)}s`, animationDuration: `${item.duration.toFixed(2)}s` })

// Day (light mode): a softly breathing sun and two drifting clouds. Night (dark mode): stars, sparkles and a rare
// shooting star. Both cover the whole conversation background; CSS shows the set that matches the theme.
export function SkySparkles() {
  return (
    <div className="feed-sky" aria-hidden="true">
      <span className="sky-sun" />
      <span className="sky-cloud" />
      <span className="sky-cloud sky-cloud-far" />
      {STAR_LAYERS.map((layer, i) => <span key={`stars-${i}`} className="sky-stars" style={{ backgroundImage: layer.image, ...timing(layer) }} />)}
      {SPARKLES.map((s, i) => (
        <span key={`sparkle-${i}`} className="sky-sparkle" style={{ left: `${s.x}%`, top: `${s.y}%`, width: s.size, height: s.size, ...timing(s) }} />
      ))}
      <span className="sky-shooting-star" />
    </div>
  )
}

export default function UaeSkyline() {
  return (
    <>
      <svg className="uae-skyline" viewBox="0 0 480 200" preserveAspectRatio="xMidYMax slice" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id="xo-sky-fill" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#7c2cf0" />
            <stop offset="0.6" stopColor="#5c039b" />
            <stop offset="1" stopColor="#03a4f4" />
          </linearGradient>
          <radialGradient id="xo-sky-sun" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0" stopColor="#03a4f4" stopOpacity="0.55" />
            <stop offset="1" stopColor="#03a4f4" stopOpacity="0" />
          </radialGradient>
        </defs>
    
        <circle cx="318" cy="62" r="46" fill="url(#xo-sky-sun)" />
    
        {/* distant towers */}
        <g fill="url(#xo-sky-fill)" opacity="0.45">
          <rect x="18" y="142" width="16" height="58" rx="1" />
          <rect x="38" y="128" width="12" height="72" rx="1" />
          <rect x="112" y="136" width="14" height="64" rx="1" />
          <rect x="198" y="120" width="13" height="80" rx="1" />
          <rect x="214" y="138" width="17" height="62" rx="1" />
          <rect x="236" y="112" width="12" height="88" rx="6" />
          <rect x="326" y="118" width="14" height="82" rx="1" />
          <rect x="344" y="134" width="16" height="66" rx="1" />
          <rect x="418" y="140" width="14" height="60" rx="1" />
        </g>
    
        <g fill="url(#xo-sky-fill)">
          {/* Burj Al Arab: sail with its spine */}
          <path d="M64 200 L64 96 C 84 108 100 150 106 200 Z" />
          <path d="M60 200 L62 84 L65 84 L66 200 Z" />
          <rect x="84" y="128" width="9" height="2.5" rx="1" />
    
          {/* Museum of the Future: torus on a green mound */}
          <path fillRule="evenodd" d="M152 182 a20 27 0 1 0 40 0 a20 27 0 1 0 -40 0 Z M163 180 a9 14 0 1 0 18 0 a9 14 0 1 0 -18 0 Z" />
          <path d="M140 200 Q 172 186 204 200 Z" />
    
          {/* Burj Khalifa: stepped spiral setbacks and spire */}
          <path d="M266 200 L266 152 L269 152 L269 116 L272 116 L272 86 L274.5 86 L274.5 60 L276.5 60 L276.5 38 L278.2 38 L279 4 L279.8 38
                   L281.4 38 L281.4 52 L283.5 52 L283.5 74 L285.8 74 L285.8 104 L288.6 104 L288.6 138 L292 138 L292 200 Z" />
    
          {/* mid-rise cluster */}
          <rect x="300" y="150" width="15" height="50" rx="1" />
          <path d="M352 200 L352 120 Q 359 108 366 120 L366 200 Z" />
    
          {/* Emirates Towers */}
          <path d="M376 200 L376 98 L384 80 L392 98 L392 200 Z" />
          <path d="M398 200 L398 112 L405 98 L412 112 L412 200 Z" />
    
          {/* Dubai Frame */}
          <path fillRule="evenodd" d="M438 200 L438 118 L466 118 L466 200 Z M444 200 L444 126 L460 126 L460 200 Z" />
    
          {/* waterfront */}
          <path d="M0 196 Q 60 192 120 196 T 240 196 T 360 196 T 480 196 L480 200 L0 200 Z" />
        </g>
      </svg>
      <svg className="uae-skyline-lights" viewBox="0 0 480 200" preserveAspectRatio="xMidYMax slice" aria-hidden="true" focusable="false">
        {WINDOW_GROUPS.map((group, i) => (
          <g key={i} className="sky-windows" style={timing(GROUPS[i])}>
            {group.map(([x, y]) => <rect key={`${x}-${y}`} x={x} y={y} width="2.2" height="3" rx="0.4" />)}
          </g>
        ))}
      </svg>
    </>
  )
}
