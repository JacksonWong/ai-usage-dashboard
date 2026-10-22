export function toast(message, kind = "") {
  const host = document.getElementById("toasts");
  if (!host) return;
  const node = document.createElement("div");
  node.className = `toast${kind ? ` toast--${kind}` : ""}`;
  node.textContent = String(message);
  host.appendChild(node);
  setTimeout(() => {
    node.style.opacity = "0";
    node.style.transform = "translateX(16px)";
    setTimeout(() => node.remove(), 220);
  }, 3600);
}
