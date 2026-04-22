/**
 * 小程序包内 /assets 由后端 /assets 统一提供。
 * 将逻辑路径 /assets/... 转为可请求的完整 URL（路径段 URL 编码以支持中文文件名）。
 */

const { resolveApiBase, DEV_LOOPBACK_FALLBACK } = require("./api-base.js");

function normalizeBase(url) {
  const s = String(url || "").trim().replace(/\/+$/, "");
  return s || DEV_LOOPBACK_FALLBACK;
}

function getApiBase() {
  return normalizeBase(resolveApiBase(null));
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
