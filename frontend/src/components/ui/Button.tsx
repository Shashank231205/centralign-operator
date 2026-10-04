import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "quiet" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-ink text-paper hover:bg-accent",
  quiet: "text-ink underline decoration-rule underline-offset-4 hover:decoration-ink",
  danger: "text-negative underline decoration-rule underline-offset-4 hover:decoration-negative",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  const shape = variant === "primary" ? "px-4 py-2" : "py-2";
  return (
    <button
      className={`${shape} text-body transition-colors duration-100 disabled:cursor-not-allowed disabled:opacity-40 ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}
