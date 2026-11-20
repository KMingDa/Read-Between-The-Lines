import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { Link, useNavigate, useParams } from 'react-router'
import { deleteConversation, MESSAGE_PAGE_SIZE } from '../api/conversations'
import { isNotFound, requestErrorMessage } from '../api/errors'
import type { ChatMessage, ConversationDetail, Participant } from '../api/types'
import { ConfirmDialog } from '../components/ConfirmDialog'
import {
  hasMore,
  loadConversation,
  loadMoreMessages,
  messagePreview,
  messageRole,
  parseConversationId,
} from '../conversationView'
import type { ConversationOutcome, MessagesOutcome } from '../conversationView'
import { dateOrderLabel, formatCount, formatInstant, formatWallClock, sourceLabel } from '../format'

type View = { kind: 'loading' } | Exclude<ConversationOutcome, { kind: 'cancelled' }>

type Deletion = { busy: boolean; error: string | null }

/** No element has focus, e.g. because the link that led here has gone. */
function nothingFocused(): boolean {
  return document.activeElement === null || document.activeElement === document.body
}

export function ConversationPage() {
  const id = parseConversationId(useParams().conversationId)
  // An id that cannot exist is "not found" at once, without a request. The key gives every
  // conversation a fresh view, so nothing of the previous one is shown or still loading.
  return id === null ? <ConversationNotFound /> : <ConversationView key={id} id={id} />
}

function ConversationView({ id }: { id: number }) {
  const [view, setView] = useState<View>({ kind: 'loading' })
  const [me, setMe] = useState<string | null>(null) // the participant picked as "you": page memory only
  const headingRef = useRef<HTMLHeadingElement>(null)
  const request = useRef<AbortController | null>(null)
  const [deletion, setDeletion] = useState<Deletion | null>(null)
  const deleteRequest = useRef<AbortController | null>(null)
  const navigate = useNavigate()

  // Only the newest load may update the page: starting one cancels the one before.
  const load = useCallback(() => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    void loadConversation(id, controller.signal).then((outcome) => {
      if (outcome.kind !== 'cancelled' && request.current === controller) setView(outcome)
    })
  }, [id])

  useEffect(() => {
    load()
    return () => request.current?.abort()
  }, [load])

  // Coming from a link that is now gone, focus the title once it is known.
  useEffect(() => {
    if (view.kind === 'loaded' && nothingFocused()) headingRef.current?.focus()
  }, [view.kind])

  // Leaving the page cancels a delete still waiting for its answer, so a late answer can no longer
  // navigate or change the dialog (the server may still have deleted the conversation). On
  // Back/Forward this happens within the popstate event: here, or in the cleanup if React renders
  // the route change during that event. The cleanup, a layout effect, also covers every other way
  // out, in the commit that removes the page.
  useLayoutEffect(() => {
    const pagePath = window.location.pathname
    const cancelDelete = () => deleteRequest.current?.abort()
    // Not when Back/Forward stays on this page (an entry differing only in #hash, say): the dialog
    // stays open too, and would be left busy for good.
    const onPopState = () => {
      if (window.location.pathname !== pagePath) cancelDelete()
    }
    window.addEventListener('popstate', onPopState)
    return () => {
      window.removeEventListener('popstate', onPopState)
      cancelDelete()
    }
  }, [])

  function retry() {
    headingRef.current?.focus() // the Try again button is about to be replaced
    setView({ kind: 'loading' })
    load()
  }

  function askToDelete(button: HTMLButtonElement) {
    button.focus() // some browsers do not focus a clicked button; Cancel returns focus here
    setDeletion({ busy: false, error: null })
  }

  async function confirmDelete(conversation: ConversationDetail) {
    if (!deletion || deletion.busy) return // one delete at a time
    const controller = new AbortController()
    deleteRequest.current = controller
    setDeletion({ busy: true, error: null })
    try {
      await deleteConversation(conversation.id, { signal: controller.signal })
      if (controller.signal.aborted) return
      leaveAfterDelete(`Deleted “${conversation.title}”.`)
    } catch (error) {
      if (controller.signal.aborted) return
      if (isNotFound(error)) {
        leaveAfterDelete(`“${conversation.title}” had already been deleted.`)
        return
      }
      // After a normal 401 the page goes away with the sign-out; otherwise the dialog explains,
      // and Delete can be tried again or the dialog cancelled.
      setDeletion({ busy: false, error: requestErrorMessage(error) })
    }
  }

  // Called only once the server confirmed the delete (204) or that it was already gone (404).
  // replace: Back must not lead to a conversation that no longer exists. The list announces the
  // notice and focuses its heading.
  function leaveAfterDelete(notice: string) {
    navigate('/conversations', { replace: true, state: { notice } })
  }

  if (view.kind === 'not-found') return <ConversationNotFound />

  return (
    <section className="workspace conversation-page" aria-labelledby="conversation-title">
      <BackLink />
      <p className="eyebrow">CONVERSATION</p>
      <h1 id="conversation-title" ref={headingRef} tabIndex={-1}>
        {view.kind === 'loaded' ? view.conversation.title : 'Conversation'}
      </h1>

      {view.kind === 'loading' && (
        <p className="status-card conversation-status" role="status">
          Loading conversation...
        </p>
      )}

      {view.kind === 'failed' && (
        <LoadError title="This conversation could not be loaded." message={view.message} onRetry={retry} />
      )}

      {view.kind === 'loaded' && (
        <>
          <ConversationDetails conversation={view.conversation} onDelete={askToDelete} />
          <Participants participants={view.conversation.participants} me={me} onChoose={setMe} />
          <Messages conversationId={id} messages={view.messages} me={me} onRetry={retry} />
        </>
      )}

      {view.kind === 'loaded' && deletion && (
        <ConfirmDialog
          title="Delete this conversation?"
          confirmLabel="Delete"
          busyLabel="Deleting..."
          busy={deletion.busy}
          error={deletion.error}
          // While the delete runs, success leaves this page, so focus must not go back to the Delete
          // button. After a failure busy is false again, and Cancel returns focus to it.
          restoreFocus={!deletion.busy}
          onConfirm={() => void confirmDelete(view.conversation)}
          onCancel={() => setDeletion(null)}
        >
          <p>
            {`“${view.conversation.title}” and its ${formatCount(view.conversation.message_count, 'message')}`}{' '}
            will be deleted permanently. This cannot be undone.
          </p>
          {/* Inside the dialog: everything outside it is inert while it is open, so cannot announce */}
          <p className="visually-hidden" role="status">
            {deletion.busy ? `Deleting “${view.conversation.title}”...` : ''}
          </p>
        </ConfirmDialog>
      )}
    </section>
  )
}

function ConversationNotFound() {
  const headingRef = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    if (nothingFocused()) headingRef.current?.focus()
  }, [])

  return (
    <section className="workspace conversation-page" aria-labelledby="conversation-title">
      <BackLink />
      <h1 id="conversation-title" ref={headingRef} tabIndex={-1}>
        Conversation not found
      </h1>
      <p className="conversation-muted">It may have been deleted, or the address is not right.</p>
    </section>
  )
}

function BackLink() {
  return (
    <Link className="conversation-back" to="/conversations">
      <span aria-hidden="true">← </span>
      Your conversations
    </Link>
  )
}

function LoadError({ title, message, onRetry }: { title: string; message: string; onRetry: () => void }) {
  return (
    <div className="status-card status-card-error conversation-status" role="alert">
      <p>
        <strong>{title}</strong>
      </p>
      <p>{message}</p>
      <button type="button" className="secondary-button" onClick={onRetry}>
        Try again
      </button>
    </div>
  )
}

type ConversationDetailsProps = {
  conversation: ConversationDetail
  onDelete: (button: HTMLButtonElement) => void
}

function ConversationDetails({ conversation, onDelete }: ConversationDetailsProps) {
  const otherOrder = conversation.date_order === 'day_first' ? 'month_first' : 'day_first'

  return (
    <div className="conversation-summary">
      <p className="conversation-meta">
        <span className="source-badge">{sourceLabel(conversation.source)}</span>
        <span className="conversation-file">{conversation.original_filename}</span>
      </p>
      <ul className="conversation-stats">
        <li>{formatCount(conversation.message_count, 'message')}</li>
        <li>First message {formatWallClock(conversation.first_message_at)}</li>
        <li>Last message {formatWallClock(conversation.last_message_at)}</li>
        <li>Imported {formatInstant(conversation.imported_at)}</li>
      </ul>
      <p className="conversation-muted">
        Date order: {dateOrderLabel(conversation.date_order)}
        {conversation.date_order_ambiguous ? ', assumed because the dates fit either order' : ''}.
      </p>
      {conversation.date_order_ambiguous && (
        <p className="conversation-warning">
          <span aria-hidden="true">⚠ </span>
          If the dates look wrong, delete this conversation, then import the file again choosing{' '}
          {dateOrderLabel(otherOrder)}.
        </p>
      )}
      <div className="conversation-summary">
        <button
          type="button"
          className="secondary-button conversation-delete"
          onClick={(event) => onDelete(event.currentTarget)}
        >
          Delete conversation
        </button>
      </div>
    </div>
  )
}

type ParticipantsProps = {
  participants: Participant[]
  me: string | null
  onChoose: (name: string | null) => void
}

function Participants({ participants, me, onChoose }: ParticipantsProps) {
  return (
    <section className="conversation-section" aria-labelledby="participants-title">
      <h2 id="participants-title">Participants</h2>
      {participants.length === 0 ? (
        <p className="conversation-muted">No participants: this chat has only system messages.</p>
      ) : (
        <>
          <ul className="participant-list">
            {participants.map((participant) => (
              <li key={participant.name}>
                {participant.name}
                <span className="participant-count">{formatCount(participant.message_count, 'message')}</span>
              </li>
            ))}
          </ul>
          <label className="participant-picker">
            You are
            <select
              value={me ?? ''}
              aria-describedby="participant-picker-hint"
              onChange={(event) => onChoose(event.target.value || null)}
            >
              <option value="">Not chosen</option>
              {participants.map((participant) => (
                <option key={participant.name} value={participant.name}>
                  {participant.name}
                </option>
              ))}
            </select>
          </label>
          <p id="participant-picker-hint" className="conversation-hint">
            Your messages are then shown on the right. The choice is not saved.
          </p>
        </>
      )}
    </section>
  )
}

type MessagesProps = { conversationId: number; messages: MessagesOutcome; me: string | null; onRetry: () => void }

function Messages({ conversationId, messages, me, onRetry }: MessagesProps) {
  return (
    <section className="conversation-section" aria-labelledby="messages-title">
      <h2 id="messages-title">Messages</h2>
      {messages.kind === 'failed' ? (
        <LoadError title="The messages could not be loaded." message={messages.message} onRetry={onRetry} />
      ) : messages.messages.length === 0 ? (
        <p className="status-card">No messages in this conversation.</p>
      ) : (
        <MessageList conversationId={conversationId} first={messages} me={me} />
      )}
    </section>
  )
}

type LoadingMore =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'failed'; message: string }
  | { status: 'gone' } // the conversation was deleted meanwhile

type MessageListProps = {
  conversationId: number
  first: Extract<MessagesOutcome, { kind: 'loaded' }>
  me: string | null
}

function MessageList({ conversationId, first, me }: MessageListProps) {
  const [messages, setMessages] = useState(first.messages)
  const [total, setTotal] = useState(first.total)
  const [more, setMore] = useState<LoadingMore>({ status: 'idle' })
  const listRef = useRef<HTMLOListElement>(null)
  const statusRef = useRef<HTMLDivElement>(null) // "Loading…" or what went wrong; focused when it appears
  const request = useRef<AbortController | null>(null)

  // Leaving the page or this conversation, or reloading it, cancels a page that is still loading.
  useEffect(() => () => request.current?.abort(), [])

  async function loadMore() {
    if (more.status === 'loading') return // one page at a time
    const controller = new AbortController()
    request.current = controller
    // The button is disabled while loading, so focus moves to the message saying so.
    flushSync(() => setMore({ status: 'loading' }))
    statusRef.current?.focus()

    const outcome = await loadMoreMessages(conversationId, messages, controller.signal)
    if (outcome.kind === 'cancelled' || request.current !== controller) return

    if (outcome.kind === 'loaded') {
      const shownBefore = messages.length
      flushSync(() => {
        setMessages(outcome.messages)
        setTotal(outcome.total)
        setMore({ status: 'idle' })
      })
      // Reading goes on at the first new message (new messages come after those already shown).
      const firstNew = listRef.current?.children[shownBefore]
      if (firstNew instanceof HTMLElement) firstNew.focus()
      else listRef.current?.focus() // the page added nothing new
    } else {
      flushSync(() =>
        setMore(outcome.kind === 'not-found' ? { status: 'gone' } : { status: 'failed', message: outcome.message }),
      )
      statusRef.current?.focus() // the message says what went wrong; the next Tab is Try again
    }
  }

  return (
    <>
      <ol ref={listRef} className="message-list" tabIndex={-1}>
        {messages.map((message) => (
          <MessageItem key={message.position} message={message} me={me} />
        ))}
      </ol>
      {/* No live region or role="alert" here: focus moves to these messages, and screen readers read them then */}
      <div className="message-more">
        {more.status === 'loading' && (
          <div ref={statusRef} className="status-card message-more-status" tabIndex={-1}>
            Loading {formatCount(Math.min(MESSAGE_PAGE_SIZE, total - messages.length), 'more message')}...
          </div>
        )}
        {more.status === 'failed' && (
          <div ref={statusRef} className="status-card status-card-error message-more-status" tabIndex={-1}>
            <p>
              <strong>The next messages could not be loaded.</strong>
            </p>
            <p>{more.message}</p>
          </div>
        )}
        {more.status === 'gone' && (
          <div ref={statusRef} className="status-card status-card-error message-more-status" tabIndex={-1}>
            <p>
              <strong>This conversation no longer exists.</strong> It may have been deleted.
            </p>
            <p>
              <Link to="/conversations">Go to your conversations</Link>
            </p>
          </div>
        )}
        {more.status !== 'gone' && hasMore(messages, total) && (
          <>
            <p className="message-count">
              Showing {messages.length.toLocaleString()} of {formatCount(total, 'message')}.
            </p>
            <button type="button" className="secondary-button" disabled={more.status === 'loading'} onClick={loadMore}>
              {more.status === 'failed' ? 'Try again' : 'Load more messages'}
            </button>
          </>
        )}
      </div>
    </>
  )
}

function MessageItem({ message, me }: { message: ChatMessage; me: string | null }) {
  const [full, setFull] = useState(false)
  const textRef = useRef<HTMLParagraphElement>(null)
  const preview = useMemo(() => messagePreview(message.content), [message.content])
  const role = messageRole(message, me)
  const time = <time dateTime={message.sent_at}>{formatWallClock(message.sent_at)}</time>

  function showFull() {
    flushSync(() => setFull(true))
    textRef.current?.focus() // the button has gone; keep the reader's place in the conversation
  }

  return (
    <li className={`message message-${role}`} tabIndex={-1}>
      {role !== 'system' && (
        <p className="message-meta">
          <span className="message-sender">{role === 'own' ? `${message.sender} (you)` : message.sender}</span>
          {time}
        </p>
      )}
      <p ref={textRef} className="message-text" tabIndex={full ? -1 : undefined}>
        {full ? message.content : preview.text}
      </p>
      {!full && preview.hidden > 0 && (
        <button type="button" className="text-button" onClick={showFull}>
          Show full message ({formatCount(preview.hidden, 'more character')})
        </button>
      )}
      {role === 'system' && <p className="message-meta">{time}</p>}
    </li>
  )
}
