import { Component } from 'react'

// WebGL can be missing (old phones, locked-down PCs, graphics acceleration off). Anything
// drawn with three.js must check first and must never take the page down with it.
export function hasWebGL() {
  try {
    const c = document.createElement('canvas')
    return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')))
  } catch {
    return false
  }
}

// Renders `fallback` (or nothing) instead of crashing the page if a child throws.
export class FallbackBoundary extends Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? (this.props.fallback ?? null) : this.props.children }
}
