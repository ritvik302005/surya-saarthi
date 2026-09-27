import { useEffect, useRef } from 'react'
import * as THREE from 'three'

// The site seen from a fixed, gently tilted angle (no perspective, no camera motion):
// solar array, battery cabinet (level = charge), transmission tower (dark in a power cut),
// diesel genset (smokes when running) and the house (windows lit by the power it gets).
// The sky follows the simulated hour: bright by day, with the sun crossing it and glowing
// more with more solar output, dark with a moon at night. Dots flow along the lines,
// faster and denser with more kW. Numbers are HTML labels pinned to each model.

const COLOR = { solar: 0xffb648, battery: 0x4fd8c4, grid: 0xff6b5c, genset: 0xb99cff }
const HIDDEN = new THREE.Vector3(0, -100, 0)

// Where each model sits (x right, y up, z towards the viewer) and where its label is pinned.
const POS = {
  solar: new THREE.Vector3(-5.9, 0, -1.0),
  tower: new THREE.Vector3(-1.9, 0, -3.3),
  battery: new THREE.Vector3(-0.35, 0, 1.3),
  genset: new THREE.Vector3(-2.9, 0, 3.0),
  house: new THREE.Vector3(3.9, 0, 0.3),
}
const ANCHOR = {
  solar: new THREE.Vector3(-5.9, 2.3, -1.4),
  grid: new THREE.Vector3(-1.9, 3.75, -3.3),
  battery: new THREE.Vector3(-0.35, 2.0, 1.3),
  genset: new THREE.Vector3(-2.9, 0, 3.45),
  house: new THREE.Vector3(3.9, 2.8, 0.3),
}
// Labels drawn below their anchor instead of above (the genset's, so it never covers the battery's).
const BELOW = new Set(['genset'])

function canvasTexture(w, h, draw) {
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  draw(c.getContext('2d'), w, h)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 4
  return t
}

const cellTexture = () => canvasTexture(256, 168, (g, w, h) => {
  g.fillStyle = '#123a6e'
  g.fillRect(0, 0, w, h)
  const cols = 8, rows = 5
  for (let i = 0; i < cols; i++) {
    for (let j = 0; j < rows; j++) {
      const x = 6 + i * ((w - 12) / cols), y = 6 + j * ((h - 12) / rows)
      const grad = g.createLinearGradient(x, y, x + 28, y + 30)
      grad.addColorStop(0, '#3a7bd5')
      grad.addColorStop(1, '#1a4b8f')
      g.fillStyle = grad
      g.fillRect(x + 1.5, y + 1.5, (w - 12) / cols - 3, (h - 12) / rows - 3)
    }
  }
  g.strokeStyle = 'rgba(200,220,255,0.5)'
  g.lineWidth = 2
  g.strokeRect(2, 2, w - 4, h - 4)
})

const glowSprite = () => canvasTexture(64, 64, (g) => {
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32)
  grad.addColorStop(0, 'rgba(255,255,255,1)')
  grad.addColorStop(0.25, 'rgba(255,255,255,0.8)')
  grad.addColorStop(1, 'rgba(255,255,255,0)')
  g.fillStyle = grad
  g.fillRect(0, 0, 64, 64)
})

const grilleTexture = () => canvasTexture(128, 64, (g, w, h) => {
  g.fillStyle = '#556548'
  g.fillRect(0, 0, w, h)
  g.fillStyle = '#2a3324'
  for (let x = 8; x < w - 8; x += 9) g.fillRect(x, 10, 4, h - 20)
})

function beam(a, b, radius, material) {
  const dir = new THREE.Vector3().subVectors(b, a)
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, dir.length(), 6), material)
  mesh.position.copy(a).add(b).multiplyScalar(0.5)
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize())
  mesh.castShadow = true
  return mesh
}

function buildSolar(texture) {
  const group = new THREE.Group()
  const frame = new THREE.MeshStandardMaterial({ color: 0x9aa4ae, metalness: 0.7, roughness: 0.35 })
  const panelMats = []
  for (let r = 0; r < 2; r++) {
    for (let c = 0; c < 3; c++) {
      const top = new THREE.MeshStandardMaterial({ map: texture, emissiveMap: texture, emissive: 0xffffff, emissiveIntensity: 0.05, metalness: 0.4, roughness: 0.25 })
      panelMats.push(top)
      const side = new THREE.MeshStandardMaterial({ color: 0xc8ced4, metalness: 0.8, roughness: 0.3 })
      const panel = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.05, 0.66), [side, side, top, side, side, side])
      panel.position.set((c - 1) * 1.06, 0.55 + r * 0.34, -0.15 + r * -0.62)
      panel.rotation.x = 0.5   // cells tilted towards the viewer
      panel.castShadow = true
      group.add(panel)
    }
  }
  for (const x of [-1.55, 1.55]) {
    group.add(beam(new THREE.Vector3(x, 0, 0.12), new THREE.Vector3(x, 0.55, 0.12), 0.035, frame))
    group.add(beam(new THREE.Vector3(x, 0, -1.0), new THREE.Vector3(x, 1.2, -1.0), 0.035, frame))
  }
  return { group, panelMats }
}

function buildBattery() {
  const group = new THREE.Group()
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.1, 1.55, 0.75),
    new THREE.MeshStandardMaterial({ color: 0x46505c, metalness: 0.45, roughness: 0.4 }))
  body.position.y = 0.78
  body.castShadow = true
  group.add(body)
  const slot = new THREE.Mesh(new THREE.PlaneGeometry(0.34, 1.16), new THREE.MeshStandardMaterial({ color: 0x0c0f12 }))
  slot.position.set(0, 0.8, 0.376)
  group.add(slot)
  const levelMat = new THREE.MeshStandardMaterial({ color: COLOR.battery, emissive: COLOR.battery, emissiveIntensity: 0.9 })
  const level = new THREE.Mesh(new THREE.BoxGeometry(0.28, 1.1, 0.02), levelMat)
  level.position.set(0, 0.8, 0.385)
  group.add(level)
  for (let i = 1; i < 4; i++) {           // quarter marks
    const mark = new THREE.Mesh(new THREE.PlaneGeometry(0.34, 0.012), new THREE.MeshBasicMaterial({ color: 0x3c444d }))
    mark.position.set(0, 0.8 - 0.55 + i * 0.275, 0.397)
    group.add(mark)
  }
  const terminal = (x, color) => {
    const t = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.12, 16), new THREE.MeshStandardMaterial({ color, metalness: 0.4, roughness: 0.4 }))
    t.position.set(x, 1.62, 0)
    t.castShadow = true
    group.add(t)
  }
  terminal(-0.3, 0xd9534f)
  terminal(0.3, 0x2b2b2b)
  const vents = new THREE.MeshStandardMaterial({ color: 0x1f242a })
  for (let i = 0; i < 4; i++) {
    const v = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.9, 0.5), vents)
    v.position.set(0.56, 0.8, -0.2 + i * 0.13)
    group.add(v)
  }
  return { group, level, levelMat }
}

function buildTower() {
  const group = new THREE.Group()
  const steel = new THREE.MeshStandardMaterial({ color: 0xa8b0b8, metalness: 0.75, roughness: 0.35 })
  const H = 3.4, base = 0.48, top = 0.14
  const corner = (sx, sz, y) => {
    const s = base + (top - base) * (y / H)
    return new THREE.Vector3(sx * s, y, sz * s)
  }
  const corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]]
  for (const [sx, sz] of corners) group.add(beam(corner(sx, sz, 0), corner(sx, sz, H), 0.03, steel))
  for (let k = 0; k < 4; k++) {
    const y0 = (k * H) / 4, y1 = ((k + 1) * H) / 4
    for (let f = 0; f < 4; f++) {
      const [ax, az] = corners[f], [bx, bz] = corners[(f + 1) % 4]
      group.add(beam(corner(ax, az, y0), corner(bx, bz, y1), 0.013, steel))
      group.add(beam(corner(bx, bz, y0), corner(ax, az, y1), 0.013, steel))
    }
  }
  const tips = []
  for (const [y, w] of [[2.65, 0.95], [3.15, 0.7]]) {
    group.add(beam(new THREE.Vector3(-w, y, 0), new THREE.Vector3(w, y, 0), 0.03, steel))
    for (const x of [-w, w]) {
      const ins = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.22, 8), new THREE.MeshStandardMaterial({ color: 0x6d8fa3, roughness: 0.3 }))
      ins.position.set(x, y - 0.12, 0)
      group.add(ins)
      tips.push(new THREE.Vector3(x, y - 0.24, 0))
    }
  }
  const wireMat = new THREE.LineBasicMaterial({ color: 0x8b939b, transparent: true, opacity: 0.7 })
  for (const tip of tips) {
    const far = tip.clone().add(new THREE.Vector3(-4, 0.1, -1.6))
    const mid = tip.clone().lerp(far, 0.5).add(new THREE.Vector3(0, -0.45, 0))
    const curve = new THREE.QuadraticBezierCurve3(tip, mid, far)
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(24)), wireMat))
  }
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 12), new THREE.MeshBasicMaterial({ color: 0xff3b30 }))
  beacon.position.set(0, H + 0.1, 0)
  group.add(beacon)
  return { group, steel, wireMat, beacon }
}

function buildGenset(grille) {
  const group = new THREE.Group()
  const shell = new THREE.MeshStandardMaterial({ color: 0x5f7050, metalness: 0.35, roughness: 0.5 })
  const box = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.7, 0.66), [
    shell, shell, shell, shell,
    new THREE.MeshStandardMaterial({ map: grille, metalness: 0.4, roughness: 0.6 }), shell,
  ])
  box.position.y = 0.45
  box.castShadow = true
  const skid = new THREE.Mesh(new THREE.BoxGeometry(1.25, 0.1, 0.72), new THREE.MeshStandardMaterial({ color: 0x1d2024 }))
  skid.position.y = 0.05
  const panel = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.2, 0.04), new THREE.MeshStandardMaterial({ color: 0x15181b }))
  panel.position.set(0.35, 0.55, 0.35)
  const lampMat = new THREE.MeshBasicMaterial({ color: 0x333333 })
  const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.035, 10, 10), lampMat)
  lamp.position.set(0.35, 0.58, 0.38)
  const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.45, 12), new THREE.MeshStandardMaterial({ color: 0x55595e, metalness: 0.8, roughness: 0.3 }))
  pipe.position.set(-0.38, 1.0, -0.12)
  const body = new THREE.Group()
  body.add(box, panel, lamp, pipe)
  group.add(skid, body)
  return { group, body, lampMat, exhaust: new THREE.Vector3(-0.38, 1.25, -0.12) }
}

function buildHouse() {
  const group = new THREE.Group()
  const wall = new THREE.MeshStandardMaterial({ color: 0xd8d2c6, roughness: 0.85 })
  const body = new THREE.Mesh(new THREE.BoxGeometry(2.1, 1.35, 1.8), wall)
  body.position.y = 0.68
  body.castShadow = true
  body.receiveShadow = true
  group.add(body)
  const shape = new THREE.Shape()
  shape.moveTo(-1.2, 0)
  shape.lineTo(1.2, 0)
  shape.lineTo(0, 0.85)
  shape.lineTo(-1.2, 0)
  const roof = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, { depth: 2.0, bevelEnabled: false }),
    new THREE.MeshStandardMaterial({ color: 0x9a4a3a, roughness: 0.7 }))
  roof.position.set(0, 1.35, -1.0)
  roof.castShadow = true
  group.add(roof)
  const windowMats = []
  const addWindow = (x, y, z, ry = 0) => {
    const m = new THREE.MeshStandardMaterial({ color: 0x2a2418, emissive: 0xffc46b, emissiveIntensity: 0.1 })
    windowMats.push(m)
    const w = new THREE.Mesh(new THREE.PlaneGeometry(0.42, 0.38), m)
    w.position.set(x, y, z)
    w.rotation.y = ry
    group.add(w)
  }
  addWindow(-0.55, 0.85, 0.905)
  addWindow(0.55, 0.85, 0.905)
  addWindow(-1.055, 0.85, 0.2, -Math.PI / 2)
  addWindow(-1.055, 0.85, -0.45, -Math.PI / 2)
  const door = new THREE.Mesh(new THREE.PlaneGeometry(0.36, 0.7), new THREE.MeshStandardMaterial({ color: 0x5a3b28 }))
  door.position.set(0, 0.36, 0.905)
  group.add(door)
  return { group, windowMats }
}

function makeFlow(scene, points, color, sprite) {
  const curve = new THREE.CatmullRomCurve3(points)
  const tubeMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0, depthWrite: false })
  const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 64, 0.06, 8, false), tubeMat)
  const N = 30
  const geom = new THREE.BufferGeometry()
  geom.setAttribute('position', new THREE.BufferAttribute(new Float32Array(N * 3), 3))
  // Lighter dots moving along the line show which way the power flows (no additive glow,
  // so they read on a bright daytime background too).
  const dotColor = new THREE.Color(color).lerp(new THREE.Color(0xffffff), 0.6)
  const mat = new THREE.PointsMaterial({ color: dotColor, size: 0.3, map: sprite, transparent: true, depthWrite: false, sizeAttenuation: true })
  const dots = new THREE.Points(geom, mat)
  dots.frustumCulled = false
  scene.add(tube, dots)
  return { curve, tubeMat, dots, mat, N, phase: Math.random() }
}

function updateFlow(flow, kw, dt) {
  const active = kw > 0.05
  // Only flows that carry power are drawn, so the picture shows just what is happening now.
  flow.tubeMat.opacity += ((active ? 0.85 : 0) - flow.tubeMat.opacity) * Math.min(1, dt * 4 || 1)
  const count = active ? Math.min(flow.N, Math.round(4 + kw * 3)) : 0
  flow.phase = (flow.phase + dt * (0.1 + Math.min(kw, 8) * 0.03)) % 1
  const arr = flow.dots.geometry.attributes.position.array
  const p = new THREE.Vector3()
  for (let i = 0; i < flow.N; i++) {
    if (i < count) flow.curve.getPointAt((flow.phase + i / count) % 1, p)
    else p.copy(HIDDEN)
    arr[i * 3] = p.x
    arr[i * 3 + 1] = p.y
    arr[i * 3 + 2] = p.z
  }
  flow.dots.geometry.attributes.position.needsUpdate = true
}

// Sky by hour of day: [hour, top colour, horizon colour, daylight 0-1]. Colours are
// blended between these points, so the scene brightens through the morning and darkens at dusk.
const SKY = [
  [0, '#0b1026', '#1c2446', 0],
  [5, '#141b3d', '#2f3563', 0],
  [6.5, '#6c8fd0', '#ffc59a', 0.55],
  [9, '#4f9be6', '#cfe7fb', 1],
  [16, '#4f9be6', '#cfe7fb', 1],
  [18, '#6a7fc6', '#ffb07e', 0.5],
  [19.5, '#1a2350', '#46396a', 0.08],
  [21, '#0b1026', '#1c2446', 0],
  [24, '#0b1026', '#1c2446', 0],
]
const mixHex = (a, b, f) => '#' + new THREE.Color(a).lerp(new THREE.Color(b), f).getHexString()
function skyAt(hour) {
  const h = ((hour % 24) + 24) % 24
  let i = 0
  while (SKY[i + 1][0] <= h) i++
  const [h0, top0, low0, d0] = SKY[i]
  const [h1, top1, low1, d1] = SKY[i + 1]
  const f = (h - h0) / (h1 - h0)
  return { top: mixHex(top0, top1, f), low: mixHex(low0, low1, f), daylight: d0 + (d1 - d0) * f }
}

const GROUND_NIGHT = new THREE.Color(0x151a22)
const GROUND_DAY = new THREE.Color(0xd3dec4)
const SUNRISE = 6, SUNSET = 18.5

const fmt = (kw) => `${Math.abs(kw).toFixed(1)} kW`
const hh = (h) => `${String(Math.floor(h) % 24).padStart(2, '0')}:00`

export default function EnergyScene3D({ hour = 12, solarGenKw = 0, solarKw = 0, batteryKw = 0, gridKw = 0, exportKw = 0, gensetKw = 0,
                                        unservedKw = 0, gridAvailable = true, loadKw = 0, socPct = 50, loading }) {
  const mountRef = useRef(null)
  const labelRefs = useRef({})
  const target = useRef({})

  // Latest values for the animation loop (it reads these every frame).
  const charge = Math.max(0, -batteryKw)
  const chargeFromSolar = Math.min(charge, Math.max(0, solarGenKw - solarKw))
  target.current = {
    solarGen: solarGenKw, solarLoad: solarKw, solarBattery: chargeFromSolar, solarGrid: exportKw,
    batteryLoad: Math.max(0, batteryKw), gridLoad: gridKw, gensetBattery: charge - chargeFromSolar,
    gensetLoad: Math.max(0, gensetKw - (charge - chargeFromSolar)), genset: gensetKw,
    gridOk: gridAvailable, soc: socPct, served: loadKw > 0 ? Math.max(0, 1 - unservedKw / loadKw) : 1, hour,
  }
  const daylight = skyAt(hour).daylight
  const timeOfDay = daylight >= 0.9 ? 'day' : daylight < 0.1 ? 'night' : hour < 12 ? 'morning' : 'evening'

  // Label text (plain HTML, updated with the data).
  useEffect(() => {
    const set = (key, main, sub) => {
      const el = labelRefs.current[key]
      if (!el) return
      el.querySelector('[data-v]').textContent = main
      el.querySelector('[data-s]').textContent = sub
    }
    set('solar', fmt(solarGenKw), solarGenKw <= 0.05 ? 'no sun now' : exportKw > 0.05 ? `exporting ${fmt(exportKw)}` : 'generating')
    set('battery', `${Math.round(socPct)}%`, batteryKw < -0.05 ? `charging ${fmt(batteryKw)}` : batteryKw > 0.05 ? `supplying ${fmt(batteryKw)}` : 'idle')
    set('grid', gridAvailable ? fmt(gridKw) : 'Power cut', gridAvailable ? (gridKw > 0.05 ? 'buying' : 'not needed') : 'grid is off')
    set('genset', fmt(gensetKw), gensetKw > 0.05 ? 'running on diesel' : 'off')
    set('house', fmt(loadKw), unservedKw > 0.05 ? `${fmt(unservedKw)} not served` : 'all load powered')
    const g = labelRefs.current.genset
    if (g) g.style.opacity = gridAvailable && gensetKw <= 0.05 ? '0.6' : '1'
  }, [solarGenKw, exportKw, socPct, batteryKw, gridAvailable, gridKw, gensetKw, loadKw, unservedKw])

  useEffect(() => {
    const mount = mountRef.current
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x000000, 0)   // the sky is the container's CSS background
    renderer.domElement.setAttribute('aria-hidden', 'true')
    mount.appendChild(renderer.domElement)

    // A fixed, gently tilted view without perspective: the site reads like a clear
    // diagram, and nothing sways or zooms.
    const scene = new THREE.Scene()
    const camera = new THREE.OrthographicCamera(-10, 10, 5, -5, 0.1, 100)
    const TILT = 0.5                                   // radians above the horizontal
    const center = new THREE.Vector3(-0.7, 0, 0)
    camera.position.copy(center).add(new THREE.Vector3(0, Math.sin(TILT), Math.cos(TILT)).multiplyScalar(30))
    camera.lookAt(center)

    const hemi = new THREE.HemisphereLight(0xdfeaff, 0x3a3f35, 0.9)
    const sunLight = new THREE.DirectionalLight(0xfff0d6, 1.2)
    sunLight.position.set(-3, 10, 6)
    scene.add(hemi, sunLight)

    // Ground ends at z = -9: above that line is sky (the container background).
    const groundMat = new THREE.MeshBasicMaterial({ color: GROUND_DAY.clone() })   // flat colour, no shading
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(80, 40), groundMat)
    ground.rotation.x = -Math.PI / 2
    ground.position.z = 11
    scene.add(ground)

    const textures = [cellTexture(), glowSprite(), grilleTexture()]
    const [cells, sprite, grille] = textures
    const solar = buildSolar(cells)
    solar.group.position.copy(POS.solar)
    solar.group.scale.setScalar(1.2)
    solar.group.rotation.y = 0.15
    const battery = buildBattery()
    battery.group.position.copy(POS.battery)
    const tower = buildTower()
    tower.group.position.copy(POS.tower)
    tower.group.rotation.y = 0.15
    const genset = buildGenset(grille)
    genset.group.position.copy(POS.genset)
    genset.group.rotation.y = 0.2
    const house = buildHouse()
    house.group.position.copy(POS.house)
    house.group.rotation.y = -0.35
    scene.add(solar.group, battery.group, tower.group, genset.group, house.group)

    // Sun: crosses the sky from left (morning) to right (evening); its glow grows with solar output.
    const sunHaloMat = new THREE.SpriteMaterial({ map: sprite, color: 0xffd27a, transparent: true, depthWrite: false })
    const sunHalo = new THREE.Sprite(sunHaloMat)
    const sunCore = new THREE.Mesh(new THREE.CircleGeometry(0.42, 32), new THREE.MeshBasicMaterial({ color: 0xffe08a }))
    const moonMat = new THREE.MeshBasicMaterial({ color: 0xe8ecf5, transparent: true })
    const moon = new THREE.Mesh(new THREE.CircleGeometry(0.32, 32), moonMat)
    for (const m of [sunHalo, sunCore, moon]) m.renderOrder = -1
    scene.add(sunHalo, sunCore, moon)
    // Sky objects sit beyond the ground's far edge, facing the camera; skyPoint takes the
    // height on screen (the ground's far edge is at 9 x sin(TILT)).
    const skyPoint = (x, screenY) => new THREE.Vector3(x, (screenY - 11 * Math.sin(TILT)) / Math.cos(TILT), -11)
    sunCore.quaternion.copy(camera.quaternion)
    moon.quaternion.copy(camera.quaternion)

    const V = (x, y, z) => new THREE.Vector3(x, y, z)
    const houseIn = V(3.2, 0.8, 0.6)
    const flows = {
      solarLoad: makeFlow(scene, [V(-4.6, 1.1, -0.6), V(-2.2, 2.3, -1.2), V(1.2, 2.0, -0.4), houseIn], COLOR.solar, sprite),
      batteryLoad: makeFlow(scene, [V(0.3, 0.9, 1.4), V(1.4, 1.2, 1.3), V(2.4, 1.0, 1.0), houseIn], COLOR.battery, sprite),
      gridLoad: makeFlow(scene, [V(-1.4, 2.35, -3.2), V(0.6, 2.4, -2.3), V(2.3, 1.6, -0.8), houseIn], COLOR.grid, sprite),
      gensetLoad: makeFlow(scene, [V(-2.2, 0.7, 3.0), V(-0.4, 0.8, 3.0), V(1.8, 0.9, 2.2), houseIn], COLOR.genset, sprite),
      solarBattery: makeFlow(scene, [V(-4.4, 0.8, 0.0), V(-2.6, 1.3, 0.9), V(-0.9, 1.0, 1.3)], COLOR.solar, sprite),
      solarGrid: makeFlow(scene, [V(-5.4, 1.6, -1.8), V(-4.0, 2.6, -2.9), V(-2.4, 2.3, -3.3)], COLOR.solar, sprite),
      gensetBattery: makeFlow(scene, [V(-2.3, 0.9, 2.6), V(-1.5, 1.2, 2.0), V(-0.8, 1.0, 1.5)], COLOR.genset, sprite),
    }

    const smokeN = 10
    const smokeGeom = new THREE.BufferGeometry()
    smokeGeom.setAttribute('position', new THREE.BufferAttribute(new Float32Array(smokeN * 3), 3))
    const smokeMat = new THREE.PointsMaterial({ color: 0x8a8f96, size: 0.3, map: sprite, transparent: true, opacity: 0.3, depthWrite: false })
    const smoke = new THREE.Points(smokeGeom, smokeMat)
    smoke.frustumCulled = false
    scene.add(smoke)
    const exhaustWorld = genset.exhaust.clone().applyMatrix4(new THREE.Matrix4().makeRotationY(0.2)).add(POS.genset)

    const cur = { solarGen: 0, soc: target.current.soc, gridOk: 1, genset: 0, served: 1, hour: target.current.hour }
    const labelPos = new THREE.Vector3()
    let width = 1, height = 1, running = true, frame = 0, last = performance.now(), time = 0, skyKey = ''

    // Keep the whole site (x -8.2..6.2, screen height -3.4..6) in view at any aspect ratio;
    // spare height goes to the sky.
    const resize = () => {
      width = mount.clientWidth
      height = mount.clientHeight
      renderer.setSize(width, height, false)
      const aspect = width / height
      const w = Math.max(15.2, 9.9 * aspect)
      const h = w / aspect
      camera.left = -w / 2 - 0.3
      camera.right = w / 2 - 0.3
      const bottom = aspect < 1.4 ? -3.9 : -3.3   // room for the genset label under the genset
      camera.bottom = bottom
      camera.top = bottom + h
      camera.updateProjectionMatrix()
    }
    const ro = new ResizeObserver(resize)
    ro.observe(mount)
    resize()

    const step = (dt) => {
      const t = target.current
      const k = Math.min(1, dt * 3)
      cur.solarGen += (t.solarGen - cur.solarGen) * k
      cur.soc += (t.soc - cur.soc) * k
      cur.gridOk += ((t.gridOk ? 1 : 0) - cur.gridOk) * k
      cur.genset += (t.genset - cur.genset) * k
      cur.served += (t.served - cur.served) * k
      // Hour eases forward (23 -> 0 wraps instead of running backwards).
      let dh = t.hour - cur.hour
      if (dh < -12) dh += 24
      if (dh > 12) dh -= 24
      cur.hour = (cur.hour + dh * Math.min(1, dt * 2) + 24) % 24

      const sky = skyAt(cur.hour)
      const key = sky.top + sky.low
      if (key !== skyKey) {
        skyKey = key
        mount.style.background = `linear-gradient(to bottom, ${sky.top} 0%, ${sky.low} 58%)`
      }
      const day = sky.daylight
      groundMat.color.copy(GROUND_NIGHT).lerp(GROUND_DAY, day)
      hemi.intensity = 0.35 + day * 0.75
      sunLight.intensity = 0.15 + day * 1.2

      // Sun arc (morning left, evening right); brighter glow with more solar output.
      const sunFrac = Math.min(1, cur.solarGen / 7)
      const arc = (cur.hour - SUNRISE) / (SUNSET - SUNRISE)
      const up = arc > 0 && arc < 1
      const sunPos = skyPoint(-9 + arc * 17, 4.7 + Math.sin(Math.PI * Math.min(1, Math.max(0, arc))) * 1.3)
      sunCore.position.copy(sunPos)
      sunHalo.position.copy(sunPos)
      sunCore.visible = sunHalo.visible = up
      sunHalo.scale.setScalar(1.4 + sunFrac * 2.2)
      sunHaloMat.opacity = 0.3 + sunFrac * 0.6
      moon.visible = !up
      moon.position.copy(skyPoint(5.5, 5.8))
      moonMat.opacity = 1 - day

      solar.panelMats.forEach((m) => { m.emissiveIntensity = 0.05 + sunFrac * 0.35 })

      const lvl = Math.max(0.02, cur.soc / 100)
      battery.level.scale.y = lvl
      battery.level.position.y = 0.8 - 0.55 + (1.1 * lvl) / 2
      battery.levelMat.emissiveIntensity = t.solarBattery + t.gensetBattery > 0.05 && !reduced ? 0.8 + 0.3 * Math.sin(time * 5) : 0.7

      tower.steel.color.setScalar(0.25 + cur.gridOk * 0.4)
      tower.wireMat.opacity = 0.15 + cur.gridOk * 0.6
      tower.beacon.visible = !t.gridOk && (reduced || Math.sin(time * 6) > 0)

      const on = cur.genset > 0.05
      genset.lampMat.color.setHex(on ? 0x3ddc6a : 0x333333)
      const sArr = smokeGeom.attributes.position.array
      for (let i = 0; i < smokeN; i++) {
        const age = (time * 0.5 + i / smokeN) % 1
        const p = on ? exhaustWorld.clone().add(new THREE.Vector3(Math.sin(i * 1.7) * 0.08 * age, age * 1.2, 0)) : HIDDEN
        sArr[i * 3] = p.x
        sArr[i * 3 + 1] = p.y
        sArr[i * 3 + 2] = p.z
      }
      smokeGeom.attributes.position.needsUpdate = true
      smokeMat.opacity = on ? 0.3 : 0

      // Windows: lit by the power the house gets (clearest at night); flicker if load goes unserved.
      house.windowMats.forEach((m, i) => {
        const flicker = cur.served < 0.99 && !reduced ? (Math.sin(time * 9 + i * 2) > 0.2 ? 1 : 0.35) : 1
        m.emissiveIntensity = (0.1 + (1.6 - day * 0.9) * cur.served) * flicker
      })

      for (const [key, flow] of Object.entries(flows)) updateFlow(flow, t[key] || 0, reduced ? 0 : dt)

      renderer.render(scene, camera)

      for (const [key, anchor] of Object.entries(ANCHOR)) {
        const el = labelRefs.current[key]
        if (!el) continue
        labelPos.copy(anchor).project(camera)
        el.style.transform = `translate(-50%, ${BELOW.has(key) ? '6px' : '-100%'}) `
          + `translate(${(labelPos.x * 0.5 + 0.5) * width}px, ${(-labelPos.y * 0.5 + 0.5) * height}px)`
      }
    }

    const loop = (now) => {
      frame = requestAnimationFrame(loop)
      const dt = Math.min(0.1, (now - last) / 1000)
      last = now
      if (!running || document.hidden) return
      time += dt
      step(dt)
    }
    const io = new IntersectionObserver(([e]) => { running = e.isIntersecting })
    io.observe(mount)
    if (reduced) {
      // No continuous animation: redraw a few times so values settle, then on each data change.
      const settle = () => { for (let i = 0; i < 30; i++) step(0.1) }
      settle()
      mount.__redraw = settle
    } else {
      frame = requestAnimationFrame(loop)
    }

    return () => {
      cancelAnimationFrame(frame)
      ro.disconnect()
      io.disconnect()
      scene.traverse((obj) => {
        obj.geometry?.dispose()
        const mats = Array.isArray(obj.material) ? obj.material : obj.material ? [obj.material] : []
        mats.forEach((m) => m.dispose())
      })
      textures.forEach((t) => t.dispose())
      renderer.dispose()
      mount.removeChild(renderer.domElement)
    }
  }, [])

  // Reduced motion: redraw once when the data changes.
  useEffect(() => { mountRef.current?.__redraw?.() })

  const label = (key, name, color) => (
    <div ref={(el) => { labelRefs.current[key] = el }} className="scene-label" style={{ '--c': color }} aria-hidden="true">
      <span className="scene-label-name">{name}</span>
      <span className="scene-label-value" data-v />
      <span className="scene-label-sub" data-s />
    </div>
  )

  return (
    <div className={`energy-scene ${loading ? 'computing' : ''}`} ref={mountRef}>
      <div className="scene-time" aria-hidden="true">{timeOfDay === 'night' ? '☾' : '☀'} {hh(hour)} · {timeOfDay}</div>
      {label('solar', 'Solar', 'var(--solar)')}
      {label('battery', 'Battery', 'var(--battery)')}
      {label('grid', 'Grid', 'var(--grid)')}
      {label('genset', 'Diesel genset', 'var(--genset)')}
      {label('house', 'Load', 'var(--foreground)')}
    </div>
  )
}
