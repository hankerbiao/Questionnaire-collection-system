import type { PageDefinition, PageReview } from '../../types'

export function ScorePicker({ value, onChange, label }: { value?: number; onChange: (score: number) => void; label: string }) {
  return (
    <div className="score-field">
      <span>{label}</span>
      <div className="score-picker" role="radiogroup" aria-label={label}>
        {Array.from({ length: 10 }, (_, index) => index + 1).map((score) => (
          <button type="button" key={score} className={value === score ? 'selected' : ''} aria-pressed={value === score} onClick={() => onChange(score)}>
            {score}
          </button>
        ))}
      </div>
      <small>1 很差 · 10 很好</small>
    </div>
  )
}

interface TextAreaProps {
  label: string
  value: string
  onChange: (value: string) => void
  maxLength?: number
  placeholder?: string
  required?: boolean
  rows?: number
}

export function TextArea({ label, value, onChange, maxLength = 2000, placeholder, required, rows = 5 }: TextAreaProps) {
  return (
    <label className="text-field">
      <span>{label} {required ? <b>必填</b> : <small>选填</small>}</span>
      <textarea rows={rows} maxLength={maxLength} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
      <i>{value.length} / {maxLength}</i>
    </label>
  )
}

export function ReviewEditor({ page, review, onChange }: { page: PageDefinition; review: PageReview; onChange: (review: PageReview) => void }) {
  const features = page.features.filter((feature) => feature.enabled).sort((a, b) => a.order - b.order)
  return (
    <div className="review-editor">
      <ScorePicker value={review.overallScore} label={`${page.name} 使用体验综合打分`} onChange={(overallScore) => onChange({ ...review, overallScore })} />
      <section className="feature-ratings" aria-labelledby="feature-ratings-title">
        <header><h2 id="feature-ratings-title">功能点评分</h2><p>请评价这个页面当前启用的每项功能。</p></header>
        {features.map((feature) => (
          <div className="feature-row" key={feature.id}>
            <div><strong>{feature.name}</strong>{feature.description ? <small>{feature.description}</small> : null}</div>
            <ScorePicker value={review.featureScores[feature.id]} label={`${feature.name}评分`} onChange={(score) => onChange({ ...review, featureScores: { ...review.featureScores, [feature.id]: score } })} />
          </div>
        ))}
      </section>
      <div className="two-column-fields">
        <TextArea label="优点" required value={review.strengths} onChange={(strengths) => onChange({ ...review, strengths })} placeholder="哪些设计真正帮你提高了效率？" />
        <TextArea label="槽点" required value={review.painPoints} onChange={(painPoints) => onChange({ ...review, painPoints })} placeholder="哪些操作最费时间、最容易出错？" />
      </div>
    </div>
  )
}
