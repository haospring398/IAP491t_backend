import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "Email analysis", description: "Select one exported email for analysis." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
