import type { AttachmentRecord, SurveyDraft } from '../types'

export const DRAFT_STORAGE_KEY = 'dml-detailed-survey:draft-v1'
export const ANONYMOUS_OWNER = 'anonymous'
export const MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024
export const MAX_ATTACHMENTS = 3
export const ACCEPTED_ATTACHMENT_TYPES = ['image/png', 'image/jpeg', 'image/webp']
const DATABASE_NAME = 'dml-detailed-survey-v1'
const ATTACHMENT_STORE = 'attachments'
const PENDING_DRAFT_CLAIM_KEY = 'dml-detailed-survey:pending-draft-claim'
const DRAFT_CLAIM_MAX_AGE = 10 * 60 * 1000
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

const draftStorageKey = (ownerKey: string) => ownerKey === ANONYMOUS_OWNER
  ? DRAFT_STORAGE_KEY
  : `${DRAFT_STORAGE_KEY}:${encodeURIComponent(ownerKey)}`

export const ownerKeyForUser = (externalUserId?: string) => externalUserId
  ? `user:${externalUserId}`
  : ANONYMOUS_OWNER

export function loadDraft(ownerKey = ANONYMOUS_OWNER): SurveyDraft | null {
  const storageKey = draftStorageKey(ownerKey)
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey) ?? 'null') as SurveyDraft | null
    return parsed?.schemaVersion === 1 ? parsed : null
  } catch {
    localStorage.removeItem(storageKey)
    return null
  }
}

export function saveDraft(draft: SurveyDraft, ownerKey = ANONYMOUS_OWNER) {
  localStorage.setItem(draftStorageKey(ownerKey), JSON.stringify({ ...draft, updatedAt: new Date().toISOString() }))
}

export function clearDraft(ownerKey = ANONYMOUS_OWNER) {
  localStorage.removeItem(draftStorageKey(ownerKey))
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

type StoredAttachment = AttachmentRecord & { ownerKey?: string }
const attachmentOwner = (record: StoredAttachment) => record.ownerKey ?? ANONYMOUS_OWNER

export const getAttachments = async (ownerKey = ANONYMOUS_OWNER) => {
  const records = await transaction<StoredAttachment[]>('readonly', (store) => store.getAll())
  return records.filter((record) => attachmentOwner(record) === ownerKey)
}

export async function removeAttachment(id: string, ownerKey = ANONYMOUS_OWNER) {
  const record = await transaction<StoredAttachment | undefined>('readonly', (store) => store.get(id))
  if (record && attachmentOwner(record) === ownerKey) {
    await transaction('readwrite', (store) => store.delete(id))
  }
}

export async function clearAttachments(ownerKey = ANONYMOUS_OWNER): Promise<void> {
  const records = await getAttachments(ownerKey)
  await Promise.all(records.map((record) => transaction('readwrite', (store) => store.delete(record.id))))
}

export async function putAttachments(records: AttachmentRecord[], ownerKey = ANONYMOUS_OWNER): Promise<void> {
  if (records.length === 0) return
  const database = await openDatabase()
  await new Promise<void>((resolve, reject) => {
    const tx = database.transaction(ATTACHMENT_STORE, 'readwrite')
    const store = tx.objectStore(ATTACHMENT_STORE)
    records.forEach((record) => store.put({ ...record, ownerKey }))
    tx.oncomplete = () => { database.close(); resolve() }
    tx.onerror = () => { database.close(); reject(tx.error) }
    tx.onabort = () => { database.close(); reject(tx.error) }
  })
}

export async function pruneAttachments(expectedIds: ReadonlySet<string>, ownerKey = ANONYMOUS_OWNER): Promise<void> {
  const database = await openDatabase()
  await new Promise<void>((resolve, reject) => {
    const tx = database.transaction(ATTACHMENT_STORE, 'readwrite')
    const store = tx.objectStore(ATTACHMENT_STORE)
    const records = store.getAll()
    records.onsuccess = () => {
      records.result.forEach((record: StoredAttachment) => {
        if (attachmentOwner(record) === ownerKey && !expectedIds.has(record.id)) store.delete(record.id)
      })
    }
    tx.oncomplete = () => { database.close(); resolve() }
    tx.onerror = () => { database.close(); reject(tx.error) }
    tx.onabort = () => { database.close(); reject(tx.error) }
  })
}

export function markPendingAnonymousDraftClaim(draftId: string) {
  localStorage.setItem(PENDING_DRAFT_CLAIM_KEY, JSON.stringify({ draftId, createdAt: Date.now() }))
}

export async function claimPendingAnonymousDraft(ownerKey: string): Promise<'none' | 'claimed' | 'conflict'> {
  if (ownerKey === ANONYMOUS_OWNER) return 'none'
  try {
    const pending = JSON.parse(localStorage.getItem(PENDING_DRAFT_CLAIM_KEY) ?? 'null') as {
      draftId?: string
      createdAt?: number
    } | null
    const draft = loadDraft(ANONYMOUS_OWNER)
    if (!pending?.draftId || !pending.createdAt || Date.now() - pending.createdAt > DRAFT_CLAIM_MAX_AGE) {
      localStorage.removeItem(PENDING_DRAFT_CLAIM_KEY)
      return 'none'
    }
    if (!draft || draft.id !== pending.draftId) {
      localStorage.removeItem(PENDING_DRAFT_CLAIM_KEY)
      return 'none'
    }
    if (loadDraft(ownerKey)) {
      localStorage.removeItem(PENDING_DRAFT_CLAIM_KEY)
      return 'conflict'
    }
    saveDraft(draft, ownerKey)
    try {
      const records = await getAttachments(ANONYMOUS_OWNER)
      await putAttachments(records, ownerKey)
    } catch (error) {
      clearDraft(ownerKey)
      throw error
    }
    clearDraft(ANONYMOUS_OWNER)
    localStorage.removeItem(PENDING_DRAFT_CLAIM_KEY)
    return 'claimed'
  } catch (error) {
    if (error instanceof SyntaxError) localStorage.removeItem(PENDING_DRAFT_CLAIM_KEY)
    throw error
  }
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
