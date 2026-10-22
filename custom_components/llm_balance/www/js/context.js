/**
 * 运行时上下文：当前挂载的 DOM 根节点与后端适配器。
 *
 * 独立部署时根节点是整个页面；Home Assistant 面板模式下是 shadow root。
 */

let root = document.body;
let backend = null;

export function setContext(nextRoot, nextBackend) {
  root = nextRoot;
  backend = nextBackend;
}

export function getRoot() {
  return root;
}

export function getBackend() {
  return backend;
}

export function el(id) {
  return root.querySelector(`#${id}`);
}

export function all(selector) {
  return [...root.querySelectorAll(selector)];
}
