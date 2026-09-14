"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";

const NAV_ITEMS = [
    { label: "Home", href: "/", icon: "⌂" },
    { label: "V1 Overview", href: "/overview", icon: "▦" },
    { label: "Live Events", href: "/globe", icon: "◎" },
    { label: "Narratives", href: "/intelligence", icon: "◌" },
    { label: "Timeline", href: "/stream", icon: "⌁" },
    { label: "Propagation", href: "/network", icon: "⌘" },
    { label: "Sources", href: "/polar", icon: "◐" },
    { label: "Ask Intelligence", href: "/chatbot", icon: "□" },
];

export default function Sidebar() {
    const [open, setOpen] = useState(false);
    const pathname = usePathname();
    const showSidebarControls = pathname !== "/" && pathname !== "/preview";

    if (!showSidebarControls) return null;

    return (
        <>
            <motion.button
                onClick={() => setOpen((v) => !v)}
                className="fixed top-5 left-5 z-[200] flex items-center justify-center w-9 h-9 bg-[#0a0806] border border-[#FFB800]/30 text-[#FFB800] hover:border-[#FFB800] hover:bg-[#FFB800]/10 transition-all duration-200"
                style={{ borderRadius: 0 }}
                whileTap={{ scale: 0.9 }}
                aria-label="Toggle sidebar"
                suppressHydrationWarning
            >
                <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.25 }}>
                    {open ? "×" : "☰"}
                </motion.span>
            </motion.button>

            <AnimatePresence>
                {open && (
                    <>
                        <motion.div
                            key="backdrop"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.2 }}
                            className="fixed inset-0 z-[150] bg-black/50 backdrop-blur-sm"
                            onClick={() => setOpen(false)}
                        />

                        <motion.aside
                            key="sidebar"
                            initial={{ x: -300, opacity: 0 }}
                            animate={{ x: 0, opacity: 1 }}
                            exit={{ x: -300, opacity: 0 }}
                            transition={{ type: "spring", stiffness: 300, damping: 30 }}
                            className="fixed top-0 left-0 h-full z-[160] flex flex-col"
                            style={{
                                width: 260,
                                background: "rgba(6, 4, 2, 0.97)",
                                borderRight: "1px solid rgba(255, 184, 0, 0.12)",
                                backdropFilter: "blur(24px)",
                            }}
                        >
                            <div className="flex items-center gap-3 px-6 py-5 border-b border-[#FFB800]/10 mt-14">
                                <div className="w-1 h-6 bg-[#FFB800]" />
                                <div>
                                  <span className="block text-[13px] font-bold text-white/80 uppercase tracking-[0.2em]">NarrativeSignal</span>
                                  <span className="block text-[9px] text-white/30 uppercase tracking-[0.16em] mt-1">V1 Prototype</span>
                                </div>
                            </div>

                            <nav className="flex-1 py-4 overflow-y-auto">
                                <div className="px-4 mb-2">
                                    <span className="text-[9px] font-mono text-[#FFB800]/40 uppercase tracking-[0.3em]">Core workflow</span>
                                </div>
                                <ul className="flex flex-col gap-0.5 px-2">
                                    {NAV_ITEMS.map((item) => {
                                        const isActive = pathname === item.href;
                                        return (
                                            <li key={item.href}>
                                                <Link
                                                    href={item.href}
                                                    onClick={() => setOpen(false)}
                                                    className={`flex items-center gap-3 px-3 py-2.5 text-[12px] uppercase tracking-wider transition-all duration-150 ${isActive
                                                        ? "bg-[#FFB800]/10 text-[#FFB800] border-l-2 border-[#FFB800]"
                                                        : "text-white/40 hover:text-white/80 hover:bg-white/5 border-l-2 border-transparent"
                                                        }`}
                                                >
                                                    <span className={isActive ? "text-[#FFB800]" : "text-white/30"}>{item.icon}</span>
                                                    <span className="font-semibold">{item.label}</span>
                                                </Link>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </nav>

                            <div className="px-6 py-4 border-t border-[#FFB800]/10">
                                <p className="text-[9px] font-mono text-white/20 uppercase tracking-widest">
                                    Events → Narratives → Evidence
                                </p>
                            </div>
                        </motion.aside>
                    </>
                )}
            </AnimatePresence>
        </>
    );
}
