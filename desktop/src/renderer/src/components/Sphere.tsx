import { Canvas, useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'

type SphereState = 'idle' | 'listening' | 'thinking' | 'waiting'

function ParticleCore({ state, audioLevel }: { state: SphereState; audioLevel: number }) {
  const pointsRef = useRef<THREE.Points>(null)
  const shellRef = useRef<THREE.Points>(null)
  const ringRef = useRef<THREE.Points>(null)

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

  // Orbital ring particles — IRIS-style equatorial ring
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

    // Audio-reactive energy boost — key IRIS feature
    const audioBoost = audioLevel * 0.6

    let energy = 0.08 + audioBoost
    let rotationBoost = 0.06
    let hue = '#2ee6c9'

    if (state === 'listening') {
      energy = 0.2 + audioBoost * 1.5
      rotationBoost = 0.11
      hue = '#5cf0ff'
    } else if (state === 'thinking') {
      energy = 0.32 + audioBoost
      rotationBoost = 0.22
      hue = '#7bffd2'
    } else if (state === 'waiting') {
      energy = 0.14 + audioBoost
      rotationBoost = 0.09
      hue = '#79ffc7'
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
          color="#10b981"
          size={0.008}
          transparent
          opacity={0.3}
          blending={THREE.AdditiveBlending}
          sizeAttenuation
        />
      </points>

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
          color="#1d7d70"
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
          color="#2ee6c9"
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
  audioLevel = 0
}: {
  state?: SphereState
  audioLevel?: number
}) {
  return (
    <Canvas camera={{ position: [0, 0, 5.1], fov: 50 }}>
      <ambientLight intensity={0.18} />
      <pointLight position={[0, 0, 5]} intensity={4} color="#5cf0ff" />
      <ParticleCore state={state} audioLevel={audioLevel} />
    </Canvas>
  )
}
