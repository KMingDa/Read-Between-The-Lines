// The rules of the chat import page, kept out of the component so they can be unit-tested.
import { ApiError } from './api/client.ts'
import { importChat, MAX_IMPORT_BYTES } from './api/conversations.ts'
import { isConflict, requestErrorMessage } from './api/errors.ts'
import type { DateOrder, ImportResult } from './api/types.ts'
import { formatFileSize } from './format.ts'

/** The date-order options on the page: 'auto' lets the backend detect the order from the file. */
export type DateOrderChoice = 'auto' | DateOrder

export const UNREADABLE_FILE_MESSAGE =
  'The chosen file could not be read. It may have been moved or changed since you chose it. Choose it again.'

export type ImportOutcome =
  | { kind: 'imported'; result: ImportResult }
  | { kind: 'duplicate'; message: string } // 409: this account already has this chat
  | { kind: 'rejected'; message: string } // 413 or 422: the file itself cannot be imported
  | { kind: 'unreadable'; message: string } // the browser could not read the chosen file
  | { kind: 'failed'; message: string } // connection, server or sign-in trouble: worth trying again
  | { kind: 'cancelled' } // aborted, e.g. the page was left: nothing to show

/** What the backend is told: nothing for Auto, so that it detects the order itself. */
export function dateOrderForUpload(choice: DateOrderChoice): DateOrder | null {
  return choice === 'auto' ? null : choice
}

/** Why this file cannot be imported, or null. Only what the browser sees cheaply is checked here,
 *  by the backend's own rules for names and sizes; the backend checks the content itself. */
export function chatFileProblem(file: Pick<File, 'name' | 'size'>): string | null {
  if (!file.name.toLowerCase().endsWith('.txt')) {
    return `“${file.name}” is not a .txt file. Export the chat from WhatsApp without media, and choose the .txt file.`
  }
  if (file.size === 0) return `“${file.name}” is empty.`
  if (file.size > MAX_IMPORT_BYTES) return `“${file.name}” is ${formatFileSize(file.size)}; the limit is 5 MB.`
  return null
}

/** The file to keep chosen after an upload: kept for another try; dropped after a success (the form
 *  starts over) and when it could not be read (it must be chosen again). */
export function fileAfter(outcome: ImportOutcome, file: File | null): File | null {
  return outcome.kind === 'imported' || outcome.kind === 'unreadable' ? null : file
}

/** Read the chosen file, then upload it. Never throws: every result is an outcome to show. */
export async function uploadChat(file: File, choice: DateOrderChoice, signal: AbortSignal): Promise<ImportOutcome> {
  // Read it here first: fetch fails in the same way for a lost connection and for a file that was
  // moved or changed after it was chosen, and the two need different advice.
  const bytes = await readAll(file)
  if (signal.aborted) return { kind: 'cancelled' }
  if (bytes === null || bytes.byteLength !== file.size) {
    return { kind: 'unreadable', message: UNREADABLE_FILE_MESSAGE } // a different size: the file changed
  }
  const copy = new File([bytes], file.name, { type: file.type, lastModified: file.lastModified })

  try {
    const result = await importChat(copy, { dateOrder: dateOrderForUpload(choice), signal })
    return signal.aborted ? { kind: 'cancelled' } : { kind: 'imported', result }
  } catch (error) {
    if (signal.aborted) return { kind: 'cancelled' } // whatever the error says
    const message = requestErrorMessage(error)
    if (isConflict(error)) return { kind: 'duplicate', message }
    if (error instanceof ApiError && (error.status === 413 || error.status === 422)) {
      return { kind: 'rejected', message }
    }
    return { kind: 'failed', message }
  }
}

async function readAll(file: File): Promise<ArrayBuffer | null> {
  try {
    return await file.arrayBuffer()
  } catch {
    return null // e.g. NotReadableError: moved, deleted or changed after it was chosen
  }
}
