import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { AppSidebar } from "@/components/app-sidebar";
import { PolicyStrip } from "@/components/policy-strip";
import { Providers } from "@/components/providers";
import "./globals.css";

const geistSans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "ToolSmith",
  description: "Procedural memory for agents: repeated workflows become tested, reusable tools.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="h-full bg-background text-foreground">
        <Providers>
          <div className="flex h-full">
            <AppSidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <main className="flex-1 overflow-y-auto">
                <div className="mx-auto max-w-6xl px-8 py-8">{children}</div>
              </main>
              <PolicyStrip />
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
