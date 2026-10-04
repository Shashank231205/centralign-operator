import type { TextareaHTMLAttributes } from "react";

export function TextArea({
  className = "",
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={`w-full resize-y border-0 border-b border-rule bg-transparent py-2 text-body placeholder:text-faint focus:border-ink focus:outline-none ${className}`}
      {...props}
    />
  );
}
