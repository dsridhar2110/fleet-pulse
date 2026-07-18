import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/dash/sidebar";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Fleet Pulse — Service Command Center",
  description:
    "A living predictive-maintenance system for a medical-imaging service fleet: daily telemetry, multi-horizon failure prediction, decision economics, and a model that learns under human governance. Independent portfolio project; all data synthetic.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
      <body>
        {/* Set the saved theme before paint to avoid a flash (default: dark). */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var q=new URLSearchParams(location.search).get('theme');var t=(q==='light'||q==='dark')?q:(localStorage.getItem('fp-theme')||'dark');if(q)localStorage.setItem('fp-theme',t);document.documentElement.setAttribute('data-theme',t);}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();`,
          }}
        />
        <div className="app">
          <Sidebar />
          <div className="main">{children}</div>
        </div>
      </body>
    </html>
  );
}
