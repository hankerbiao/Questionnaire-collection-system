import type { SurveyVersionData } from '../types'

export type SurveyVersionConfig = SurveyVersionData

export interface SubmissionRow {
  id: string
  submissionId: string
  surveyId: string
  surveyVersionId: string
  submittedAt: string
  roles: string[]
  pages: string[]
  roleNames: Record<string, string>
  pageNames: Record<string, string>
  attachmentCount: number
  authType?: 'external' | 'anonymous'
  externalUserId?: string
  username?: string
}

export interface SubmissionFilterCatalog {
  roles: Array<{ id: string; label: string }>
  pages: Array<{ id: string; name: string }>
}

export interface SubmissionSection {
  id: string
  label: string
  value: unknown
  pageNames?: Record<string, string>
  attachments?: Array<{ id: string; attachmentId: string; name: string; type: string; size: number }>
}

export interface SubmissionDetail extends SubmissionRow {
  sections: SubmissionSection[]
  payload: Record<string, unknown>
}
