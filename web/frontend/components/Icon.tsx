// Adapted from Mailguard's Icon.jsx; see ../LICENSE and THIRD_PARTY_NOTICES.md.
export default function Icon({ name, size = 24 }: { name: "upload" | "mail"; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {name === "mail" ? <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></> : <><path d="M12 16V4m-5 5 5-5 5 5" /><path d="M20 16.5v2A1.5 1.5 0 0 1 18.5 20h-13A1.5 1.5 0 0 1 4 18.5v-2" /></>}
  </svg>;
}
