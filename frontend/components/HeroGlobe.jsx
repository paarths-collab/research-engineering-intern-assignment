'use client';

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import Globe from 'react-globe.gl';
import * as THREE from 'three';

export default function HeroGlobe() {
  const globeRef = useRef(null);
  const wrapRef = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  // Track the container so the canvas matches it instead of a hardcoded size.
  // three.js draws the sphere at the canvas centre, so an oversized canvas
  // pushes the globe outside the hero.
  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;

    const measure = (width, height) =>
      setSize(prev => {
        const next = { width: Math.round(width), height: Math.round(height) };
        return prev.width === next.width && prev.height === next.height ? prev : next;
      });

    // Measure up front: a ResizeObserver alone never fires on a background
    // tab, which would leave the globe unmounted until the tab is focused.
    // clientWidth/Height, not getBoundingClientRect: the entrance animation
    // scales the wrapper, and we want the untransformed layout size to match
    // what ResizeObserver reports.
    measure(el.clientWidth, el.clientHeight);

    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      measure(width, height);
    });
    observer.observe(el);

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const globe = globeRef.current;
    if (!globe) return;

    // 1. Get the underlying Three.js scene
    const scene = globe.scene();

    // 2. Ambient light carries most of the exposure: the whole visible arc
    //    should read, not just the side facing the key light.
    const ambientLight = scene.children.find(obj => obj.type === 'AmbientLight');
    if (ambientLight) ambientLight.intensity = 0.65;

    // 3. Key light from the upper right for surface relief and cloud shading
    const dLight = new THREE.DirectionalLight(0xffffff, 0.55);
    dLight.position.set(1, 1, 1);
    scene.add(dLight);

    // 4. Configure Controls (STABLE - NO ROTATION)
    const controls = globe.controls();
    if (controls) {
      controls.enableZoom = false;
      controls.autoRotate = false;
    }

    // 5. Add Static Clouds Sphere
    // Self-hosted: the unpkg copy 404s on current versions, and the
    // http -> https redirect drops the CORS header the texture loader needs.
    const CLOUDS_IMG_URL = '/textures/clouds.png';
    const CLOUDS_ALT = 0.004;

    new THREE.TextureLoader().load(CLOUDS_IMG_URL, cloudsTexture => {
      const clouds = new THREE.Mesh(
        new THREE.SphereGeometry(globe.getGlobeRadius() * (1 + CLOUDS_ALT), 75, 75),
        new THREE.MeshPhongMaterial({ map: cloudsTexture, transparent: true, opacity: 0.7 })
      );
      scene.add(clouds);
    });

    // 6. Camera Angle (Showcasing Green Landmasses: Africa/Europe)
    globe.pointOfView({ lat: 10, lng: 25, altitude: 2.0 }, 0);
  }, [size.width > 0 && size.height > 0]);

  return (
    <div ref={wrapRef} className="flex items-center justify-center w-full h-full">
      {size.width > 0 && size.height > 0 && (
        <Globe
          ref={globeRef}
          width={size.width}
          height={size.height}
          backgroundColor="rgba(0,0,0,0)"
          globeImageUrl="//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
          bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
          showAtmosphere={true}
          atmosphereColor="#ffffff"
          atmosphereAltitude={0.15}
        />
      )}
    </div>
  );
}
