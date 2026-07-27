import { FileImage, ImagePlus, Trash2 } from 'lucide-react'
import type { AttachmentMeta } from '../types'

interface AttachmentUploadProps {
  attachments: AttachmentMeta[]
  previews: Record<string, string>
  error?: string
  disabled?: boolean
  onUpload: (files: FileList) => void
  onRemove: (id: string) => void
}

const formatSize = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`

export function AttachmentUpload({
  attachments,
  previews,
  error,
  disabled = false,
  onUpload,
  onRemove,
}: AttachmentUploadProps) {
  return (
    <div className="attachment-area">
      <label className="upload-dropzone">
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          disabled={disabled}
          onChange={(event) => {
            if (event.target.files) onUpload(event.target.files)
            event.target.value = ''
          }}
        />
        <ImagePlus size={24} />
        <strong>选择界面截图</strong>
        <span>PNG、JPEG 或 WebP，单张不超过 5 MB，最多 3 张</span>
      </label>
      {error ? <p className="field-error">{error}</p> : null}
      {attachments.length > 0 ? (
        <div className="attachment-list">
          {attachments.map((attachment) => (
            <figure key={attachment.id} className="attachment-preview">
              {previews[attachment.id] ? (
                <img src={previews[attachment.id]} alt={attachment.name} />
              ) : (
                <div className="attachment-placeholder">
                  <FileImage size={28} />
                </div>
              )}
              <figcaption>
                <span>
                  <strong>{attachment.name}</strong>
                  <small>{formatSize(attachment.size)}</small>
                </span>
                <button type="button" disabled={disabled} onClick={() => onRemove(attachment.id)} aria-label={`删除 ${attachment.name}`}>
                  <Trash2 size={16} />
                </button>
              </figcaption>
            </figure>
          ))}
        </div>
      ) : null}
    </div>
  )
}
