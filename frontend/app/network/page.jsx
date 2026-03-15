"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function NetworkPageRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/intelligence");
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: "#0a0806", color: "#FFB800" }}>
      <div className="text-[11px] font-mono uppercase tracking-[0.22em]">Redirecting to Narrative Ecosystem...</div>
    </div>
  );
}
