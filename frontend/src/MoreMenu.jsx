import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'

// Phone-width menu for the secondary header actions, so the sticky header
// stays one row. `items` is [{ label, onClick }].
export default function MoreMenu({ items }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('pointerdown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  return (
    <div ref={ref} className="relative sm:hidden">
      <Button variant="outline" size="sm" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        More ▾
      </Button>
      {open && (
        <div role="menu" className="absolute right-0 top-full mt-2 min-w-44 rounded-lg border border-border bg-card p-1 shadow-lg z-30">
          {items.map((item) => (
            <button
              key={item.label}
              role="menuitem"
              className="block w-full text-left px-3 py-2 text-sm rounded-md hover:bg-secondary focus-visible:bg-secondary outline-none"
              onClick={() => { setOpen(false); item.onClick() }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
