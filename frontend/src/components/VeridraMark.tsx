export function VeridraMark({ className = 'h-8 w-8' }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <circle cx="32" cy="32" r="30" fill="#18233A" />
      <circle cx="32" cy="32" r="24" stroke="#5B5CE2" strokeWidth="3" />
      <path
        d="M21 32.5L28.5 40L44 24.5"
        stroke="#FFFFFF"
        strokeWidth="4.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="44" cy="24.5" r="4" fill="#13A89E" />
    </svg>
  );
}
