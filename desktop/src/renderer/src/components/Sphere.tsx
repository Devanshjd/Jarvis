import { Canvas, useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import type { ActivityAgent, ActivityState } from '../lib/types'

function ParticleCore({ state, agent, audioLevel }: {
  state: ActivityState
  agent: ActivityAgent
  audioLevel: number
}) {
  const pointsRef = useRef<THREE.Points>(null)
  const shellRef = useRef<THREE.Points>(null)
  const ringRef = useRef<THREE.Points>(null)
  const wireRef = useRef<THREE.Mesh>(null)
  const scanOuterRef = useRef<THREE.Mesh>(null)
  const scanInnerRef = useRef<THREE.Mesh>(null)

  const particleCount = 5200
  const shellCount = 1400
  const ringCount = 600

  const particles = useMemo(() => {
    const positions = new Float32Array(particleCount * 3)
    const origins = new Float32Array(particleCount * 3)
    const drift = new Float32Array(particleCount)

    for (let i = 0; i < particleCount; i += 1) {
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      const radius = 1.65 + Math.random() * 0.28

      const x = radius * Math.sin(phi) * Math.cos(theta)
      const y = radius * Math.sin(phi) * Math.sin(theta)
      const z = radius * Math.cos(phi)

      positions[i * 3] = x
      positions[i * 3 + 1] = y
      positions[i * 3 + 2] = z

      origins[i * 3] = x
      origins[i * 3 + 1] = y
      origins[i * 3 + 2] = z

      drift[i] = 0.35 + Math.random() * 0.75
    }

    return { positions, origins, drift }
  }, [])

  const shell = useMemo(() => {
    const positions = new Float32Array(shellCount * 3)
    for (let i = 0; i < shellCount; i += 1) {
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      const radius = 2.08 + Math.random() * 0.22

      positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta)
      positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta)
      positions[i * 3 + 2] = radius * Math.cos(phi)
    }
    return positions
  }, [])

  // Orbital ring particles — Stormbreaker-style equatorial ring
  const ring = useMemo(() => {
    const positions = new Float32Array(ringCount * 3)
    for (let i = 0; i < ringCount; i += 1) {
      const theta = (i / ringCount) * Math.PI * 2 + Math.random() * 0.04
      const radius = 2.4 + Math.random() * 0.15
      const yOffset = (Math.random() - 0.5) * 0.08

      positions[i * 3] = radius * Math.cos(theta)
      positions[i * 3 + 1] = yOffset
      positions[i * 3 + 2] = radius * Math.sin(theta)
    }
    return positions
  }, [])

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const pointCloud = pointsRef.current
    const shellCloud = shellRef.current
    const ringCloud = ringRef.current
    if (!pointCloud || !shellCloud || !ringCloud) return

    const wire = wireRef.current
    const scanOuter = scanOuterRef.current
    const scanInner = scanInnerRef.current

    // Audio-reactive energy boost — key Stormbreaker feature
    const audioBoost = audioLevel * 0.6

    // Stormbreaker energy core — amber/gold (arc-reactor tactical feel),
    // distinct from Stormbreaker's teal-green. State changes shift the amber tone.
    let energy = 0.08 + audioBoost
    let rotationBoost = 0.06
    let scanStrength = 0.08
    let wireOpacity = 0.08
    let hue = '#FFB020'                       // idle — tactical amber

    if (state === 'listening') {
      energy = 0.2 + audioBoost * 1.5
      rotationBoost = 0.11
      hue = '#FFD24A'                         // listening — bright gold
    } else if (state === 'thinking') {
      energy = 0.32 + audioBoost
      rotationBoost = 0.22
      hue = '#FF8C2A'                         // thinking — hot orange
    } else if (state === 'idle') {
      energy = 0.14 + audioBoost
      rotationBoost = 0.09
      hue = '#FFC862'                         // waiting — soft amber
    }

    if (state === 'tool_running') {
      energy = 0.28 + audioBoost
      rotationBoost = 0.2
      hue = agent === 'ULTRON' ? '#FF5364'
        : agent === 'FRIDAY' ? '#45D8FF'
          : agent === 'VISION' ? '#B89CFF'
            : agent === 'EDITH' ? '#63E6A6'
              : '#FFB020'
      scanStrength = 0.34
      wireOpacity = 0.24
    } else if (state === 'speaking') {
      energy = 0.28 + audioBoost * 1.8
      rotationBoost = 0.14
      hue = '#FFE29A'
      scanStrength = 0.22
      wireOpacity = 0.18
    } else if (state === 'error') {
      energy = 0.16 + audioBoost
      rotationBoost = 0.04
      hue = '#FF5364'
      scanStrength = 0.4
      wireOpacity = 0.28
    } else if (state === 'listening') {
      scanStrength = 0.2
      wireOpacity = 0.16
    } else if (state === 'thinking') {
      scanStrength = 0.28
      wireOpacity = 0.2
    }

    pointCloud.rotation.y += rotationBoost * 0.01
    pointCloud.rotation.z += rotationBoost * 0.004
    shellCloud.rotation.y -= rotationBoost * 0.004
    shellCloud.rotation.x += rotationBoost * 0.002
    ringCloud.rotation.y += 0.003
    ringCloud.rotation.x = Math.sin(t * 0.2) * 0.1

    const current = pointCloud.geometry.attributes.position.array as Float32Array
    const shellCurrent = shellCloud.geometry.attributes.position.array as Float32Array
    const ringCurrent = ringCloud.geometry.attributes.position.array as Float32Array

    for (let i = 0; i < particleCount; i += 1) {
      const index = i * 3
      const phase = t * (0.28 + particles.drift[i] * 0.42)
      const pulse = 1 + Math.sin(phase + i * 0.017) * energy
      current[index] = particles.origins[index] * pulse
      current[index + 1] = particles.origins[index + 1] * pulse
      current[index + 2] = particles.origins[index + 2] * pulse
    }

    for (let i = 0; i < shellCount; i += 1) {
      const index = i * 3
      const offset = Math.sin(t * 0.5 + i * 0.021) * (0.02 + energy * 0.08)
      shellCurrent[index] = shell[index] * (1 + offset)
      shellCurrent[index + 1] = shell[index + 1] * (1 + offset)
      shellCurrent[index + 2] = shell[index + 2] * (1 + offset)
    }

    // Orbital ring pulses with audio
    for (let i = 0; i < ringCount; i += 1) {
      const index = i * 3
      const wave = Math.sin(t * 1.2 + i * 0.05) * (0.01 + audioBoost * 0.06)
      ringCurrent[index] = ring[index] * (1 + wave)
      ringCurrent[index + 1] = ring[index + 1] + Math.sin(t * 2 + i * 0.03) * 0.02
      ringCurrent[index + 2] = ring[index + 2] * (1 + wave)
    }

    pointCloud.geometry.attributes.position.needsUpdate = true
    shellCloud.geometry.attributes.position.needsUpdate = true
    ringCloud.geometry.attributes.position.needsUpdate = true
    ;(pointCloud.material as THREE.PointsMaterial).color = new THREE.Color(hue)

    // Shell opacity reacts to audio
    const shellMat = shellCloud.material as THREE.PointsMaterial
    shellMat.opacity = 0.18 + audioBoost * 0.3

    if (wire) {
      wire.rotation.x += 0.0015 + rotationBoost * 0.006
      wire.rotation.y -= 0.001 + rotationBoost * 0.003
      const material = wire.material as THREE.MeshBasicMaterial
      material.color.set(hue)
      material.opacity = wireOpacity
    }

    // Two low-cost scan rings add the holographic language of the reference
    // UI without introducing a field of canvas sprites or post-processing.
    if (scanOuter) {
      const wave = Math.sin(t * (state === 'error' ? 5 : 1.6))
      scanOuter.rotation.z += 0.006 + rotationBoost * 0.01
      scanOuter.scale.setScalar(1 + wave * 0.025)
      const material = scanOuter.material as THREE.MeshBasicMaterial
      material.color.set(hue)
      material.opacity = scanStrength * (0.72 + (wave + 1) * 0.14)
    }
    if (scanInner) {
      const wave = Math.sin(t * (state === 'error' ? 7 : 2.1) + 1.7)
      scanInner.rotation.z -= 0.008 + rotationBoost * 0.006
      scanInner.rotation.y += 0.002
      scanInner.scale.setScalar(1 + wave * 0.04)
      const material = scanInner.material as THREE.MeshBasicMaterial
      material.color.set(hue)
      material.opacity = scanStrength * (0.5 + (wave + 1) * 0.18)
    }
  })

  return (
    <>
      {/* Orbital ring */}
      <points ref={ringRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[ring, 3]}
            count={ring.length / 3}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          color="#FFB020"
          size={0.008}
          transparent
          opacity={0.3}
          blending={THREE.AdditiveBlending}
          sizeAttenuation
        />
      </points>

      {/* Restrained holographic shells: a few geometries, no sprite field. */}
      <mesh ref={wireRef} rotation={[0.35, 0.2, 0.1]}>
        <icosahedronGeometry args={[2.18, 2]} />
        <meshBasicMaterial
          color="#FFB020"
          wireframe
          transparent
          opacity={0.08}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <mesh ref={scanOuterRef} rotation={[1.15, 0.15, 0]}>
        <ringGeometry args={[2.52, 2.54, 96]} />
        <meshBasicMaterial
          color="#FFB020"
          transparent
          opacity={0.08}
          side={THREE.DoubleSide}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <mesh ref={scanInnerRef} rotation={[0.55, 0.7, 0.4]}>
        <ringGeometry args={[1.92, 1.935, 80]} />
        <meshBasicMaterial
          color="#FFB020"
          transparent
          opacity={0.06}
          side={THREE.DoubleSide}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>

      {/* Outer shell */}
      <points ref={shellRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[shell, 3]}
            count={shell.length / 3}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          color="#8A4A0F"
          size={0.012}
          transparent
          opacity={0.18}
          blending={THREE.AdditiveBlending}
          sizeAttenuation
        />
      </points>

      {/* Core particles */}
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[particles.positions, 3]}
            count={particles.positions.length / 3}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          color="#FFB020"
          size={0.016}
          transparent
          opacity={0.96}
          blending={THREE.AdditiveBlending}
          sizeAttenuation
        />
      </points>
    </>
  )
}

export default function Sphere({
  state = 'idle',
  agent = null,
  audioLevel = 0
}: {
  state?: ActivityState
  agent?: ActivityAgent
  audioLevel?: number
}) {
  return (
    <Canvas dpr={[1, 1.5]} camera={{ position: [0, 0, 5.1], fov: 50 }}>
      <ambientLight intensity={0.18} />
      <pointLight position={[0, 0, 5]} intensity={4} color="#FFB020" />
      <ParticleCore state={state} agent={agent} audioLevel={audioLevel} />
    </Canvas>
  )
}
