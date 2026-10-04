import { Button } from "@/components/ui/Button";

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
    >
      <p>{message}</p>
      {onRetry && (
        <Button variant="secondary" className="mt-2" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}
