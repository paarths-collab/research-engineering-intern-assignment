

"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import ThreeGlobe from "three-globe";
import { OrbitControls } from "three-stdlib";

export default function GlobeVisualization() {

    const mountRef = useRef(null);

    useEffect(() => {

        const width = 1600;
        const height = 1600;

        const scene = new THREE.Scene();

        const camera = new THREE.PerspectiveCamera(
            60,
            width / height,
            0.1,
            2000
        );

        camera.position.z = 220;

        const renderer = new THREE.WebGLRenderer({
            antialias: true,
            alpha: true
        });

        renderer.setSize(width, height);

        mountRef.current.appendChild(renderer.domElement);

        const controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.enablePan = false;
        controls.minDistance = 150;
        controls.maxDistance = 600;
        controls.autoRotate = true;
        controls.autoRotateSpeed = 0.8;

        const globe = new ThreeGlobe()
            .globeImageUrl("/earth-night.jpg")
            .bumpImageUrl("/earth-topology.png")
            .arcsData(generateArcs())
            .arcColor(() => ["#ff0033", "#ff6600"])
            .arcAltitude(0.2)
            .arcStroke(0.5)
            .arcDashLength(0.4)
            .arcDashGap(1)
            .arcDashAnimateTime(3000);

        scene.add(globe);

        const ambientLight = new THREE.AmbientLight(0xffffff, 0.4); // Subtle ambient glow
        scene.add(ambientLight);

        const dLight = new THREE.DirectionalLight(0xffffff, 1.8); // Strong sunlight
        dLight.position.set(-200, 100, 200); // Shines from the left to create shadows
        scene.add(dLight);

        function animate() {
            controls.update();
            renderer.render(scene, camera);
            requestAnimationFrame(animate);
        }

        animate();

        const currentMount = mountRef.current;
        return () => {
            controls.dispose();
            if (currentMount && renderer.domElement && currentMount.contains(renderer.domElement)) {
                currentMount.removeChild(renderer.domElement);
            }
        };

    }, []);

    function generateArcs() {

        return Array.from({ length: 15 }).map(() => ({
            startLat: (Math.random() - 0.5) * 180,
            startLng: (Math.random() - 0.5) * 360,
            endLat: (Math.random() - 0.5) * 180,
            endLng: (Math.random() - 0.5) * 360
        }));

    }

    return (
        <div
            style={{
                position: "absolute",
                inset: 0,
                display: "flex",
                justifyContent: "center",
                alignItems: "center"
            }}
        >
            <div ref={mountRef} />
        </div>
    );
}