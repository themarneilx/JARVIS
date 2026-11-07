import { useLayoutEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import {
  BufferAttribute,
  BufferGeometry,
  DynamicDrawUsage,
  InstancedMesh,
  LineBasicMaterial,
  MathUtils,
  Object3D,
} from "three";
import { audioBus } from "../services/audioBus";
import type { Phase } from "../state/machine";

const POINTS = 128,
  BANDS = 48;
export function SpeechWaveform({
  phase,
  reduced,
}: {
  phase: Phase;
  reduced: boolean;
}) {
  const geometry = useRef<BufferGeometry>(null),
    material = useRef<LineBasicMaterial>(null),
    bars = useRef<InstancedMesh>(null);
  const positions = useMemo(() => new Float32Array(POINTS * 3), []);
  const radii = useMemo(() => new Float32Array(POINTS).fill(1.39), []);
  const heights = useMemo(() => new Float32Array(BANDS).fill(0.015), []);
  const dummy = useMemo(() => new Object3D(), []);
  useLayoutEffect(() => {
    const attribute = geometry.current?.getAttribute("position") as
      BufferAttribute | undefined;
    attribute?.setUsage(DynamicDrawUsage);
  }, []);
  useFrame((_, dt) => {
    if (!geometry.current || !material.current || !bars.current) return;
    const active = !reduced && (phase === "speaking" || phase === "listening");
    const wave = active ? audioBus.waveform() : null,
      spectrum = active ? audioBus.spectrum() : null;
    const delta = Math.min(dt, 0.08);
    for (let i = 0; i < POINTS; i++) {
      const angle = (i / POINTS) * Math.PI * 2;
      const sample = wave
        ? (wave[Math.floor((i / POINTS) * wave.length)] - 128) / 128
        : 0;
      radii[i] = MathUtils.damp(radii[i], 1.39 + sample * 0.65, 24, delta);
      positions[i * 3] = Math.cos(angle) * radii[i];
      positions[i * 3 + 1] = Math.sin(angle) * radii[i];
      positions[i * 3 + 2] = sample * 0.16;
    }
    geometry.current.getAttribute("position").needsUpdate = true;
    material.current.opacity = MathUtils.damp(
      material.current.opacity,
      active ? 0.95 : 0.18,
      10,
      delta,
    );
    for (let i = 0; i < BANDS; i++) {
      const angle = (i / BANDS) * Math.PI * 2;
      const index = spectrum
        ? Math.min(
            spectrum.length - 1,
            Math.floor(2 ** ((i / (BANDS - 1)) * 6)) - 1,
          )
        : 0;
      const power = spectrum ? spectrum[index] / 255 : 0;
      heights[i] = MathUtils.damp(
        heights[i],
        0.015 + power * power * 0.3,
        18,
        delta,
      );
      dummy.position.set(
        Math.cos(angle) * (1.49 + heights[i] / 2),
        Math.sin(angle) * (1.49 + heights[i] / 2),
        0,
      );
      dummy.rotation.z = angle - Math.PI / 2;
      dummy.scale.set(1, heights[i], 1);
      dummy.updateMatrix();
      bars.current.setMatrixAt(i, dummy.matrix);
    }
    bars.current.instanceMatrix.needsUpdate = true;
  });
  return (
    <group rotation={[0.18, 0, 0]}>
      <lineLoop frustumCulled={false}>
        <bufferGeometry ref={geometry}>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        </bufferGeometry>
        <lineBasicMaterial
          ref={material}
          color="#64fcff"
          transparent
          opacity={0.18}
          toneMapped={false}
        />
      </lineLoop>
      <instancedMesh
        ref={bars}
        args={[undefined, undefined, BANDS]}
        frustumCulled={false}
      >
        <boxGeometry args={[0.018, 1, 0.015]} />
        <meshBasicMaterial
          color="#2ce9ef"
          transparent
          opacity={0.8}
          toneMapped={false}
        />
      </instancedMesh>
    </group>
  );
}
