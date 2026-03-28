"use client";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import ThreeGlobe from "three-globe";
import { OrbitControls } from "three-stdlib";

function generateArcs(pins) {
  const valid = (pins || []).filter((p) => Number.isFinite(p?.lat) && Number.isFinite(p?.lon));
  if (valid.length >= 2) {
    const arcs = [];
    for (let i = 0; i < Math.min(valid.length - 1, 30); i += 1) {
      const a = valid[i];
      const b = valid[i + 1];
      arcs.push({
        startLat: a.lat,
        startLng: a.lon,
        endLat: b.lat,
        endLng: b.lon,
      });
    }
    return arcs;
  }

  return Array.from({ length: 15 }).map(() => ({
    startLat: (Math.random() - 0.5) * 180,
    startLng: (Math.random() - 0.5) * 360,
    endLat: (Math.random() - 0.5) * 180,
    endLng: (Math.random() - 0.5) * 360,
  }));
}

function pinToPoint(pin, selectedId) {
  const isSelected = pin?.id === selectedId;
  const risk = String(pin?.risk_level || "");
  const color = isSelected
    ? "#FFFFFF"
    : risk === "High"
      ? "#FFA000"
      : risk === "Medium"
        ? "#FFB800"
        : "#8B7500";

  return {
    lat: pin.lat,
    lng: pin.lon,
    size: isSelected ? 0.65 : 0.45,
    color,
    id: pin.id,
    title: pin.title,
  };
}

export default function GlobeViewer({ pins = [], selectedId, onPinClick, onDblClick, onCoordinateClick }) {
  const mountRef = useRef(null);
  const globeRef = useRef(null);
  const rendererRef = useRef(null);
  const cameraRef = useRef(null);
  const controlsRef = useRef(null);
  const frameRef = useRef(null);
  const pinsRef = useRef(pins);

  const findNearestPin = (lat, lon, maxDistanceDeg = 2.8) => {
    const validPins = (pinsRef.current || []).filter((p) => Number.isFinite(p?.lat) && Number.isFinite(p?.lon));
    let nearest = null;
    let best = Number.POSITIVE_INFINITY;

    for (const p of validPins) {
      const dLat = Math.abs(lat - p.lat);
      let dLon = Math.abs(lon - p.lon);
      if (dLon > 180) dLon = 360 - dLon;
      const dist2 = dLat * dLat + dLon * dLon;
      if (dist2 < best) {
        best = dist2;
        nearest = p;
      }
    }

    return nearest && best <= maxDistanceDeg * maxDistanceDeg ? nearest : null;
  };

  useEffect(() => {
    pinsRef.current = pins;
  }, [pins]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const width = mount.clientWidth || 1000;
    const height = mount.clientHeight || 1000;

    const scene = new THREE.Scene();

    const camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 2500);
    camera.position.z = 290;
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(width, height);
    rendererRef.current = renderer;
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.enablePan = false;
    controls.minDistance = 180;
    controls.maxDistance = 700;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.8;
    controlsRef.current = controls;

    const globe = new ThreeGlobe()
      .globeImageUrl("/earth-night.jpg")
      .bumpImageUrl("/earth-topology.png")
      .arcsData(generateArcs(pins))
      .arcColor(() => ["#FFB800", "#8B7500"])
      .arcAltitude(0.2)
      .arcStroke(0.5)
      .arcDashLength(0.4)
      .arcDashGap(1)
      .arcDashAnimateTime(3000)
      .pointsData((pins || []).filter((p) => Number.isFinite(p?.lat) && Number.isFinite(p?.lon)).map((p) => pinToPoint(p, selectedId)))
      .pointLat("lat")
      .pointLng("lng")
      .pointAltitude(0.02)
      .pointRadius("size")
      .pointColor("color");

    // globe.gl-style animated cloud shell
    const globeRadius = typeof globe.getGlobeRadius === "function" ? globe.getGlobeRadius() : 100;
    const cloudGeometry = new THREE.SphereGeometry(globeRadius * 1.01, 64, 64);
    const cloudTexture = new THREE.TextureLoader().load(
      "https://unpkg.com/three-globe/example/img/earth-clouds.png"
    );
    const cloudMaterial = new THREE.MeshPhongMaterial({
      map: cloudTexture,
      transparent: true,
      opacity: 0.33,
      depthWrite: false,
    });
    const clouds = new THREE.Mesh(cloudGeometry, cloudMaterial);

    globeRef.current = globe;
    scene.add(globe);
    scene.add(clouds);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    const dLight = new THREE.DirectionalLight(0xffffff, 1.8);
    dLight.position.set(-200, 100, 200);
    scene.add(dLight);

    const animate = () => {
      controls.update();
      clouds.rotation.y += 0.0008;
      renderer.render(scene, camera);
      frameRef.current = requestAnimationFrame(animate);
    };

    animate();

    const handleResize = () => {
      const w = mount.clientWidth || width;
      const h = mount.clientHeight || height;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };

    const handleDblClick = () => onDblClick?.();
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const handleClick = (event) => {
      const rect = renderer.domElement.getBoundingClientRect();
      if (!rect.width || !rect.height) return;

      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);

      const intersects = raycaster.intersectObject(globe, true);
      if (!intersects.length) return;

      const hit = intersects.find((i) => i?.point) || intersects[0];
      if (!hit?.point) return;

      const r = hit.point.length();
      if (!Number.isFinite(r) || r <= 0) return;

      const lat = THREE.MathUtils.radToDeg(Math.asin(hit.point.y / r));
      const lon = THREE.MathUtils.radToDeg(Math.atan2(hit.point.z, -hit.point.x));
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

      const nearestPin = findNearestPin(lat, lon);
      if (nearestPin) {
        onPinClick?.(nearestPin);
      } else {
        onCoordinateClick?.(lat, lon);
      }
    };

    window.addEventListener("resize", handleResize);
    renderer.domElement.addEventListener("click", handleClick);
    renderer.domElement.addEventListener("dblclick", handleDblClick);

    return () => {
      window.removeEventListener("resize", handleResize);
      renderer.domElement.removeEventListener("click", handleClick);
      renderer.domElement.removeEventListener("dblclick", handleDblClick);
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
      controls.dispose();
      cloudGeometry.dispose();
      cloudMaterial.dispose();
      cloudTexture.dispose();
      renderer.dispose();
      if (mount.contains(renderer.domElement)) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!globeRef.current) return;
    globeRef.current
      .pointsData((pins || []).filter((p) => Number.isFinite(p?.lat) && Number.isFinite(p?.lon)).map((p) => pinToPoint(p, selectedId)))
      .arcsData(generateArcs(pins));
  }, [pins, selectedId]);

  useEffect(() => {
    if (!selectedId || !cameraRef.current || !controlsRef.current) return;
    const pin = (pins || []).find((p) => p.id === selectedId);
    if (!pin || !Number.isFinite(pin.lat) || !Number.isFinite(pin.lon)) return;

    const radius = 220;
    const phi = (90 - pin.lat) * (Math.PI / 180);
    const theta = (pin.lon + 180) * (Math.PI / 180);
    const x = -(radius * Math.sin(phi) * Math.cos(theta));
    const y = radius * Math.cos(phi);
    const z = radius * Math.sin(phi) * Math.sin(theta);

    cameraRef.current.position.set(x, y, z);
    controlsRef.current.update();
  }, [selectedId, pins]);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div ref={mountRef} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}