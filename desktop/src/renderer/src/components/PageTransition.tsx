/**
 * GSAP-powered page transition wrapper.
 * Wraps view content with cinematic enter/exit animations.
 */

import { useRef, useEffect } from 'react'
import gsap from 'gsap'
import { useGSAP } from '@gsap/react'

gsap.registerPlugin(useGSAP)

interface PageTransitionProps {
  children: React.ReactNode
  id: string  // unique key per view — triggers transition on change
  className?: string
}

export default function PageTransition({ children, id, className = '' }: PageTransitionProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const prevId = useRef(id)

  useEffect(() => {
    if (prevId.current !== id && containerRef.current) {
      const el = containerRef.current
      // Cinematic entrance — fade + scale + slight upward slide
      gsap.fromTo(
        el,
        {
          opacity: 0,
          scale: 0.97,
          y: 14,
          filter: 'blur(6px)',
        },
        {
          opacity: 1,
          scale: 1,
          y: 0,
          filter: 'blur(0px)',
          duration: 0.45,
          ease: 'power3.out',
        }
      )
      prevId.current = id
    }
  }, [id])

  // Initial mount animation
  useGSAP(() => {
    if (!containerRef.current) return
    gsap.fromTo(
      containerRef.current,
      { opacity: 0, y: 20, scale: 0.98 },
      { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: 'power2.out' }
    )
  }, { scope: containerRef })

  return (
    <div ref={containerRef} className={`h-full ${className}`}>
      {children}
    </div>
  )
}
