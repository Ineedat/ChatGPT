import type { ReactNode } from "react";

type HelpTooltipProps = { label: string; help: string; children?: ReactNode };

/** Accessible initial tooltip pattern. Help text is bundled with the UI. */
export function HelpTooltip({ label, help, children }: HelpTooltipProps) {
  return (
    <span className="help-tooltip" tabIndex={0} aria-label={label} title={help}>
      {children ?? <span className="help-tooltip__icon" aria-hidden="true">?</span>}
      <span className="help-tooltip__bubble" role="tooltip">{help}</span>
    </span>
  );
}
