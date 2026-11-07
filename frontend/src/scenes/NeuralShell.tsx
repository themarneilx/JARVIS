import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { AdditiveBlending, Group, MathUtils } from 'three';
import { audioBus } from '../services/audioBus';
import type { Phase } from '../state/machine';

export function NeuralShell({ phase, reduced }: { phase: Phase; reduced: boolean }) {
  const group = useRef<Group>(null);
  const { nodes, links } = useMemo(() => {
    const points: number[][] = [];
    for (let i = 0; i < 180; i++) {
      const y = 1 - (i / 179) * 2;
      const r = Math.sqrt(1 - y * y);
      const a = i * Math.PI * (3 - Math.sqrt(5));
      points.push([Math.cos(a) * r * 1.26, y * 1.26, Math.sin(a) * r * 1.26]);
    }
    const lines: number[] = [];
    for (let i = 0; i < points.length; i++) for (let j = i + 1; j < points.length; j++) {
      const a = points[i], b = points[j];
      if (Math.hypot(a[0]-b[0], a[1]-b[1], a[2]-b[2]) < .35) lines.push(...a, ...b);
    }
    return { nodes: new Float32Array(points.flat()), links: new Float32Array(lines) };
  }, []);
  useFrame((_, dt) => {
    if (!group.current || reduced) return;
    const delta = Math.min(dt, .08);
    group.current.rotation.y -= delta * (phase === 'thinking' ? .19 : .045);
    group.current.rotation.z += delta * .018;
    const amplitude = phase === 'speaking' || phase === 'listening' ? audioBus.amplitude() : 0;
    group.current.scale.setScalar(MathUtils.damp(group.current.scale.x, 1 + amplitude * .12, 8, delta));
  });
  return <group ref={group} rotation={[.2, .4, .1]}>
    <points>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[nodes, 3]} /></bufferGeometry>
      <pointsMaterial color={phase === 'error' ? '#eeaa66' : '#7bf6eb'} size={.022} transparent opacity={.8} depthWrite={false} blending={AdditiveBlending} />
    </points>
    <lineSegments>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[links, 3]} /></bufferGeometry>
      <lineBasicMaterial color="#56bfcf" transparent opacity={.2} depthWrite={false} blending={AdditiveBlending} />
    </lineSegments>
  </group>;
}
