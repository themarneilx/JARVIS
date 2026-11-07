export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    core: (
      <>
        <circle cx="12" cy="12" r="3" />
        <circle cx="12" cy="12" r="8" />
        <path d="M12 1v3m0 16v3M1 12h3m16 0h3" />
      </>
    ),
    system: (
      <>
        <path d="M4 4h16v12H4zM8 20h8m-4-4v4" />
        <path d="m7 10 2-2 3 5 3-4 2 1" />
      </>
    ),
    memory: (
      <>
        <path d="M5 3h14v18H5zM9 7h6m-6 5h6m-6 5h4" />
      </>
    ),
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="m9 3 6 0 1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z" />
      </>
    ),
    shortcuts: (
      <>
        <path d="M4 4h6v6H4zM14 14h6v6h-6zM14 7h4v4M10 17H6v-4" />
        <path d="m15 4 3 3-3 3M9 14l-3 3 3 3" />
      </>
    ),
    mic: (
      <>
        <rect x="9" y="2" width="6" height="13" rx="3" />
        <path d="M5 10v2a7 7 0 0 0 14 0v-2m-7 9v3m-4 0h8" />
      </>
    ),
    send: (
      <>
        <path d="m3 3 18 9-18 9 4-9-4-9Zm4 9h14" />
      </>
    ),
    chat: <path d="M3 4h18v13H9l-6 4V4Z" />,
    stop: <rect x="6" y="6" width="12" height="12" />,
    sound: (
      <>
        <path d="M4 9h4l5-5v16l-5-5H4zM17 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14" />
      </>
    ),
    copy: (
      <>
        <rect x="8" y="8" width="12" height="13" rx="1" />
        <path d="M16 8V3H3v13h5" />
      </>
    ),
    plus: <path d="M12 4v16M4 12h16" />,
    power: (
      <>
        <path d="M12 2v10M6 5a9 9 0 1 0 12 0" />
      </>
    ),
  };
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
    >
      {paths[name] || paths.core}
    </svg>
  );
}
