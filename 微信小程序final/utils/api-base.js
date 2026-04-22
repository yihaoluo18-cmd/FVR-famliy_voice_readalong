/**
 * 统一解析小程序请求使用的 API 根地址（与 app.getApiBaseUrl 逻辑对齐，避免各处散落 127.0.0.1）。
 */
const deploy = require("./deploy-config.js");

const DEV_LOOPBACK_FALLBACK = "http://127.0.0.1:9880";

function normalizeBaseUrl(url) {
  if (!url) return "";
  return String(url).trim().replace(/\/+$/, "");
}

function getForcedOnlineApiBase() {
  return normalizeBaseUrl(deploy.onlineApiBaseUrl || "");
}

function readStoredApiBaseUrl() {
  try {
    const primary = normalizeBaseUrl(wx.getStorageSync("apiBaseUrl") || "");
    if (primary) return primary;
    const legacy = normalizeBaseUrl(wx.getStorageSync("readalong.apiBaseUrl") || "");
    if (legacy) return legacy;
  } catch (e) {}
  return "";
}

/**
 * @param {WechatMiniprogram.App.Instance|null|undefined} appMaybe 可传入 getApp()，传 null 时内部会尝试 getApp()
 */
function resolveApiBase(appMaybe) {
  const forced = getForcedOnlineApiBase();
  if (forced) return forced;
  let app = appMaybe;
  if (app === undefined || app === null) {
    try {
      app = typeof getApp === "function" ? getApp() : null;
    } catch (e) {
      app = null;
    }
  }
  if (app && typeof app.getApiBaseUrl === "function") {
    const u = normalizeBaseUrl(app.getApiBaseUrl());
    if (u) return u;
  }
  if (app && app.globalData && app.globalData.apiBaseUrl) {
    const u = normalizeBaseUrl(app.globalData.apiBaseUrl);
    if (u) return u;
  }
  const stored = readStoredApiBaseUrl();
  if (stored) return stored;
  return DEV_LOOPBACK_FALLBACK;
}

module.exports = {
  normalizeBaseUrl,
  getForcedOnlineApiBase,
  resolveApiBase,
  DEV_LOOPBACK_FALLBACK,
};
