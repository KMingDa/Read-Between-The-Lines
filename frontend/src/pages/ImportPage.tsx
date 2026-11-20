import { useEffect, useRef, useState } from 'react'
import type { FormEvent, RefObject } from 'react'
import { flushSync } from 'react-dom'
import { Link } from 'react-router'
import type { ImportResult } from '../api/types'
import { chatFileProblem, fileAfter, uploadChat } from '../chatImport'
import type { DateOrderChoice, ImportOutcome } from '../chatImport'
import { dateOrderLabel, formatCount, formatDateRange, formatFileSize, sourceLabel } from '../format'

type Problem = Exclude<ImportOutcome, { kind: 'imported' } | { kind: 'cancelled' }>

type Phase =
  | { status: 'editing' }
  | { status: 'uploading' }
  | { status: 'problem'; problem: Problem }
  | { status: 'imported'; result: ImportResult; choice: DateOrderChoice }

const DATE_ORDER_CHOICES: { value: DateOrderChoice; label: string }[] = [
  { value: 'auto', label: 'Detect automatically (recommended)' },
  { value: 'day_first', label: dateOrderLabel('day_first') },
  { value: 'month_first', label: dateOrderLabel('month_first') },
]

const NO_FILE_MESSAGE = 'Choose your WhatsApp .txt export first.'

export function ImportPage() {
  const [file, setFile] = useState<File | null>(null)
  const [fileProblem, setFileProblem] = useState<string | null>(null) // from the browser's own checks
  const [choice, setChoice] = useState<DateOrderChoice>('auto')
  const [phase, setPhase] = useState<Phase>({ status: 'editing' })
  const inputRef = useRef<HTMLInputElement>(null)
  const summaryHeadingRef = useRef<HTMLHeadingElement>(null)
  const statusRef = useRef<HTMLDivElement>(null) // "Importing…" or what went wrong; focused when it appears
  const uploadRequest = useRef<AbortController | null>(null)

  // Leaving the page cancels an upload that is still running.
  useEffect(() => () => uploadRequest.current?.abort(), [])

  const uploading = phase.status === 'uploading'
  const problem = phase.status === 'problem' ? phase.problem : null

  // Without this, choosing the same file again would not fire "change".
  function clearFileInput() {
    if (inputRef.current) inputRef.current.value = ''
  }

  function chooseFile(chosen: File) {
    setFile(chosen)
    setFileProblem(chatFileProblem(chosen))
    setPhase({ status: 'editing' })
  }

  function removeFile() {
    setFile(null)
    setFileProblem(null)
    setPhase({ status: 'editing' })
    clearFileInput()
    inputRef.current?.focus()
  }

  function chooseDateOrder(value: DateOrderChoice) {
    setChoice(value)
    if (problem) setPhase({ status: 'editing' }) // that message was about the previous attempt
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (uploading) return // one upload at a time
    if (!file || fileProblem) {
      if (!file) setFileProblem(NO_FILE_MESSAGE)
      inputRef.current?.focus()
      return
    }
    const controller = new AbortController()
    uploadRequest.current = controller
    // The Import button is disabled while uploading, so focus moves to the message saying so.
    flushSync(() => setPhase({ status: 'uploading' }))
    statusRef.current?.focus()

    const outcome = await uploadChat(file, choice, controller.signal)
    if (outcome.kind === 'cancelled' || uploadRequest.current !== controller) return // nobody is waiting

    const kept = fileAfter(outcome, file)
    if (!kept) clearFileInput()
    if (outcome.kind === 'imported') {
      flushSync(() => {
        setFile(kept)
        setPhase({ status: 'imported', result: outcome.result, choice })
      })
      summaryHeadingRef.current?.focus() // the form has just been replaced by the summary
    } else {
      flushSync(() => {
        setFile(kept)
        setPhase({ status: 'problem', problem: outcome })
      })
      statusRef.current?.focus() // the message says what went wrong; the next Tab is the Import button
    }
  }

  function startOver() {
    flushSync(() => {
      setFile(null)
      setFileProblem(null)
      setChoice('auto')
      setPhase({ status: 'editing' })
    })
    inputRef.current?.focus()
  }

  return (
    <section className="workspace import-page" aria-labelledby="import-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">IMPORT</p>
          <h1 id="import-title">Import a WhatsApp chat</h1>
          <p>The chat is read once and saved as messages. The file itself is not kept.</p>
        </div>
      </div>

      {phase.status === 'imported' ? (
        <ImportSummary
          result={phase.result}
          choice={phase.choice}
          headingRef={summaryHeadingRef}
          onStartOver={startOver}
        />
      ) : (
        <form className="import-form" onSubmit={upload}>
          <p className="input-label">WhatsApp export</p>
          <p id="import-file-hint" className="import-hint">
            In WhatsApp, open the chat and choose Export chat, then Without media. Choose the .txt file it
            creates (up to 5 MB).
          </p>
          <div className="import-picker">
            <input
              ref={inputRef}
              id="import-file"
              className="visually-hidden import-file-input"
              type="file"
              accept=".txt,text/plain"
              disabled={uploading}
              aria-describedby={fileProblem ? 'import-file-hint import-file-problem' : 'import-file-hint'}
              aria-invalid={fileProblem ? true : undefined}
              onClick={(event) => {
                event.currentTarget.value = '' // choosing the same file again (e.g. once it changed) still counts
              }}
              onChange={(event) => {
                const chosen = event.currentTarget.files?.[0]
                if (chosen) chooseFile(chosen) // nothing chosen (the dialog was cancelled): keep the current file
              }}
            />
            <label htmlFor="import-file" className="secondary-button import-file-button">
              {file ? 'Choose a different file' : 'Choose a .txt file'}
            </label>
            {file && (
              <p className="import-chosen">
                <span className="import-chosen-name">{file.name}</span>
                <span className="import-chosen-size">{formatFileSize(file.size)}</span>
                <button
                  type="button"
                  className="text-button"
                  aria-label={`Remove ${file.name}`}
                  disabled={uploading}
                  onClick={removeFile}
                >
                  Remove
                </button>
              </p>
            )}
          </div>
          {fileProblem && (
            <p id="import-file-problem" className="import-problem" role="alert">
              {fileProblem}
            </p>
          )}

          <fieldset className="import-order" disabled={uploading} aria-describedby="import-order-hint">
            <legend className="input-label">Date order</legend>
            <p id="import-order-hint" className="import-hint">
              Leave this on automatic unless the dates come out wrong.
            </p>
            {DATE_ORDER_CHOICES.map(({ value, label }) => (
              <label key={value} className="import-order-option">
                <input
                  type="radio"
                  name="date-order"
                  value={value}
                  checked={choice === value}
                  onChange={() => chooseDateOrder(value)}
                />
                {label}
              </label>
            ))}
          </fieldset>

          {/* No live region or role="alert" on these: focus moves to them, and screen readers read them then */}
          {uploading && file && (
            <div ref={statusRef} className="status-card import-outcome" tabIndex={-1}>
              {`Importing “${file.name}”...`}
            </div>
          )}
          {problem && <ImportProblem problem={problem} messageRef={statusRef} />}

          <button type="submit" className="analyze-button" disabled={uploading}>
            {uploading ? 'Importing...' : problem?.kind === 'failed' ? 'Try again' : 'Import chat'}
          </button>
        </form>
      )}
    </section>
  )
}

function ImportProblem({ problem, messageRef }: { problem: Problem; messageRef: RefObject<HTMLDivElement | null> }) {
  return (
    <div ref={messageRef} className="status-card status-card-error import-outcome" tabIndex={-1}>
      <p>{problem.message}</p>
      {problem.kind === 'duplicate' && (
        <p>
          <Link to="/conversations">Go to your conversations</Link>
        </p>
      )}
    </div>
  )
}

type ImportSummaryProps = {
  result: ImportResult
  choice: DateOrderChoice
  headingRef: RefObject<HTMLHeadingElement | null>
  onStartOver: () => void
}

function ImportSummary({ result, choice, headingRef, onStartOver }: ImportSummaryProps) {
  const { conversation, detected_date_order: order, date_order_ambiguous: ambiguous, warnings } = result
  const skipped = result.skipped_line_count
  const how =
    choice !== 'auto'
      ? 'as you chose'
      : ambiguous
        ? 'assumed, because the dates fit either order'
        : 'detected from the dates'
  const otherOrder = order === 'day_first' ? 'month_first' : 'day_first'

  return (
    <div className="import-summary">
      <h2 ref={headingRef} tabIndex={-1}>
        {`Imported “${conversation.title}”`}
      </h2>
      <ul className="conversation-stats">
        <li>{formatCount(conversation.message_count, 'message')}</li>
        <li>{formatDateRange(conversation.first_message_at, conversation.last_message_at)}</li>
        <li>{`${sourceLabel(conversation.source)}: ${conversation.original_filename}`}</li>
      </ul>
      <p className="import-summary-text">
        Date order: {dateOrderLabel(order)}, {how}.
      </p>
      {ambiguous && (
        <p className="conversation-warning">
          <span aria-hidden="true">⚠ </span>
          If the dates look wrong, delete this conversation first, then import the file again choosing{' '}
          {dateOrderLabel(otherOrder)}.
        </p>
      )}
      {skipped > 0 && (
        <p className="import-summary-text">
          {formatCount(skipped, 'line')} could not be read as messages and {skipped === 1 ? 'was' : 'were'}{' '}
          skipped.
        </p>
      )}
      {warnings.length > 0 && (
        <div className="import-warnings">
          <h3>Notes from the import</h3>
          <ul>
            {warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="import-actions">
        <Link className="analyze-button" to={`/conversations/${conversation.id}`}>
          Open conversation
        </Link>
        <Link className="secondary-button" to="/conversations">
          View your conversations
        </Link>
        <button type="button" className="secondary-button" onClick={onStartOver}>
          Import another chat
        </button>
      </div>
    </div>
  )
}
