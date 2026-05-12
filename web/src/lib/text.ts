/**
 * Strip <think> / <thinking> / <reasoning> / <reflection> blocks from any
 * model-emitted text. The backend already strips these at the LLM layer, but
 * older actions saved before the fix may still contain them — and this is a
 * cheap belt-and-suspenders for any future model that surprises us.
 */

const THINK_RE = /<(think|thinking|reasoning|reflection)\b[^>]*>[\s\S]*?<\/\1>/gi;
const ORPHAN_CLOSE_RE = /^\s*<\/(?:think|thinking|reasoning|reflection)>\s*/i;
const ORPHAN_OPEN_RE = /<(?:think|thinking|reasoning|reflection)\b[^>]*>/i;

export function stripReasoning(text: string | null | undefined): string {
  if (!text) return "";
  let out = text.replace(THINK_RE, "");
  out = out.replace(ORPHAN_CLOSE_RE, "");
  const m = out.match(ORPHAN_OPEN_RE);
  if (m && m.index !== undefined) {
    out = out.slice(0, m.index);
  }
  return out.replace(/\n{3,}/g, "\n\n").trim();
}
