import { Button } from "@/components/ui/Button";

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="border-l-2 border-negative pl-4 text-body text-negative">
      <p>{message}</p>
      {onRetry && (
        <Button variant="quiet" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
