// Tiny inline icon set (stroke icons, 24px grid) so we ship no icon library.

const PATHS = {
  home: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z',
  chat:
    'M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12zM8.5 11h.01M12 11h.01' +
    'M15.5 11h.01',
  back: 'M15 5l-7 7 7 7',
  chevron: 'M9 5l7 7-7 7',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zm9 3-4.4-4.4',
  send: 'M12 19V5m-6 6 6-6 6 6',
  stop: 'M7 7h10v10H7z',
  close: 'M6 6l12 12M18 6 6 18',
  sparkle:
    'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19' +
    'l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z',
  wallet:
    'M3 7a2 2 0 0 1 2-2h13v4M3 7v11a2 2 0 0 0 2 2h15V9H5a2 2 0 0 1-2-2zm13 7h.01',
  calendar: 'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4',
  house: 'M4 11l8-7 8 7M6 9.5V20h12V9.5M10 20v-5h4v5',
  check: 'M5 12.5l4.5 4.5L19 7',
  alert: 'M12 4 2.5 20h19zM12 10v4m0 3h.01',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm0-10v6m0-9h.01',
  bulb:
    'M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.6.5 1.1 1.3 1.1 2.2h5c0-.9.5-1.7 ' +
    '1.1-2.2A6 6 0 0 0 12 3z',
  trend: 'M3 17l6-6 4 4 8-8m0 0h-5m5 0v5',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm-7 9a7 7 0 0 1 14 0',
  refresh: 'M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7',
}

export default function Icon({ name, size = 20, className, strokeWidth = 2 }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
