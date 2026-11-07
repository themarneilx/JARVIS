import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { audioBus } from "../services/audioBus";
import type { Phase } from "../state/machine";
import { MathUtils, Points } from "three";
export function ParticleField({
  count,
  reduced,
  phase,
}: {
  count: number;
  reduced: boolean;
  phase: Phase;
}) {
  const ref = useRef<Points>(null);
  const positions = useMemo(() => {
    const array = new Float32Array(count * 3);
    let seed = 42;
    const rand = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 4294967296;
    };
    for (let i = 0; i < count; i++) {
      const a = rand() * Math.PI * 2,
        r = 1.4 + rand() * 3.4;
      array[i * 3] = Math.cos(a) * r;
      array[i * 3 + 1] = Math.sin(a) * r;
      array[i * 3 + 2] = (rand() - 0.5) * 4;
    }
    return array;
  }, [count]);
  useFrame((_, dt) => {
    if (ref.current && !reduced) {
      const delta = Math.min(dt, .08);
      const amplitude = phase === "listening" || phase === "speaking" ? audioBus.amplitude() : 0;
      ref.current.rotation.z += delta * .018;
      ref.current.scale.setScalar(MathUtils.damp(ref.current.scale.x, 1 + amplitude * .035, 6, delta));
    }
  });
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        color="#52dce5"
        size={0.014}
        transparent
        opacity={0.55}
        depthWrite={false}
      />
    </points>
  );
}
