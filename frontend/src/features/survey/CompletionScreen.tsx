import { CheckCircle2 } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect, useRef } from 'react'

const CELEBRATION_PIECES = [
  { x: -64, y: -48, rotate: -38, color: '#e0a72f', delay: 0.12 },
  { x: -78, y: 5, rotate: 24, color: '#287c68', delay: 0.18 },
  { x: -52, y: 58, rotate: 68, color: '#d9614b', delay: 0.24 },
  { x: -8, y: -72, rotate: -18, color: '#3b7bbf', delay: 0.16 },
  { x: 48, y: -58, rotate: 42, color: '#d9614b', delay: 0.22 },
  { x: 76, y: -4, rotate: 76, color: '#e0a72f', delay: 0.14 },
  { x: 58, y: 54, rotate: -54, color: '#3b7bbf', delay: 0.2 },
  { x: 8, y: 74, rotate: 32, color: '#287c68', delay: 0.26 },
] as const

export function CompletionScreen({ submissionId, onRestart, onViewMine }: { submissionId: string; onRestart: () => void; onViewMine?: () => void }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => headingRef.current?.focus(), [])

  return (
    <motion.main className="completion" aria-labelledby="completion-title" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.28 }}>
      <div className="completion-visual" aria-hidden="true">
        <motion.span className="completion-pulse" initial={{ opacity: 0.45, scale: 0.55 }} animate={{ opacity: 0, scale: 1.55 }} transition={{ duration: 0.9, delay: 0.08, ease: 'easeOut' }} />
        {CELEBRATION_PIECES.map((piece, index) => (
          <motion.span className="completion-piece" data-testid="celebration-piece" key={`${piece.x}-${piece.y}`} style={{ backgroundColor: piece.color }} initial={{ x: 0, y: 0, rotate: 0, opacity: 0, scale: 0 }} animate={{ x: piece.x, y: piece.y, rotate: piece.rotate, opacity: [0, 1, 1, 0], scale: [0, 1, 1, 0.8] }} transition={{ duration: 0.85, delay: piece.delay + index * 0.01, ease: 'easeOut' }} />
        ))}
        <motion.div className="completion-check" initial={{ opacity: 0, scale: 0.55, rotate: -10 }} animate={{ opacity: 1, scale: 1, rotate: 0 }} transition={{ type: 'spring', stiffness: 260, damping: 17, delay: 0.08 }}>
          <CheckCircle2 size={58} strokeWidth={1.8} />
        </motion.div>
      </div>
      <motion.h1 id="completion-title" ref={headingRef} tabIndex={-1} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.2 }}>问卷已提交</motion.h1>
      <motion.p initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.27 }}>感谢你提供具体、可落地的 DML 使用反馈。</motion.p>
      <motion.code initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3, delay: 0.34 }}>{submissionId}</motion.code>
      <motion.button type="button" className="primary-button" onClick={onRestart} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.38 }}>填写另一份</motion.button>
      {onViewMine ? <motion.button type="button" className="secondary-button" onClick={onViewMine} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.44 }}>查看我的提交</motion.button> : null}
    </motion.main>
  )
}
