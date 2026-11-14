// Small helpers shared by the product, dashboard and compare pages.

/** Builds a DOM node. Text is always added as text, never as HTML. */
export function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) node.append(kid instanceof Node ? kid : String(kid));
  return node;
}

/** A lone web address means "read this page"; anything else is policy text. Returns the address or null. */
export const asLink = (value) => (/^(https?:\/\/)?([a-z0-9-]+\.)+[a-z]{2,}(:\d+)?([/?#]\S*)?$/i.test(value.trim()) ? value.trim() : null);
