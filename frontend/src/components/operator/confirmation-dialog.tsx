"use client";

import { useCallback, useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ConfirmationDialogProps {
  open: boolean;
  eyebrow: string;
  title: string;
  description: string;
  identity: ReactNode;
  outcome: ReactNode;
  confirmLabel: string;
  confirmDisabled?: boolean;
  children?: ReactNode;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmationDialog({
  open,
  eyebrow,
  title,
  description,
  identity,
  outcome,
  confirmLabel,
  confirmDisabled,
  children,
  onConfirm,
  onClose,
}: ConfirmationDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const priorFocus = useRef<HTMLElement | null>(null);
  const closeAndRestoreFocus = useCallback(() => {
    const target = priorFocus.current;
    onClose();
    target?.focus();
  }, [onClose]);

  useEffect(() => {
    if (!open) {
      return;
    }

    priorFocus.current = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();
    const overlay = overlayRef.current;
    const background = Array.from(document.body.children).filter(
      (element) => element !== overlay
    );
    const previousInert = background.map((element) =>
      element.hasAttribute("inert")
    );
    background.forEach((element) => element.setAttribute("inert", ""));
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeAndRestoreFocus();
      }
      if (event.key === "Tab" && overlay) {
        const focusable = Array.from(
          overlay.querySelectorAll<HTMLElement>(
            'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
          )
        );
        const first = focusable[0];
        const last = focusable.at(-1);
        if (
          event.shiftKey &&
          last &&
          (document.activeElement === first ||
            !overlay.contains(document.activeElement))
        ) {
          event.preventDefault();
          last.focus();
        } else if (
          !event.shiftKey &&
          first &&
          document.activeElement === last
        ) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      background.forEach((element, index) => {
        if (!previousInert[index]) {
          element.removeAttribute("inert");
        }
      });
      priorFocus.current?.focus();
    };
  }, [closeAndRestoreFocus, open]);

  if (!open) {
    return null;
  }

  return createPortal(
    <div
      ref={overlayRef}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-4"
    >
      <Card className="w-full max-w-lg border-2 border-foreground shadow-2xl">
        <CardHeader>
          <p className="text-xs font-black uppercase tracking-[0.2em] text-red-600">
            {eyebrow}
          </p>
          <CardTitle id={titleId} className="text-2xl">
            {title}
          </CardTitle>
          <p
            id={descriptionId}
            className="text-sm leading-relaxed text-muted-foreground"
          >
            {description}
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border bg-muted/40 p-3 text-sm">
            <div>{identity}</div>
            <div className="mt-2 font-semibold text-destructive">{outcome}</div>
          </div>
          {children}
          <div className="flex justify-end gap-2">
            <Button
              ref={cancelRef}
              variant="outline"
              onClick={closeAndRestoreFocus}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={onConfirm}
              disabled={confirmDisabled}
            >
              {confirmLabel}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>,
    document.body
  );
}
