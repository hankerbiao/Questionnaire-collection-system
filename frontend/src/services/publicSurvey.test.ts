import { expect, it, vi } from 'vitest'
import type { PublishedSurvey } from '../types'
import { loadPublishedSurvey } from './publicSurvey'

const survey: PublishedSurvey = {
  versionId: 'v1', surveyKey: 'dml-v4', version: 1, status: 'published', revision: 1,
  title: '问卷', description: '', roles: [], pages: [],
}

it('loads and caches the current published survey', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(survey), { status: 200 })))
  await expect(loadPublishedSurvey()).resolves.toEqual(survey)
  expect(JSON.parse(localStorage.getItem('dml-detailed-survey:current') ?? 'null')).toEqual(survey)
})
