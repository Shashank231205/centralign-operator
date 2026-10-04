import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-slate-900 text-white hover:bg-slate-700",
  secondary: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
  danger: "bg-red-600 text-white hover:bg-red-500",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  return (
    <button
      className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}
