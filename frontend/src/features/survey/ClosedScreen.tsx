import { CalendarX2 } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect, useRef } from 'react'

export function ClosedScreen({ title, closedAt, canViewMine, onViewMine }: {
  title: string
  closedAt?: string | null
  canViewMine: boolean
  onViewMine: () => void
}) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => headingRef.current?.focus(), [])

  const closedText = closedAt ? new Date(closedAt).toLocaleString('zh-CN') : undefined

  return (
    <motion.main className="completion" aria-labelledby="closed-title" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.28 }}>
      <div className="completion-visual" aria-hidden="true">
        <motion.div className="closed-check" initial={{ opacity: 0, scale: 0.55, rotate: -10 }} animate={{ opacity: 1, scale: 1, rotate: 0 }} transition={{ type: 'spring', stiffness: 260, damping: 17, delay: 0.08 }}>
          <CalendarX2 size={56} strokeWidth={1.8} />
        </motion.div>
      </div>
      <motion.h1 id="closed-title" ref={headingRef} tabIndex={-1} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.2 }}>问卷收集已截止</motion.h1>
      <motion.p initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.27 }}>
        感谢你关注「{title}」。{closedText ? `本次收集已于 ${closedText} 结束，` : ''}暂不接受新的提交。
      </motion.p>
      {canViewMine ? (
        <motion.button type="button" className="primary-button" onClick={onViewMine} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: 0.38 }}>查看我的提交</motion.button>
      ) : null}
    </motion.main>
  )
}
