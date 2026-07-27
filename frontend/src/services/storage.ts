import type { AttachmentRecord, SurveyDraft } from '../types'

export const DRAFT_STORAGE_KEY = 'dml-detailed-survey:draft-v1'
export const MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024
export const MAX_ATTACHMENTS = 3
export const ACCEPTED_ATTACHMENT_TYPES = ['image/png', 'image/jpeg', 'image/webp']
const DATABASE_NAME = 'dml-detailed-survey-v1'
const ATTACHMENT_STORE = 'attachments'
const OLD_KEYS = [
  'dml-v4-survey-draft',
  'dml-survey-current-version',
  'dml-survey-draft',
  'dml-v4-survey-version',
]

export function clearLegacyBrowserData() {
  for (const key of OLD_KEYS) localStorage.removeItem(key)
  for (let index = localStorage.length - 1; index >= 0; index -= 1) {
    const key = localStorage.key(index)
    if (key?.startsWith('dml-survey-version:')) localStorage.removeItem(key)
  }
  if ('indexedDB' in window) indexedDB.deleteDatabase('dml-v4-survey')
}

export function loadDraft(): SurveyDraft | null {
  try {
    const parsed = JSON.parse(localStorage.getItem(DRAFT_STORAGE_KEY) ?? 'null') as SurveyDraft | null
    return parsed?.schemaVersion === 1 ? parsed : null
  } catch {
    localStorage.removeItem(DRAFT_STORAGE_KEY)
    return null
  }
}

export function saveDraft(draft: SurveyDraft) {
  localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify({ ...draft, updatedAt: new Date().toISOString() }))
}

export function clearDraft() {
  localStorage.removeItem(DRAFT_STORAGE_KEY)
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(ATTACHMENT_STORE, { keyPath: 'id' })
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function transaction<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>) {
  const database = await openDatabase()
  return new Promise<T>((resolve, reject) => {
    const tx = database.transaction(ATTACHMENT_STORE, mode)
    const request = action(tx.objectStore(ATTACHMENT_STORE))
    let result!: T
    request.onsuccess = () => { result = request.result }
    tx.oncomplete = () => { database.close(); resolve(result) }
    tx.onerror = () => { database.close(); reject(tx.error) }
    tx.onabort = () => { database.close(); reject(tx.error) }
  })
}

export const getAttachments = () => transaction<AttachmentRecord[]>('readonly', (store) => store.getAll())
export const removeAttachment = (id: string) => transaction('readwrite', (store) => store.delete(id))
export const clearAttachments = () => transaction('readwrite', (store) => store.clear())

export async function putAttachments(records: AttachmentRecord[]): Promise<void> {
  if (records.length === 0) return
  const database = await openDatabase()
  await new Promise<void>((resolve, reject) => {
    const tx = database.transaction(ATTACHMENT_STORE, 'readwrite')
    const store = tx.objectStore(ATTACHMENT_STORE)
    records.forEach((record) => store.put(record))
    tx.oncomplete = () => { database.close(); resolve() }
    tx.onerror = () => { database.close(); reject(tx.error) }
    tx.onabort = () => { database.close(); reject(tx.error) }
  })
}

export async function pruneAttachments(expectedIds: ReadonlySet<string>): Promise<void> {
  const database = await openDatabase()
  await new Promise<void>((resolve, reject) => {
    const tx = database.transaction(ATTACHMENT_STORE, 'readwrite')
    const store = tx.objectStore(ATTACHMENT_STORE)
    const keys = store.getAllKeys()
    keys.onsuccess = () => {
      keys.result.forEach((key) => {
        if (!expectedIds.has(String(key))) store.delete(key)
      })
    }
    tx.oncomplete = () => { database.close(); resolve() }
    tx.onerror = () => { database.close(); reject(tx.error) }
    tx.onabort = () => { database.close(); reject(tx.error) }
  })
}

export function attachmentRecordsForDraft(records: AttachmentRecord[], attachmentIds: ReadonlySet<string>) {
  return records.filter((record) => attachmentIds.has(record.id))
}

export function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

export function validateAttachmentFiles(files: File[], existingCount: number): string | null {
  if (existingCount + files.length > MAX_ATTACHMENTS) return '最多上传 3 张截图。'
  if (files.some((file) => !ACCEPTED_ATTACHMENT_TYPES.includes(file.type))) return '仅支持 PNG、JPEG 和 WebP 图片。'
  const oversized = files.find((file) => file.size > MAX_ATTACHMENT_SIZE)
  return oversized ? `${oversized.name} 超过 5 MB，请压缩后重试。` : null
}
