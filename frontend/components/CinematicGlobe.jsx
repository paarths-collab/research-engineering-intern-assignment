'use client';
import React, { useRef, Suspense } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { useTexture, Float } from '@react-three/drei';
import * as THREE from 'three';

function EarthModel() {
  const earthRef = useRef(null);
  const cloudsRef = useRef(null);

  // High-res textures from common CDN
  const [colorMap, cloudsMap] = useTexture([
    'https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg',
    'https://raw.githubusercontent.com/mrdoob/three.js/master/examples/textures/planets/earth_clouds_1024.png',
  ]);

  useFrame((state, delta) => {
    if (earthRef.current) earthRef.current.rotation.y += delta * 0.05;
    if (cloudsRef.current) cloudsRef.current.rotation.y += delta * 0.07;
  });

  return (
    <group rotation={[0.4, 0, 0]}> {/* Tilts Earth slightly toward viewer */}
      {/* Base Earth */}
      <mesh ref={earthRef}>
        <sphereGeometry args={[1, 64, 64]} />
        <meshStandardMaterial 
          map={colorMap} 
          roughness={1}
          metalness={0}
        />
      </mesh>

      {/* Clouds Layer */}
      <mesh ref={cloudsRef} scale={1.01}>
        <sphereGeometry args={[1, 64, 64]} />
        <meshStandardMaterial 
          map={cloudsMap} 
          transparent={true} 
          opacity={0.4} 
          blending={THREE.AdditiveBlending}
        />
      </mesh>
    </group>
  );
}

export default function CinematicGlobe() {
  return (
    <Canvas 
      camera={{ position: [0, 0, 2.2], fov: 45 }}
      style={{ background: 'transparent' }}
    >
      {/* 1. Ambient Light - very low to keep the bottom face dark */}
      <ambientLight intensity={0.05} />

      {/* 2. THE RIM LIGHT - Positioned behind and above the globe */}
      {/* This creates the glowing top edge seen in your image */}
      <spotLight 
        position={[0, 5, -2]} 
        intensity={200} 
        color="#4db8ff" 
        angle={0.5} 
        penumbra={1} 
      />

      {/* 3. Top-down directional light for subtle detail */}
      <directionalLight position={[0, 2, 1]} intensity={1.5} color="#ffffff" />

      <React.Suspense fallback={null}>
        <Float speed={1.5} rotationIntensity={0.2} floatIntensity={0.5}>
          <EarthModel />
        </Float>
      </React.Suspense>
    </Canvas>
  );
}
