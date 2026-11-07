import {
  Component,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Line } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { AdditiveBlending, BackSide, Color, Mesh, ShaderMaterial } from "three";
import { HolographicRings } from "./HolographicRings";
import { ParticleField } from "./ParticleField";
import { NeuralShell } from "./NeuralShell";
import { SpeechWaveform } from "./SpeechWaveform";
import { audioBus } from "../services/audioBus";
import {
  phaseLabels,
  presets,
  type Phase,
  type Quality,
} from "../state/machine";

class RenderBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <Fallback /> : this.props.children;
  }
}
export function Fallback() {
  return (
    <div
      className="core-fallback"
      role="img"
      aria-label="Lightweight core. WebGL is unavailable."
    >
      <div />
      <div />
      <span>
        J.A.R.V.I.S.<small>LIGHTWEIGHT DISPLAY</small>
      </span>
    </div>
  );
}
function FrameDriver({
  fps,
  active,
  reduced,
  phase,
}: {
  fps: number;
  active: boolean;
  reduced: boolean;
  phase: Phase;
}) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    invalidate();
    if (!active || reduced) return;
    const timer = setInterval(invalidate, 1000 / fps);
    return () => clearInterval(timer);
  }, [fps, active, reduced, invalidate, phase]);
  return null;
}
function CameraFit({ immersive }: { immersive: boolean }) {
  const { camera, size, invalidate } = useThree();
  useEffect(() => {
    // Keep the entire orbital assembly in frame on narrow displays.
    camera.position.z = Math.max(9.7, 8.6 * size.height / Math.max(size.width, 1));
    camera.updateProjectionMatrix();
    invalidate();
  }, [camera, size.width, size.height, immersive, invalidate]);
  return null;
}
function ResolutionBudget({ maximum }: { maximum: number }) {
  const { size, setDpr } = useThree();
  useEffect(() => {
    const budget = Math.sqrt(1_800_000 / Math.max(1, size.width * size.height));
    setDpr(Math.max(.25, Math.min(window.devicePixelRatio || 1, maximum, budget)));
  }, [size.width, size.height, maximum, setDpr]);
  return null;
}
const vertex = `varying vec3 normalView; varying vec3 positionView; void main(){normalView=normalize(normalMatrix*normal); vec4 p=modelViewMatrix*vec4(position,1.0);positionView=p.xyz;gl_Position=projectionMatrix*p;}`;
const fragment = `varying vec3 normalView; varying vec3 positionView; uniform vec3 tint; uniform float time; uniform float energy; void main(){float rim=pow(1.0-max(0.0,dot(normalize(normalView),normalize(-positionView))),2.1);float scan=pow(max(0.0,sin(positionView.y*44.0+time*0.6)),18.0)*0.15;gl_FragColor=vec4(tint*(rim*2.5+scan+0.06+energy*0.2),rim*0.85+0.12);}`;
function Energy({ phase, reduced }: { phase: Phase; reduced: boolean }) {
  const mesh = useRef<Mesh>(null),
    wire = useRef<Mesh>(null),
    shader = useRef<ShaderMaterial>(null);
  const uniforms = useMemo(
    () => ({
      tint: { value: new Color("#24d9e7") },
      time: { value: 0 },
      energy: { value: 0 },
    }),
    [],
  );
  const target = useMemo(
    () =>
      new Color(
        phase === "error"
          ? "#f2a456"
          : phase === "thinking"
            ? "#238cff"
            : "#24d9e7",
      ),
    [phase],
  );
  useFrame(({ clock }, dt) => {
    if (!mesh.current || !wire.current || !shader.current) return;
    const amplitude =
      phase === "listening" || phase === "speaking" ? audioBus.amplitude() : 0;
    const d = Math.min(dt, 0.08);
    const size = 1 + amplitude * 0.2;
    mesh.current.scale.setScalar(
      mesh.current.scale.x + (size - mesh.current.scale.x) * 0.2,
    );
    if (!reduced) {
      wire.current.rotation.y += d * (phase === "thinking" ? 0.27 : 0.07);
      wire.current.rotation.x += d * 0.025;
      shader.current.uniforms.time.value = clock.elapsedTime;
    }
    shader.current.uniforms.tint.value.lerp(target, 0.08);
    shader.current.uniforms.energy.value = amplitude;
  });
  return (
    <group ref={mesh}>
      <mesh>
        <sphereGeometry args={[1.16, 48, 32]} />
        <shaderMaterial
          ref={shader}
          vertexShader={vertex}
          fragmentShader={fragment}
          uniforms={uniforms}
          transparent
          depthWrite={false}
          blending={AdditiveBlending}
        />
      </mesh>
      <mesh ref={wire} rotation={[0.3, 0, 0]}>
        <icosahedronGeometry args={[1.12, 3]} />
        <meshBasicMaterial
          color={target}
          wireframe
          transparent
          opacity={0.18}
          toneMapped={false}
        />
      </mesh>
      <mesh scale={1.11}>
        <sphereGeometry args={[1.16, 32, 24]} />
        <meshBasicMaterial
          color="#073b54"
          transparent
          opacity={0.06}
          side={BackSide}
          blending={AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}
function Orbits() {
  const points = useMemo(
    () =>
      Array.from({ length: 101 }, (_, i) => {
        const a = (i / 100) * Math.PI * 2;
        return [Math.cos(a) * 3.45, Math.sin(a) * 3.45, 0] as [
          number,
          number,
          number,
        ];
      }),
    [],
  );
  return (
    <group rotation={[0.92, 0.35, 0.3]}>
      <Line
        points={points}
        color="#1b5e76"
        lineWidth={0.6}
        transparent
        opacity={0.5}
      />
    </group>
  );
}
function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl2");
    if (gl) {
      gl.getExtension("WEBGL_lose_context")?.loseContext();
      return true;
    }
    return false;
  } catch {
    return false;
  }
}
export default function JarvisCore({
  phase,
  quality,
  reducedMotion,
  immersive = false,
  active = true,
}: {
  phase: Phase;
  quality: Quality;
  reducedMotion: boolean;
  immersive?: boolean;
  active?: boolean;
}) {
  const [visible, setVisible] = useState(!document.hidden),
    [supported] = useState(webglAvailable),
    [lost, setLost] = useState(false);
  const config = presets[quality];
  useEffect(() => {
    const change = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", change);
    return () => document.removeEventListener("visibilitychange", change);
  }, []);
  return (
    <div
      className={`core-stage phase-${phase} ${supported && !lost ? "" : "fallback-active"}`}
      data-testid="core-stage"
      aria-label={`Assistant core: ${phaseLabels[phase]}`}
    >
      <div className="scene-coordinate top-left">
        REASONING INTERFACE
        <br />
        <span>LOCAL COMPUTE / PRIVATE CHANNEL</span>
      </div>
      {supported && !lost ? (
        <RenderBoundary>
          <Canvas
            frameloop="demand"
            dpr={[1, config.dpr]}
            camera={{ position: [0, 0, 9.7], fov: 45 }}
            gl={{ antialias: false, alpha: true, powerPreference: "low-power" }}
            onCreated={({ gl }) => {
              gl.domElement.addEventListener(
                "webglcontextlost",
                (e) => {
                  e.preventDefault();
                  setLost(true);
                },
                { once: true },
              );
            }}
            fallback={<Fallback />}
          >
            <FrameDriver
              fps={config.fps}
              active={visible && active}
              reduced={reducedMotion}
              phase={phase}
            />
            <ResolutionBudget maximum={config.dpr} />
            <CameraFit immersive={immersive} />
            <NeuralShell phase={phase} reduced={reducedMotion} />
            <Energy phase={phase} reduced={reducedMotion} />
            <SpeechWaveform phase={phase} reduced={reducedMotion} />
            <HolographicRings phase={phase} reduced={reducedMotion} />
            <ParticleField phase={phase} count={config.particles} reduced={reducedMotion} />
            <Orbits />
            {config.bloom ? (
              <EffectComposer multisampling={0} resolutionScale={0.6}>
                <Bloom luminanceThreshold={0.9} intensity={0.65} mipmapBlur />
              </EffectComposer>
            ) : null}
          </Canvas>
        </RenderBoundary>
      ) : (
        <Fallback />
      )}
      {supported && !lost ? (
        <div className="core-center">
          <span>J.A.R.V.I.S.</span>
          <small>JUST A RATHER VERY INTELLIGENT SYSTEM</small>
        </div>
      ) : null}
      <div className="scene-coordinate bottom-left">
        {supported && !lost ? "PROCEDURAL WEBGL" : "WEBGL UNAVAILABLE"}
        <br />
        <span>
          {quality.toUpperCase()} /{" "}
          {reducedMotion ? "REDUCED MOTION" : `${config.fps} FPS LIMIT`}
        </span>
      </div>
      <div className="scene-coordinate bottom-right">
        {phase.replace("_", " ").toUpperCase()}
        <br />
        <span>INFERENCE: LOCAL</span>
      </div>
    </div>
  );
}
