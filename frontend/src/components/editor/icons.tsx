// Small inline icons (16px, currentColor). No icon library: the editor needs only a handful.
import type { ReactNode } from "react";

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {children}
    </svg>
  );
}

export const ListIcon = () => (
  <Icon>
    <path d="M6 4h8M6 8h8M6 12h8" />
    <circle cx="2.5" cy="4" r=".6" fill="currentColor" />
    <circle cx="2.5" cy="8" r=".6" fill="currentColor" />
    <circle cx="2.5" cy="12" r=".6" fill="currentColor" />
  </Icon>
);

export const TableIcon = () => (
  <Icon>
    <rect x="2" y="3" width="12" height="10" rx="1.5" />
    <path d="M2 7h12M7 3v10" />
  </Icon>
);

export const UndoIcon = () => (
  <Icon>
    <path d="M5.5 3.5 2.5 6.5l3 3" />
    <path d="M3 6.5h6a4 4 0 0 1 0 8H6" />
  </Icon>
);

export const RedoIcon = () => (
  <Icon>
    <path d="m10.5 3.5 3 3-3 3" />
    <path d="M13 6.5H7a4 4 0 0 0 0 8h3" />
  </Icon>
);

export const SparkIcon = () => (
  <Icon>
    <path d="M8 1.5 9.4 6.6 14.5 8 9.4 9.4 8 14.5 6.6 9.4 1.5 8 6.6 6.6z" />
  </Icon>
);

export const CloseIcon = () => (
  <Icon>
    <path d="m4 4 8 8M12 4l-8 8" />
  </Icon>
);

export const PlusIcon = () => (
  <Icon>
    <path d="M8 3v10M3 8h10" />
  </Icon>
);
