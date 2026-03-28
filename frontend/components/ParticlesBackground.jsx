export default function ParticlesBackground() {
    const particles = Array.from({ length: 70 }).map((_, i) => {
        const left = ((i * 37) % 100) + "%";
        const top = ((i * 53) % 100) + "%";
        const size = 1 + (i % 3);
        const delay = `${(i % 9) * 0.35}s`;
        const duration = `${4 + (i % 6)}s`;
        const opacity = 0.15 + ((i % 5) * 0.08);
        return { left, top, size, delay, duration, opacity };
    });

    return (
        <div className="absolute inset-0 pointer-events-none z-0 overflow-hidden">
            {particles.map((p, idx) => (
                <span
                    key={idx}
                    className="absolute rounded-full bg-[#FFB800] animate-pulse"
                    style={{
                        left: p.left,
                        top: p.top,
                        width: `${p.size}px`,
                        height: `${p.size}px`,
                        opacity: p.opacity,
                        animationDelay: p.delay,
                        animationDuration: p.duration,
                        boxShadow: "0 0 8px rgba(255,184,0,0.4)",
                    }}
                />
            ))}
        </div>
    );
}