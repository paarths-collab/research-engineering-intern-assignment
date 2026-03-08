"use client";

import ParticlesBackground from "../components/ParticlesBackground";
import AmbrosiaPage from "../components/AmbrosiaPage";

export default function Home() {
    return (
        <main className="relative min-h-screen bg-[#05070A] overflow-hidden">
            {/* background particles */}
            {/* <ParticlesBackground /> */}

            {/* hero content */}
            <section className="relative z-10 block min-h-screen">
                <AmbrosiaPage />
            </section>
        </main>
    );
}
