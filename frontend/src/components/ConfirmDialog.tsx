import { useId, useLayoutEffect, useRef } from 'react'
import type { ReactNode } from 'react'

type ConfirmDialogProps = {
  title: string
  children: ReactNode // what will happen, e.g. which conversation is deleted
  confirmLabel: string
  busyLabel: string // the confirm button's text while the action runs
  busy: boolean
  error: string | null
  /** When the dialog goes away, send focus back to the element that opened it (default true).
   *  False when that element is about to disappear: the caller then moves focus itself. */
  restoreFocus?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/**
 * A modal confirmation on the native <dialog>, open while it is mounted. Focus starts on Cancel,
 * Escape cancels, nothing cancels while busy, and when it goes away focus returns to the element
 * that had it when it opened (if restoreFocus is on and that element still exists).
 */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  busyLabel,
  busy,
  error,
  restoreFocus = true,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const restoreFocusRef = useRef(restoreFocus)
  const titleId = useId()
  const messageId = useId()

  // The unmount cleanup below needs the latest restoreFocus, not the one from the first render.
  useLayoutEffect(() => {
    restoreFocusRef.current = restoreFocus
  })

  // A layout effect, so the dialog opens before the first paint and its cleanup runs while it is
  // still in the page.
  useLayoutEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    const opener = document.activeElement
    dialog.showModal()
    cancelRef.current?.focus() // the safe choice, whatever the browser focused first
    return () => {
      // Without restoreFocus, skip close(): closing would make the browser itself send focus back
      // to the opener. Removing the open dialog with the page's update does not move focus.
      if (!restoreFocusRef.current) return
      dialog.close()
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus()
    }
  }, [])

  function cancel() {
    if (!busy) onCancel()
  }

  return (
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      role="alertdialog"
      aria-labelledby={titleId}
      aria-describedby={messageId}
      onCancel={(event) => {
        event.preventDefault() // Escape: the page decides when the dialog goes away
        cancel()
      }}
      onClose={() => {
        // A browser may close a dialog without a cancelable "cancel" event (e.g. a second Escape),
        // and this event arrives later. If the action is still running, or has failed meanwhile and
        // shows its error, open it again; only a close with neither counts as Cancel.
        const dialog = dialogRef.current
        if (!dialog || dialog.open || !dialog.isConnected) return // reopened already, or unmounted
        if (busy || error) dialog.showModal()
        else onCancel()
      }}
    >
      <h2 id={titleId}>{title}</h2>
      <div id={messageId} className="confirm-dialog-message">
        {children}
      </div>
      {error && (
        <p className="confirm-dialog-error" role="alert">
          {error}
        </p>
      )}
      <div className="confirm-dialog-actions">
        <button
          ref={cancelRef}
          type="button"
          className="secondary-button"
          aria-disabled={busy || undefined}
          onClick={cancel}
        >
          Cancel
        </button>
        <button
          type="button"
          className="danger-button"
          aria-disabled={busy || undefined}
          onClick={() => {
            if (!busy) onConfirm()
          }}
        >
          {busy ? busyLabel : confirmLabel}
        </button>
      </div>
    </dialog>
  )
}
