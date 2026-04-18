/**
 * 小程序逻辑路径 /assets/... 已统一由后端 /assets/... 提供。
 * 将逻辑路径转为完整 URL（路径段 URL 编码以支持中文文件名）。
 */

const DEFAULT_BASE = "http://127.0.0.1:9880";

function normalizeBase(url) {
  const s = String(url || "").trim().replace(/\/+$/, "");
  return s || DEFAULT_BASE;
}

function getApiBase() {
  try {
    const app = typeof getApp === "function" ? getApp() : null;
    if (app && typeof app.getApiBaseUrl === "function") {
      return normalizeBase(app.getApiBaseUrl());
    }
  } catch (e) {}
  return DEFAULT_BASE;
}

function toMiniprogramAssetUrl(relPath) {
  const p = String(relPath || "").trim();
  if (!p) return "";
  if (/^https?:\/\//i.test(p)) return p;
  if (p.startsWith("/assets/")) {
    const b = getApiBase();
    const tail = p.slice("/assets/".length);
    const segs = tail.split("/").map((seg) => encodeURIComponent(seg)).join("/");
    return `${b}/assets/${segs}`;
  }
  return p;
}

function getMiniprogramStaticBase() {
  return `${getApiBase()}/assets`;
}

module.exports = {
  getApiBase,
  toMiniprogramAssetUrl,
  getMiniprogramStaticBase,
};
