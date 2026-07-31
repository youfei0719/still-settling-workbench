import { Link } from "@tanstack/react-router"

import { cn } from "@/lib/utils"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
}: LogoProps) {
  const content =
    variant === "responsive" ? (
      <>
        <img
          src="/assets/images/still-settling-mark.svg"
          alt="依旧沉淀"
          className={cn(
            "size-6 group-data-[collapsible=icon]:hidden",
            className,
          )}
        />
        <img
          src="/assets/images/still-settling-mark.svg"
          alt="依旧沉淀"
          className={cn(
            "size-5 hidden group-data-[collapsible=icon]:block",
            className,
          )}
        />
      </>
    ) : (
      <img
        src="/assets/images/still-settling-mark.svg"
        alt="依旧沉淀"
        className={cn(variant === "full" ? "size-6" : "size-5", className)}
      />
    )

  if (!asLink) {
    return content
  }

  return <Link to="/">{content}</Link>
}
