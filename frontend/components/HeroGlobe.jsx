'use client';

import { useEffect, useRef } from 'react';
import Globe from 'react-globe.gl';
import * as THREE from 'three';

export default function HeroGlobe() {
  const globeRef = useRef(null);

  useEffect(() => {
    const globe = globeRef.current;
    if (!globe) return;

    // 1. Get the underlying Three.js scene
    const scene = globe.scene();
    
    // 2. Dim the Ambient Light for a moody tone
    const ambientLight = scene.children.find(obj => obj.type === 'AmbientLight');
    if (ambientLight) ambientLight.intensity = 0.1; 

    // 3. Add Subtle Dimmed Lighting for Clouds
    const dLight = new THREE.DirectionalLight(0xffffff, 0.4);
    dLight.position.set(1, 1, 1);
    scene.add(dLight);

    // 4. Configure Controls (STABLE - NO ROTATION)
    const controls = globe.controls();
    if (controls) {
      controls.enableZoom = false;
      controls.autoRotate = false;
    }

    // 5. Add Static Clouds Sphere
    const CLOUDS_IMG_URL = '//unpkg.com/three-globe/example/img/clouds.png';
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
  }, []);

  return (
    <div className="flex items-center justify-center w-full h-full">
      <Globe
        ref={globeRef}
        width={2700}
        height={1500}
        backgroundColor="rgba(0,0,0,0)"
        globeImageUrl="//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
        bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
        showAtmosphere={true}
        atmosphereColor="#ffffff" 
        atmosphereAltitude={0.15}
      />
    </div>
  );
}
