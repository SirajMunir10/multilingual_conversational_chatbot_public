// Line icons (24×24, 2px stroke) used across the widget instead of emoji, so they render the same on every phone.
const ICONS = {
  globe: ['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z', 'M3 12h18', 'M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3Z'],
  headset: ['M3 11h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5Zm0 0a9 9 0 1 1 18 0m0 0v5a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3Z', 'M21 16v2a4 4 0 0 1-4 4h-5'],
  moon: ['M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z'],
  sun: ['M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z', 'M12 2v2', 'M12 20v2', 'M4.9 4.9l1.4 1.4', 'M17.7 17.7l1.4 1.4', 'M2 12h2', 'M20 12h2', 'M6.3 17.7l-1.4 1.4', 'M19.1 4.9l-1.4 1.4'],
  bulb: ['M9 18h6', 'M10 21h4', 'M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.2h5c0-.9.4-1.7 1.1-2.2A6 6 0 0 0 12 3Z'],
  trash: ['M3 6h18', 'M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6', 'M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2', 'M10 11v6', 'M14 11v6'],
  expand: ['M15 3h6v6', 'M9 21H3v-6', 'M21 3l-7 7', 'M3 21l7-7'],
  shrink: ['M4 14h6v6', 'M20 10h-6V4', 'M14 10l7-7', 'M3 21l7-7'],
  close: ['M18 6 6 18', 'M6 6l12 12'],
  mic: ['M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z', 'M19 11a7 7 0 0 1-14 0', 'M12 18v3'],
  send: ['M12 19V5', 'M5 12l7-7 7 7'],
  check: ['M5 12.5l4.5 4.5L19 7.5'],
  search: ['M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z', 'M20 20l-4-4'],
  pause: ['M9 6v12', 'M15 6v12'],
  arrowDown: ['M12 5v14', 'M5 12l7 7 7-7'],
  pin: ['M12 21s-7-5.5-7-11a7 7 0 0 1 14 0c0 5.5-7 11-7 11Z', 'M12 7.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5Z'],
  heart: ['M12 20s-7.5-4.6-7.5-10A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 7.5 3c0 5.4-7.5 10-7.5 10Z'],
  chevronDown: ['M6 9l6 6 6-6'],
  calculator: ['M6 3h12a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z', 'M8 7h8', 'M8 12h.01', 'M12 12h.01', 'M16 12h.01', 'M8 16h.01', 'M12 16h.01', 'M16 16h.01'],
  info: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z', 'M12 11v5', 'M12 8h.01'],
  bed: ['M3 18V7', 'M3 14h18v4', 'M21 14v-2a3 3 0 0 0-3-3h-7v5', 'M7 11.5a1.5 1.5 0 1 0 0-.01'],
  bath: ['M4 12h16v3a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4v-3Z', 'M6 12V5a2 2 0 0 1 4 0', 'M7 19l-1 2', 'M17 19l1 2'],
  area: ['M4 4h16v16H4z', 'M4 9h5V4', 'M20 15h-5v5'],
  edit: ['M4 20h4l10.5-10.5a2.1 2.1 0 0 0-4-4L4 16v4Z', 'M13.5 6.5l4 4'],
  chevronUp: ['M6 15l6-6 6 6'],
  external: ['M14 4h6v6', 'M20 4l-9 9', 'M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5'],
  thumbUp: ['M7 10v11', 'M15 5.9 14 10h5.8a2 2 0 0 1 2 2.3l-1.4 7a2 2 0 0 1-2 1.7H7V10l4-8a3 3 0 0 1 3 3.9Z', 'M7 10H4a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h3'],
  thumbDown: ['M17 14V3', 'M9 18.1 10 14H4.2a2 2 0 0 1-2-2.3l1.4-7A2 2 0 0 1 5.6 3H17v11l-4 8a3 3 0 0 1-3-3.9Z', 'M17 14h3a1 1 0 0 0 1-1V4a1 1 0 0 0-1-1h-3']
}


export default function XoIcon({ name, size = 18, stroke = 2, className }) {
  const paths = ICONS[name] || []
  return (
    <svg className={className ? `xo-icon ${className}` : 'xo-icon'} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {paths.map((d, i) => <path key={i} d={d} />)}
    </svg>
  )
}
