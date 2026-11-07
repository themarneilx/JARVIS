import { useLayoutEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Color, Group, InstancedMesh, MathUtils, Object3D } from "three";
import type { Phase } from "../state/machine";
import { audioBus } from "../services/audioBus";

function Ticks({
  radius,
  count = 96,
  color = "#42d8e7",
  width = 0.018,
}: {
  radius: number;
  count?: number;
  color?: string;
  width?: number;
}) {
  const ref = useRef<InstancedMesh>(null);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const dummy = new Object3D();
    for (let i = 0; i < count; i++) {
      const a = (i / count) * Math.PI * 2;
      dummy.position.set(Math.cos(a) * radius, Math.sin(a) * radius, 0);
      dummy.rotation.z = a - Math.PI / 2;
      dummy.scale.set(1, i % 8 === 0 ? 2 : 1, 1);
      dummy.updateMatrix();
      ref.current.setMatrixAt(i, dummy.matrix);
    }
    ref.current.instanceMatrix.needsUpdate = true;
  }, [count, radius]);
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, count]}>
      <boxGeometry args={[width, 0.07, 0.012]} />
      <meshBasicMaterial
        color={color}
        transparent
        opacity={0.7}
        toneMapped={false}
      />
    </instancedMesh>
  );
}
function Arc({
  radius,
  start,
  length,
  bright = false,
}: {
  radius: number;
  start: number;
  length: number;
  bright?: boolean;
}) {
  const color = useMemo(
    () =>
      new Color(bright ? "#27e8ee" : "#14748c").multiplyScalar(
        bright ? 1.6 : 0.8,
      ),
    [bright],
  );
  return (
    <mesh rotation={[0, 0, start]}>
      <torusGeometry
        args={[
          radius,
          bright ? 0.025 : 0.007,
          5,
          Math.max(16, Math.ceil(length * 30)),
          length,
        ]}
      />
      <meshBasicMaterial
        color={color}
        transparent
        opacity={bright ? 0.85 : 0.6}
        toneMapped={false}
      />
    </mesh>
  );
}
export function HolographicRings({
  phase,
  reduced,
}: {
  phase: Phase;
  reduced: boolean;
}) {
  const outer = useRef<Group>(null),
    middle = useRef<Group>(null),
    inner = useRef<Group>(null),
    assembly = useRef<Group>(null);
  useFrame((state, dt) => {
    if (
      !outer.current ||
      !middle.current ||
      !inner.current ||
      !assembly.current
    )
      return;
    const delta = Math.min(dt, 0.08);
    const speed =
      phase === "thinking"
        ? 2.8
        : phase === "executing_tool"
          ? 3.8
          : phase === "transcribing"
            ? 2
            : 1;
    if (!reduced) {
      outer.current.rotation.z += delta * 0.055 * speed;
      middle.current.rotation.z -= delta * 0.11 * speed;
      inner.current.rotation.z += delta * 0.16 * speed;
    }
    const amplitude =
      phase === "listening" || phase === "speaking" ? audioBus.amplitude() : 0;
    const scale = (phase === "listening" ? 1.045 : 1) + amplitude * 0.045;
    assembly.current.scale.setScalar(
      MathUtils.damp(assembly.current.scale.x, scale, 5, delta),
    );
    if (!reduced) {
      assembly.current.rotation.y = MathUtils.damp(
        assembly.current.rotation.y,
        state.pointer.x * 0.12,
        3,
        delta,
      );
      assembly.current.rotation.x = MathUtils.damp(
        assembly.current.rotation.x,
        0.18 - state.pointer.y * 0.08,
        3,
        delta,
      );
    }
  });
  return (
    <group ref={assembly} rotation={[0.18, 0, 0]}>
      <group ref={outer}>
        <Arc radius={3.08} start={0} length={Math.PI * 2} />
        <Arc radius={2.96} start={0.2} length={1.8} bright />
        <Arc radius={2.96} start={2.4} length={0.5} bright />
        <Arc radius={2.96} start={3.25} length={1.25} bright />
        <Ticks
          radius={2.84}
          count={120}
          color={phase === "error" ? "#e8ab61" : "#2a929f"}
        />
        <Arc radius={2.74} start={0} length={6.28} />
      </group>
      <group ref={middle} rotation={[0.15, -0.18, 0.4]}>
        <Ticks radius={2.48} count={72} width={0.035} />
        <Arc radius={2.6} start={0.1} length={2.1} bright />
        <Arc radius={2.6} start={2.8} length={2.7} />
        <Arc radius={2.31} start={0} length={6.28} />
        {Array.from({ length: 12 }, (_, i) => (
          <mesh
            key={i}
            position={[
              Math.cos((i / 12) * Math.PI * 2) * 2.18,
              Math.sin((i / 12) * Math.PI * 2) * 2.18,
              0,
            ]}
            rotation={[0, 0, (i / 12) * Math.PI * 2]}
          >
            <boxGeometry args={[0.1, 0.024, 0.02]} />
            <meshBasicMaterial color="#518c9b" />
          </mesh>
        ))}
      </group>
      <group ref={inner} rotation={[-0.2, 0.12, 0]}>
        <Arc radius={1.92} start={0} length={6.28} />
        <Ticks radius={1.83} count={100} color="#267d99" />
        <Arc radius={1.66} start={0.6} length={1.8} bright />
        <Arc radius={1.66} start={3} length={2.5} bright />
      </group>
      <group rotation={[1.05, 0.35, -0.3]}>
        <Arc radius={2.1} start={0} length={6.28} />
        <Arc radius={2.13} start={0.3} length={2.2} bright />
      </group>
    </group>
  );
}
