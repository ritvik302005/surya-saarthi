"use client"
/*! Wave Background by Kain Xu (https://21st.dev/@xubohuah/components/wave-background),
 * inspired by Antoine Wodniack. Adapted for Surya Saarthi.
 *
 * MIT License
 *
 * Copyright (c) Kain Xu
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */
import { useEffect, useRef } from "react"
import { createNoise2D } from "simplex-noise"

export function Waves({ className = "", strokeColor = "#4fd8c4", backgroundColor = "transparent", pointerSize = 0.5 }) {
  const containerRef = useRef(null)
  const svgRef = useRef(null)
  const mouseRef = useRef({ x: -10, y: 0, lx: 0, ly: 0, sx: 0, sy: 0, v: 0, vs: 0, a: 0, set: false })
  const pathsRef = useRef([])
  const linesRef = useRef([])
  const noiseRef = useRef(null)
  const rafRef = useRef(null)
  const boundingRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || !svgRef.current) return
    noiseRef.current = createNoise2D()
    setSize()
    setLines()

    window.addEventListener('resize', onResize)
    window.addEventListener('mousemove', onMouseMove)
    containerRef.current.addEventListener('touchmove', onTouchMove, { passive: false })
    rafRef.current = requestAnimationFrame(tick)

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('mousemove', onMouseMove)
      containerRef.current?.removeEventListener('touchmove', onTouchMove)
    }
  }, [])

  const setSize = () => {
    if (!containerRef.current || !svgRef.current) return
    boundingRef.current = containerRef.current.getBoundingClientRect()
    const { width, height } = boundingRef.current
    svgRef.current.style.width = `${width}px`
    svgRef.current.style.height = `${height}px`
  }

  const setLines = () => {
    if (!svgRef.current || !boundingRef.current) return
    const { width, height } = boundingRef.current
    linesRef.current = []
    pathsRef.current.forEach((path) => path.remove())
    pathsRef.current = []

    const xGap = 8, yGap = 8
    const oWidth = width + 200, oHeight = height + 30
    const totalLines = Math.ceil(oWidth / xGap)
    const totalPoints = Math.ceil(oHeight / yGap)
    const xStart = (width - xGap * totalLines) / 2
    const yStart = (height - yGap * totalPoints) / 2

    for (let i = 0; i < totalLines; i++) {
      const points = []
      for (let j = 0; j < totalPoints; j++) {
        points.push({ x: xStart + xGap * i, y: yStart + yGap * j, wave: { x: 0, y: 0 }, cursor: { x: 0, y: 0, vx: 0, vy: 0 } })
      }
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path')
      path.classList.add('a__line', 'js-line')
      path.setAttribute('fill', 'none')
      path.setAttribute('stroke', strokeColor)
      path.setAttribute('stroke-width', '1')
      svgRef.current.appendChild(path)
      pathsRef.current.push(path)
      linesRef.current.push(points)
    }
  }

  const onResize = () => { setSize(); setLines() }
  const onMouseMove = (e) => updateMousePosition(e.pageX, e.pageY)
  const onTouchMove = (e) => { e.preventDefault(); const t = e.touches[0]; updateMousePosition(t.clientX, t.clientY) }

  const updateMousePosition = (x, y) => {
    if (!boundingRef.current) return
    const mouse = mouseRef.current
    mouse.x = x - boundingRef.current.left
    mouse.y = y - boundingRef.current.top + window.scrollY
    if (!mouse.set) { mouse.sx = mouse.x; mouse.sy = mouse.y; mouse.lx = mouse.x; mouse.ly = mouse.y; mouse.set = true }
    if (containerRef.current) {
      containerRef.current.style.setProperty('--x', `${mouse.sx}px`)
      containerRef.current.style.setProperty('--y', `${mouse.sy}px`)
    }
  }

  const movePoints = (time) => {
    const { current: lines } = linesRef, { current: mouse } = mouseRef, { current: noise } = noiseRef
    if (!noise) return
    lines.forEach((points) => {
      points.forEach((p) => {
        const move = noise((p.x + time * 0.008) * 0.003, (p.y + time * 0.003) * 0.002) * 8
        p.wave.x = Math.cos(move) * 12
        p.wave.y = Math.sin(move) * 6
        const dx = p.x - mouse.sx, dy = p.y - mouse.sy
        const d = Math.hypot(dx, dy)
        const l = Math.max(175, mouse.vs)
        if (d < l) {
          const s = 1 - d / l
          const f = Math.cos(d * 0.001) * s
          p.cursor.vx += Math.cos(mouse.a) * f * l * mouse.vs * 0.00035
          p.cursor.vy += Math.sin(mouse.a) * f * l * mouse.vs * 0.00035
        }
        p.cursor.vx += (0 - p.cursor.x) * 0.01
        p.cursor.vy += (0 - p.cursor.y) * 0.01
        p.cursor.vx *= 0.95
        p.cursor.vy *= 0.95
        p.cursor.x += p.cursor.vx
        p.cursor.y += p.cursor.vy
        p.cursor.x = Math.min(50, Math.max(-50, p.cursor.x))
        p.cursor.y = Math.min(50, Math.max(-50, p.cursor.y))
      })
    })
  }

  const moved = (point, withCursorForce = true) => ({
    x: point.x + point.wave.x + (withCursorForce ? point.cursor.x : 0),
    y: point.y + point.wave.y + (withCursorForce ? point.cursor.y : 0),
  })

  const drawLines = () => {
    const { current: lines } = linesRef, { current: paths } = pathsRef
    lines.forEach((points, lIndex) => {
      if (points.length < 2 || !paths[lIndex]) return
      const first = moved(points[0], false)
      let d = `M ${first.x} ${first.y}`
      for (let i = 1; i < points.length; i++) { const c = moved(points[i]); d += `L ${c.x} ${c.y}` }
      paths[lIndex].setAttribute('d', d)
    })
  }

  const tick = (time) => {
    const { current: mouse } = mouseRef
    mouse.sx += (mouse.x - mouse.sx) * 0.1
    mouse.sy += (mouse.y - mouse.sy) * 0.1
    const dx = mouse.x - mouse.lx, dy = mouse.y - mouse.ly
    const d = Math.hypot(dx, dy)
    mouse.v = d
    mouse.vs += (d - mouse.vs) * 0.1
    mouse.vs = Math.min(100, mouse.vs)
    mouse.lx = mouse.x
    mouse.ly = mouse.y
    mouse.a = Math.atan2(dy, dx)
    if (containerRef.current) {
      containerRef.current.style.setProperty('--x', `${mouse.sx}px`)
      containerRef.current.style.setProperty('--y', `${mouse.sy}px`)
    }
    movePoints(time)
    drawLines()
    rafRef.current = requestAnimationFrame(tick)
  }

  return (
    <div ref={containerRef} className={`waves-component relative overflow-hidden ${className}`}
      style={{ backgroundColor, position: 'absolute', top: 0, left: 0, margin: 0, padding: 0, width: '100%', height: '100%', overflow: 'hidden', '--x': '-0.5rem', '--y': '50%' }}>
      <svg ref={svgRef} className="block w-full h-full js-svg" xmlns="http://www.w3.org/2000/svg" />
      <div className="pointer-dot" style={{ position: 'absolute', top: 0, left: 0, width: `${pointerSize}rem`, height: `${pointerSize}rem`, background: strokeColor, borderRadius: '50%', transform: 'translate3d(calc(var(--x) - 50%), calc(var(--y) - 50%), 0)', willChange: 'transform' }} />
    </div>
  )
}