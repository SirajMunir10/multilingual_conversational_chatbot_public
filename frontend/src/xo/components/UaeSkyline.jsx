// Decorative Dubai skyline (Burj Al Arab, Museum of the Future, Burj Khalifa, Emirates Towers, Dubai Frame)
export default function UaeSkyline() {
  return (
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
  )
}
