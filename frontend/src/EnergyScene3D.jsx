import { useEffect, useRef } from 'react'
import * as THREE from 'three'

// A small 3D site: solar array (under a sun that follows the output), battery cabinet
// (level = charge), transmission tower (dark in a power cut), diesel genset (shakes and
// smokes when running) and the house (windows lit by the power it gets). Glowing
// particles flow along conduits, faster and denser with more kW. Numbers are HTML labels
// pinned to each model, so they stay crisp and readable.

const COLOR = { solar: 0xffb648, battery: 0x4fd8c4, grid: 0xff6b5c, genset: 0xb99cff }
const HIDDEN = new THREE.Vector3(0, -100, 0)

// Where each model sits (x right, y up, z towards the viewer) and where its label is pinned.
const POS = {
  solar: new THREE.Vector3(-5.9, 0, -1.3),
  tower: new THREE.Vector3(-1.9, 0, -3.3),
  battery: new THREE.Vector3(-1.6, 0, 0.7),
  genset: new THREE.Vector3(-3.2, 0, 3.3),
  house: new THREE.Vector3(3.9, 0, 0.3),
}
const ANCHOR = {
  solar: new THREE.Vector3(-5.9, 2.45, -1.7),
  grid: new THREE.Vector3(-1.9, 3.75, -3.3),
  battery: new THREE.Vector3(-1.6, 2.05, 0.7),
  genset: new THREE.Vector3(-3.2, 1.35, 3.3),
  house: new THREE.Vector3(3.9, 2.8, 0.3),
}

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
  const tubeMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.08, depthWrite: false })
  const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 64, 0.035, 8, false), tubeMat)
  const N = 40
  const geom = new THREE.BufferGeometry()
  geom.setAttribute('position', new THREE.BufferAttribute(new Float32Array(N * 3), 3))
  const mat = new THREE.PointsMaterial({ color, size: 0.3, map: sprite, transparent: true, depthWrite: false,
    blending: THREE.AdditiveBlending, sizeAttenuation: true })
  const dots = new THREE.Points(geom, mat)
  dots.frustumCulled = false
  scene.add(tube, dots)
  return { curve, tubeMat, dots, mat, N, phase: Math.random(), shown: 0 }
}

function updateFlow(flow, kw, dt) {
  const active = kw > 0.05
  flow.tubeMat.opacity += ((active ? 0.32 : 0.06) - flow.tubeMat.opacity) * Math.min(1, dt * 4)
  const count = active ? Math.min(flow.N, Math.round(5 + kw * 5)) : 0
  flow.phase = (flow.phase + dt * (0.1 + Math.min(kw, 8) * 0.035)) % 1
  flow.mat.size = 0.22 + Math.min(kw, 6) * 0.035
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

const fmt = (kw) => `${Math.abs(kw).toFixed(1)} kW`

export default function EnergyScene3D({ solarGenKw = 0, solarKw = 0, batteryKw = 0, gridKw = 0, exportKw = 0, gensetKw = 0,
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
    gridOk: gridAvailable, soc: socPct, served: loadKw > 0 ? Math.max(0, 1 - unservedKw / loadKw) : 1,
  }

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
    if (g) g.style.opacity = gridAvailable && gensetKw <= 0.05 ? '0.55' : '1'
  }, [solarGenKw, exportKw, socPct, batteryKw, gridAvailable, gridKw, gensetKw, loadKw, unservedKw])

  useEffect(() => {
    const mount = mountRef.current
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x000000, 0)
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.domElement.setAttribute('aria-hidden', 'true')
    mount.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(34, 16 / 9, 0.1, 100)
    const lookAt = new THREE.Vector3(-0.9, 1.25, -0.2)
    const camBase = new THREE.Vector3(0.6, 6.0, 12.4)

    const hemi = new THREE.HemisphereLight(0xcfe0ff, 0x16181b, 0.7)
    const sunLight = new THREE.DirectionalLight(0xfff0d6, 1.2)
    sunLight.position.set(-2, 10, 4)
    sunLight.castShadow = true
    sunLight.shadow.mapSize.set(1024, 1024)
    Object.assign(sunLight.shadow.camera, { left: -9, right: 9, top: 9, bottom: -9 })
    const fill = new THREE.DirectionalLight(0x8fb4ff, 0.35)
    fill.position.set(6, 4, 8)
    scene.add(hemi, sunLight, fill)

    const ground = new THREE.Mesh(new THREE.CircleGeometry(10, 64), new THREE.MeshStandardMaterial({ color: 0x15171a, roughness: 1 }))
    ground.rotation.x = -Math.PI / 2
    ground.receiveShadow = true
    const grid = new THREE.GridHelper(20, 40, 0x2a2e33, 0x1d2024)
    grid.position.y = 0.005
    scene.add(ground, grid)

    const textures = [cellTexture(), glowSprite(), grilleTexture()]
    const [cells, sprite, grille] = textures
    const solar = buildSolar(cells)
    solar.group.position.copy(POS.solar)
    solar.group.scale.setScalar(1.3)
    solar.group.rotation.y = 0.25
    const battery = buildBattery()
    battery.group.position.copy(POS.battery)
    battery.group.rotation.y = 0.15
    const tower = buildTower()
    tower.group.position.copy(POS.tower)
    tower.group.rotation.y = 0.2
    const genset = buildGenset(grille)
    genset.group.position.copy(POS.genset)
    genset.group.rotation.y = 0.35
    const house = buildHouse()
    house.group.position.copy(POS.house)
    house.group.rotation.y = -0.45
    scene.add(solar.group, battery.group, tower.group, genset.group, house.group)

    const sunMat = new THREE.SpriteMaterial({ map: sprite, color: 0xffd27a, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })
    const sun = new THREE.Sprite(sunMat)
    sun.position.set(-7.6, 4.1, -3.4)
    const sunCore = new THREE.Mesh(new THREE.SphereGeometry(0.28, 24, 24), new THREE.MeshBasicMaterial({ color: 0xffe2a3 }))
    sunCore.position.copy(sun.position)
    scene.add(sun, sunCore)

    const V = (x, y, z) => new THREE.Vector3(x, y, z)
    const houseIn = V(2.85, 0.8, 0.5)
    const flows = {
      solarLoad: makeFlow(scene, [V(-4.2, 1.2, -1.0), V(-2.0, 2.4, -1.4), V(1.0, 2.0, -0.6), houseIn], COLOR.solar, sprite),
      batteryLoad: makeFlow(scene, [V(-1.0, 0.9, 0.8), V(0.6, 1.3, 0.8), V(1.8, 1.0, 0.7), houseIn], COLOR.battery, sprite),
      gridLoad: makeFlow(scene, [V(-1.6, 1.8, -2.9), V(0.2, 2.2, -2.2), V(1.8, 1.5, -0.8), houseIn], COLOR.grid, sprite),
      gensetLoad: makeFlow(scene, [V(-2.5, 0.7, 3.2), V(-0.4, 1.0, 2.8), V(1.5, 1.0, 1.8), houseIn], COLOR.genset, sprite),
      solarBattery: makeFlow(scene, [V(-4.4, 0.9, -0.6), V(-3.2, 1.5, 0.1), V(-2.2, 1.2, 0.6)], COLOR.solar, sprite),
      solarGrid: makeFlow(scene, [V(-5.6, 1.5, -2.1), V(-4.2, 2.6, -3.1), V(-2.3, 2.3, -3.3)], COLOR.solar, sprite),
      gensetBattery: makeFlow(scene, [V(-2.9, 0.9, 2.8), V(-2.4, 1.4, 1.8), V(-1.9, 1.1, 1.0)], COLOR.genset, sprite),
    }

    const smokeN = 14
    const smokeGeom = new THREE.BufferGeometry()
    smokeGeom.setAttribute('position', new THREE.BufferAttribute(new Float32Array(smokeN * 3), 3))
    const smokeMat = new THREE.PointsMaterial({ color: 0x8a8f96, size: 0.35, map: sprite, transparent: true, opacity: 0.35, depthWrite: false })
    const smoke = new THREE.Points(smokeGeom, smokeMat)
    smoke.frustumCulled = false
    scene.add(smoke)
    const exhaustWorld = genset.exhaust.clone().applyMatrix4(new THREE.Matrix4().makeRotationY(0.35)).add(POS.genset)

    const cur = { solarGen: 0, soc: target.current.soc, gridOk: 1, genset: 0, served: 1 }
    const labelPos = new THREE.Vector3()
    let width = 1, height = 1, running = true, frame = 0, last = performance.now(), time = 0

    const resize = () => {
      width = mount.clientWidth
      height = mount.clientHeight
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      // Narrow screens: step back and aim a little right so the whole site (house included) fits.
      const narrow = camera.aspect < 1.35
      const back = narrow ? 1.5 : camera.aspect < 1.6 ? 1.15 : 1
      camBase.set(narrow ? 1.6 : 0.6 * back, 6.0 * back, 12.4 * back)
      lookAt.set(narrow ? -0.2 : -0.9, 1.25, -0.2)
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

      const sunFrac = Math.min(1, cur.solarGen / 8)
      solar.panelMats.forEach((m) => { m.emissiveIntensity = 0.3 + sunFrac * 0.6 })
      sun.visible = sunCore.visible = cur.solarGen > 0.05
      sun.scale.setScalar(1.2 + sunFrac * 2.4)
      sunMat.opacity = 0.35 + sunFrac * 0.6
      sunLight.intensity = 0.45 + sunFrac * 1.5
      hemi.intensity = 0.55 + sunFrac * 0.45
      hemi.color.setHex(sunFrac > 0.05 ? 0xcfe0ff : 0x7d8cb8)

      const lvl = Math.max(0.02, cur.soc / 100)
      battery.level.scale.y = lvl
      battery.level.position.y = 0.8 - 0.55 + (1.1 * lvl) / 2
      battery.levelMat.emissiveIntensity = 0.5 + (t.solarBattery + t.gensetBattery > 0.05 ? 0.6 + 0.3 * Math.sin(time * 5) : 0.2)

      tower.steel.color.setScalar(0.2 + cur.gridOk * 0.46)
      tower.wireMat.opacity = 0.15 + cur.gridOk * 0.55
      tower.beacon.visible = !t.gridOk && Math.sin(time * 6) > 0

      const on = cur.genset > 0.05
      genset.lampMat.color.setHex(on ? 0x6bff8a : 0x333333)
      genset.body.position.set(on && !reduced ? Math.sin(time * 60) * 0.008 : 0, on && !reduced ? Math.cos(time * 53) * 0.006 : 0, 0)
      const sArr = smokeGeom.attributes.position.array
      for (let i = 0; i < smokeN; i++) {
        const age = (time * 0.6 + i / smokeN) % 1
        const p = on ? exhaustWorld.clone().add(new THREE.Vector3(Math.sin(i * 1.7 + time) * 0.1 * age, age * 1.6, age * 0.35)) : HIDDEN
        sArr[i * 3] = p.x
        sArr[i * 3 + 1] = p.y
        sArr[i * 3 + 2] = p.z
      }
      smokeGeom.attributes.position.needsUpdate = true
      smokeMat.opacity = on ? 0.3 : 0

      house.windowMats.forEach((m, i) => {
        const flicker = cur.served < 0.99 && !reduced ? (Math.sin(time * 9 + i * 2) > 0.2 ? 1 : 0.35) : 1
        m.emissiveIntensity = (0.15 + 1.5 * cur.served) * flicker
      })

      for (const [key, flow] of Object.entries(flows)) updateFlow(flow, t[key] || 0, reduced ? 0 : dt)

      if (!reduced) {
        camera.position.set(camBase.x + Math.sin(time * 0.12) * 0.7, camBase.y + Math.sin(time * 0.09) * 0.15, camBase.z)
      } else {
        camera.position.copy(camBase)
      }
      camera.lookAt(lookAt)
      renderer.render(scene, camera)

      for (const [key, anchor] of Object.entries(ANCHOR)) {
        const el = labelRefs.current[key]
        if (!el) continue
        labelPos.copy(anchor).project(camera)
        el.style.transform = `translate(-50%, -100%) translate(${(labelPos.x * 0.5 + 0.5) * width}px, ${(-labelPos.y * 0.5 + 0.5) * height}px)`
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
      {label('solar', 'Solar', 'var(--solar)')}
      {label('battery', 'Battery', 'var(--battery)')}
      {label('grid', 'Grid', 'var(--grid)')}
      {label('genset', 'Diesel genset', 'var(--genset)')}
      {label('house', 'Load', 'var(--foreground)')}
    </div>
  )
}
