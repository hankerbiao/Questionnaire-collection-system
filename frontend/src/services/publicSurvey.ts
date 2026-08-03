import type { PublishedSurvey } from '../types'
import { API_BASE } from '../shared/apiConfig'
const CURRENT_CACHE = 'dml-detailed-survey:current'

export async function loadPublishedSurvey(): Promise<PublishedSurvey | null> {
  try {
    const response = await fetch(`${API_BASE}/surveys/current`)
    if (response.status >= 400 && response.status < 500) {
      localStorage.removeItem(CURRENT_CACHE)
      return null
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const survey = await response.json() as PublishedSurvey
    if (survey.closedAt) localStorage.removeItem(CURRENT_CACHE)
    else localStorage.setItem(CURRENT_CACHE, JSON.stringify(survey))
    return survey
  } catch {
    try {
      return JSON.parse(localStorage.getItem(CURRENT_CACHE) ?? 'null') as PublishedSurvey | null
    } catch {
      return null
    }
  }
}
