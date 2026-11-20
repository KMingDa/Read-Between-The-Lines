import { useCallback, useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { Link, useLocation, useNavigate } from 'react-router'
import { deleteConversation, listConversations } from '../api/conversations'
import { isNotFound, requestErrorMessage } from '../api/errors'
import type { ConversationSummary } from '../api/types'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { noticeFromLocationState } from '../conversationView'
import { dateOrderLabel, formatCount, formatDateRange, formatInstant, sourceLabel } from '../format'

type ListState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'loaded'; conversations: ConversationSummary[] }

type Deletion = { conversation: ConversationSummary; busy: boolean; error: string | null }

export function ConversationsPage() {
  const [list, setList] = useState<ListState>({ status: 'loading' })
  const [deletion, setDeletion] = useState<Deletion | null>(null)
  const [notice, setNotice] = useState<string | null>(null) // announced by the status region
  const headingRef = useRef<HTMLHeadingElement>(null)
  const loadRequest = useRef<AbortController | null>(null)
  const deleteRequest = useRef<AbortController | null>(null)
  const location = useLocation()
  const navigate = useNavigate()

  // Only the newest load may update the page: starting one cancels the one before.
  const load = useCallback((announce: boolean) => {
    loadRequest.current?.abort()
    const controller = new AbortController()
    loadRequest.current = controller
    listConversations({ signal: controller.signal }).then(
      (conversations) => {
        if (controller.signal.aborted) return
        setList({ status: 'loaded', conversations })
        if (announce) setNotice(`${formatCount(conversations.length, 'conversation')} loaded.`)
      },
      (error: unknown) => {
        if (controller.signal.aborted) return // cancelled, whatever the error says
        // After a normal 401 the client signs out and this page is replaced by /login in the same
        // update, so this error is only seen if the page stays (the sign-in changed in another tab).
        setList({ status: 'error', message: requestErrorMessage(error) })
      },
    )
  }, [])

  useEffect(() => {
    load(false) // the first load is not announced: the page has only just opened
    return () => {
      loadRequest.current?.abort()
      deleteRequest.current?.abort()
    }
  }, [load])

  // Arriving from a conversation that was just deleted: announce the notice it passed, focus the
  // heading, and drop the notice from this history entry, so that a reload does not repeat it.
  useEffect(() => {
    const arrived = noticeFromLocationState(location.state)
    if (arrived === null) return
    // Set after mount on purpose: a status region that already holds its text when the page opens
    // is not announced, so this is not state that could be derived during render.
    // oxlint-disable-next-line react/set-state-in-effect
    setNotice(arrived)
    headingRef.current?.focus()
    navigate(`${location.pathname}${location.search}${location.hash}`, { replace: true, state: null })
  }, [location, navigate])

  function retry() {
    headingRef.current?.focus() // the Try again button is about to be replaced
    setNotice(null) // so the result is announced even when its text repeats
    setList({ status: 'loading' })
    load(true)
  }

  function askToDelete(conversation: ConversationSummary, button: HTMLButtonElement) {
    button.focus() // some browsers do not focus a clicked button; Cancel returns focus here
    setNotice(null)
    setDeletion({ conversation, busy: false, error: null })
  }

  async function confirmDelete() {
    if (!deletion || deletion.busy) return
    const { conversation } = deletion
    const controller = new AbortController()
    deleteRequest.current = controller
    setDeletion({ conversation, busy: true, error: null })
    try {
      await deleteConversation(conversation.id, { signal: controller.signal })
      if (controller.signal.aborted) return
      removeDeleted(conversation, `Deleted “${conversation.title}”.`)
    } catch (error) {
      if (controller.signal.aborted) return
      if (isNotFound(error)) {
        removeDeleted(conversation, `“${conversation.title}” had already been deleted.`)
        return
      }
      // As for the list: after a normal 401 the page goes away with the sign-out; if it stays, the
      // dialog explains, and Delete can be tried again or the dialog cancelled.
      setDeletion({ conversation, busy: false, error: requestErrorMessage(error) })
    }
  }

  // Called only once the server confirmed the delete (204) or that it was already gone (404).
  function removeDeleted(conversation: ConversationSummary, text: string) {
    // One synchronous update removes the item and the dialog. The dialog was rendered with
    // restoreFocus off while the delete ran, so nothing sends focus to the item's vanishing button.
    flushSync(() => {
      setList((current) =>
        current.status === 'loaded'
          ? { status: 'loaded', conversations: current.conversations.filter((item) => item.id !== conversation.id) }
          : current,
      )
      setDeletion(null)
    })
    // The page is no longer inert behind the dialog: move focus once, then announce the result.
    headingRef.current?.focus()
    setNotice(text)
  }

  const conversations = list.status === 'loaded' ? list.conversations : null

  return (
    <section className="workspace conversations-page" aria-labelledby="conversations-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">YOUR CONVERSATIONS</p>
          <h1 id="conversations-title" ref={headingRef} tabIndex={-1}>
            Conversations
          </h1>
          <p>Chats you have imported, newest first.</p>
        </div>
        <div className="conversation-header-actions">
          {conversations && conversations.length > 0 && (
            <span className="step-label conversation-count">{formatCount(conversations.length, 'conversation')}</span>
          )}
          <Link className="secondary-button" to="/conversations/import">
            Import a chat
          </Link>
        </div>
      </div>

      <p className="conversation-notice" role="status">
        {notice}
      </p>

      {list.status === 'loading' && (
        <p className="status-card" role="status">
          Loading your conversations...
        </p>
      )}

      {list.status === 'error' && (
        <div className="status-card status-card-error" role="alert">
          <p>
            <strong>Your conversations could not be loaded.</strong>
          </p>
          <p>{list.message}</p>
          <button type="button" className="secondary-button" onClick={retry}>
            Try again
          </button>
        </div>
      )}

      {conversations?.length === 0 && (
        <div className="status-card">
          <p>
            <strong>No conversations yet.</strong>
          </p>
          <p>Chats you import from WhatsApp will appear here.</p>
          <Link className="secondary-button" to="/conversations/import">
            Import a chat
          </Link>
        </div>
      )}

      {conversations && conversations.length > 0 && (
        <ul className="conversation-list">
          {conversations.map((conversation) => (
            <ConversationItem key={conversation.id} conversation={conversation} onDelete={askToDelete} />
          ))}
        </ul>
      )}

      {deletion && (
        <ConfirmDialog
          title="Delete this conversation?"
          confirmLabel="Delete"
          busyLabel="Deleting..."
          busy={deletion.busy}
          error={deletion.error}
          // While the delete runs, success would remove the item and its button, so focus must not go
          // back there. After a failure busy is false again, and Cancel returns focus to the button.
          restoreFocus={!deletion.busy}
          onConfirm={confirmDelete}
          onCancel={() => setDeletion(null)}
        >
          <p>
            {`“${deletion.conversation.title}” and its ${formatCount(deletion.conversation.message_count, 'message')}`}{' '}
            will be deleted permanently. This cannot be undone.
          </p>
          {/* Inside the dialog: everything outside it is inert while it is open, so cannot announce */}
          <p className="visually-hidden" role="status">
            {deletion.busy ? `Deleting “${deletion.conversation.title}”...` : ''}
          </p>
        </ConfirmDialog>
      )}
    </section>
  )
}

type ConversationItemProps = {
  conversation: ConversationSummary
  onDelete: (conversation: ConversationSummary, button: HTMLButtonElement) => void
}

function ConversationItem({ conversation, onDelete }: ConversationItemProps) {
  const otherOrder = conversation.date_order === 'day_first' ? 'month_first' : 'day_first'

  return (
    <li className="conversation-item">
      <div className="conversation-details">
        <h2 className="conversation-title">
          <Link to={`/conversations/${conversation.id}`}>{conversation.title}</Link>
        </h2>
        <p className="conversation-meta">
          <span className="source-badge">{sourceLabel(conversation.source)}</span>
          <span className="conversation-file">{conversation.original_filename}</span>
        </p>
        <ul className="conversation-stats">
          <li>{formatCount(conversation.message_count, 'message')}</li>
          <li>{formatDateRange(conversation.first_message_at, conversation.last_message_at)}</li>
          <li>Imported {formatInstant(conversation.imported_at)}</li>
        </ul>
        {conversation.date_order_ambiguous && (
          <p className="conversation-warning">
            <span aria-hidden="true">⚠ </span>
            Dates in this chat could be read either way. They were read as {dateOrderLabel(conversation.date_order)};
            if they look wrong, delete this chat and import it again choosing {dateOrderLabel(otherOrder)}.
          </p>
        )}
      </div>
      <button
        type="button"
        className="secondary-button conversation-delete"
        aria-label={`Delete ${conversation.title}`}
        onClick={(event) => onDelete(conversation, event.currentTarget)}
      >
        Delete
      </button>
    </li>
  )
}
