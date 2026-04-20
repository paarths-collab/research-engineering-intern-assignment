"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";

const NAV_ITEMS = [
    {
        label: "Home",
        href: "/",
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
            </svg>
        ),
    },
    {
        label: "Overview",
        href: "/overview",
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
            </svg>
        ),
    },
    {
        label: "Polar Analysis",
        href: "/polar",
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
            </svg>
        ),
    },
    {
        label: "Narrative Ecosystem",
        href: "/intelligence",
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
            </svg>
        ),
    },
    {
        label: "Streamgraph",
        href: "/stream",
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
        ),
    },
    {
        label: "Globe",
        href: "/globe",
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" />
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
            </svg>
        ),
    },
    {
        label: "Chatbot",
        href: "/chatbot",
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
        ),
    },
    {
        label: "Perspective",
        href: "/perspective",
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a7 7 0 0 1 7 7v3a7 7 0 0 1-14 0V9a7 7 0 0 1 7-7z" />
                <path d="M4 22c1.5-3 4.5-4.5 8-4.5S18.5 19 20 22" />
            </svg>
        ),
    },
];

export default function Sidebar() {
    const [open, setOpen] = useState(false);
    const pathname = usePathname();
    const showSidebarControls = pathname !== "/" && pathname !== "/preview";

    if (!showSidebarControls) {
        return null;
    }

    return (
        <>
            {/* Toggle Button — always visible */}
            <motion.button
                onClick={() => setOpen((v) => !v)}
                className="fixed top-5 left-5 z-[200] flex items-center justify-center w-9 h-9 bg-[#0a0806] border border-[#FFB800]/30 text-[#FFB800] hover:border-[#FFB800] hover:bg-[#FFB800]/10 transition-all duration-200"
                style={{ borderRadius: 0 }}
                whileTap={{ scale: 0.9 }}
                aria-label="Toggle sidebar"
                suppressHydrationWarning
            >
                <motion.span
                    animate={{ rotate: open ? 90 : 0 }}
                    transition={{ duration: 0.25 }}
                    className="flex flex-col gap-[4px] items-center justify-center"
                >
                    {open ? (
                        /* X icon when open */
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                    ) : (
                        /* Hamburger icon when closed */
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
                        </svg>
                    )}
                </motion.span>
            </motion.button>

            {/* Sidebar panel */}
            <AnimatePresence>
                {open && (
                    <>
                        {/* Backdrop */}
                        <motion.div
                            key="backdrop"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.2 }}
                            className="fixed inset-0 z-[150] bg-black/50 backdrop-blur-sm"
                            onClick={() => setOpen(false)}
                        />

                        {/* Panel */}
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
                            {/* Brand header */}
                            <div className="flex items-center gap-3 px-6 py-5 border-b border-[#FFB800]/10 mt-14">
                                <div className="w-1 h-6 bg-[#FFB800]" style={{ boxShadow: "0 0 12px rgba(255,184,0,0.5)" }} />
                                <span className="text-[13px] font-bold text-white/80 font-manrope uppercase tracking-[0.2em]">
                                    NarrativeSignal
                                </span>
                            </div>

                            {/* Nav links */}
                            <nav className="flex-1 py-4 overflow-y-auto">
                                <div className="px-4 mb-2">
                                    <span className="text-[9px] font-mono text-[#FFB800]/40 uppercase tracking-[0.3em]">Navigation</span>
                                </div>
                                <ul className="flex flex-col gap-0.5 px-2">
                                    {NAV_ITEMS.map((item) => {
                                        const isActive = pathname === item.href;
                                        return (
                                            <li key={item.href}>
                                                <Link
                                                    href={item.href}
                                                    onClick={() => setOpen(false)}
                                                    className={`flex items-center gap-3 px-3 py-2.5 text-[12px] font-inter uppercase tracking-wider transition-all duration-150 ${isActive
                                                        ? "bg-[#FFB800]/10 text-[#FFB800] border-l-2 border-[#FFB800]"
                                                        : "text-white/40 hover:text-white/80 hover:bg-white/5 border-l-2 border-transparent"
                                                        }`}
                                                >
                                                    <span className={isActive ? "text-[#FFB800]" : "text-white/30"}>
                                                        {item.icon}
                                                    </span>
                                                    <span className="font-manrope font-semibold">{item.label}</span>
                                                    {isActive && (
                                                        <motion.div
                                                            layoutId="activeIndicator"
                                                            className="ml-auto w-1 h-1 rounded-full bg-[#FFB800]"
                                                        />
                                                    )}
                                                </Link>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </nav>

                            {/* Footer */}
                            <div className="px-6 py-4 border-t border-[#FFB800]/10">
                                <p className="text-[9px] font-mono text-white/20 uppercase tracking-widest">
                                    Research Interface v2.0
                                </p>
                            </div>
                        </motion.aside>
                    </>
                )}
            </AnimatePresence>
        </>
    );
}
