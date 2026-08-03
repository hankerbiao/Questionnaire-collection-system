export interface RoleDefinition {
  id: string
  label: string
  description: string
}

export interface PageFeatureDefinition {
  id: string
  name: string
  description: string
  order: number
  enabled: boolean
}

export interface PageDefinition {
  id: string
  name: string
  category: string
  order: number
  enabled: boolean
  features: PageFeatureDefinition[]
}

export type SurveyStatus = 'draft' | 'published' | 'archived'

export interface SurveyVersionData {
  versionId: string
  surveyKey: string
  version: number
  status: SurveyStatus
  revision: number
  title: string
  description: string
  roles: RoleDefinition[]
  pages: PageDefinition[]
  publishedAt?: string
  closedAt?: string | null
}

export interface PublishedSurvey extends SurveyVersionData {
  status: 'published' | 'archived'
}

export interface AttachmentMeta {
  id: string
  questionId: 'issue-evidence'
  name: string
  type: string
  size: number
}

export interface AttachmentRecord extends AttachmentMeta {
  dataUrl: string
}

export interface PageReview {
  pageId: string
  overallScore?: number
  featureScores: Record<string, number>
  strengths: string
  painPoints: string
}

export interface FavoritePageReview {
  pageId: string
  winningReason: string
  improvement: string
}

export interface OtherPageReview {
  pageId: string
  status: 'unused' | 'rated'
  overallScore?: number
  strengths: string
  painPoints: string
}

export interface SurveyDraft {
  schemaVersion: 1
  id: string
  surveyVersionId: string
  createdAt: string
  updatedAt: string
  currentStep: number
  roleIds: string[]
  roleContext: string
  topPageIds: string[]
  topPageReviews: PageReview[]
  favoritePageReview: FavoritePageReview
  otherPageReviews: OtherPageReview[]
  issueDescription: string
  attachments: AttachmentMeta[]
  finalFeedback: string
}

export interface SurveySubmission {
  schemaVersion: 1
  surveyId: string
  surveyVersionId: string
  startedAt: string
  submittedAt: string
  profile: { roleIds: string[]; roleContext: string }
  topPageIds: string[]
  topPageReviews: Array<Required<PageReview>>
  favoritePageReview: FavoritePageReview
  otherPageReviews: OtherPageReview[]
  issueEvidence: { description: string; attachments: AttachmentMeta[] }
  finalFeedback: string
}

export interface ExternalUser {
  externalUserId: string
  username: string
}

export interface UserSession {
  authenticated: boolean
  user: ExternalUser | null
  ssoEnabled: boolean
  loginUrl: string | null
}

export interface MySubmissionRow {
  id: string
  submissionId: string
  surveyId: string
  surveyVersionId: string
  submittedAt: string
  updatedAt?: string | null
  version: number
  revisionCount: number
  attachmentCount: number
}

export interface SubmissionAttachment {
  id: string
  attachmentId: string
  name: string
  type: string
  size: number
  available?: boolean
}

export interface SubmissionRevision {
  index: number
  editedAt: string
  payload: SurveySubmission
  attachments: SubmissionAttachment[]
}

export interface MySubmissionDetail extends MySubmissionRow {
  payload: SurveySubmission
  attachments: SubmissionAttachment[]
  revisions: SubmissionRevision[]
  surveyClosed: boolean
}
