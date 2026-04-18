const DEFAULT_BASE_URL = "http://127.0.0.1:9880";
const DEFAULT_USER_ID = "wx_child_user";
const STORAGE_KEY_COMPANION_USER_ID = "ar_companion_user_id";

function getApiBaseUrl() {
  const app = getApp();
  return (app && app.getApiBaseUrl) ? app.getApiBaseUrl() : DEFAULT_BASE_URL;
}

function isApiTemporarilyDown() {
  try {
    const app = getApp();
    if (!app || typeof app.isApiTemporarilyDown !== "function") return false;
    return !!app.isApiTemporarilyDown(getApiBaseUrl());
  } catch (e) {
    return false;
  }
}

function markApiTemporarilyDown() {
  try {
    const app = getApp();
    if (app && typeof app.markApiTemporarilyDown === "function") {
      app.markApiTemporarilyDown(getApiBaseUrl(), 20000);
    }
  } catch (e) {}
}

function clearApiDownMark() {
  try {
    const app = getApp();
    if (app && typeof app.clearApiDownMark === "function") {
      app.clearApiDownMark(getApiBaseUrl());
    }
  } catch (e) {}
}

/** 与后端 pet_egg.is_guest_companion_user_id 一致：未登录设备游客 id */
function isGuestCompanionUserId(uid) {
  const s = String(uid || "").trim();
  return s === "wx_child_user" || s.startsWith("wx_child_user_");
}

function getUserId() {
  // 已登录：与账号体系一致，伴宠/蛋/小柴数据按 user_id 隔离
  try {
    const app = getApp();
    const loggedIn = !!(app && app.globalData && app.globalData.isLoggedIn);
    const token =
      app && typeof app.getAuthToken === "function" ? String(app.getAuthToken() || "").trim() : "";
    const uid =
      app && typeof app.getUserId === "function" ? String(app.getUserId() || "").trim() : "";
    if (loggedIn && token && uid) {
      return uid;
    }
  } catch (e) {}

  // 未登录（游客/联调）：每台设备一份随机 id，便于测试且不污染正式账号
  try {
    const stored = wx.getStorageSync(STORAGE_KEY_COMPANION_USER_ID);
    if (stored) return String(stored).trim();
  } catch (e) {}
  const uid = `${DEFAULT_USER_ID}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  try {
    wx.setStorageSync(STORAGE_KEY_COMPANION_USER_ID, uid);
  } catch (e) {}
  return uid;
}

function requestPetState() {
  if (isApiTemporarilyDown()) return Promise.reject(new Error("api temporarily down"));
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/pet/state?user_id=${encodeURIComponent(getUserId())}`,
      method: "GET",
      success: (res) => {
        clearApiDownMark();
        resolve(res?.data || {});
      },
      fail: (err) => {
        markApiTemporarilyDown();
        reject(err);
      },
    });
  });
}

function reportPetProgress(eventType, payload = {}) {
  if (isApiTemporarilyDown()) return Promise.reject(new Error("api temporarily down"));
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/pet/progress/report`,
      method: "POST",
      data: {
        user_id: getUserId(),
        event_type: String(eventType || ""),
        payload: payload || {},
      },
      success: (res) => {
        clearApiDownMark();
        resolve(res?.data || {});
      },
      fail: (err) => {
        markApiTemporarilyDown();
        reject(err);
      },
    });
  });
}

function claimPetHatch() {
  if (isApiTemporarilyDown()) return Promise.reject(new Error("api temporarily down"));
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/pet/hatch/claim`,
      method: "POST",
      data: { user_id: getUserId() },
      success: (res) => {
        clearApiDownMark();
        resolve(res?.data || {});
      },
      fail: (err) => {
        markApiTemporarilyDown();
        reject(err);
      },
    });
  });
}

/** 宠物蛋主系统（10 槽，首页专页） */
function requestEggState() {
  if (isApiTemporarilyDown()) return Promise.reject(new Error("api temporarily down"));
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/pet/egg/state?user_id=${encodeURIComponent(getUserId())}`,
      method: "GET",
      success: (res) => {
        clearApiDownMark();
        resolve(res?.data || {});
      },
      fail: (err) => {
        markApiTemporarilyDown();
        reject(err);
      },
    });
  });
}

function reportEggProgress(eventType, payload = {}) {
  if (isApiTemporarilyDown()) return Promise.reject(new Error("api temporarily down"));
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/pet/egg/progress/report`,
      method: "POST",
      data: {
        user_id: getUserId(),
        event_type: String(eventType || ""),
        payload: payload || {},
      },
      header: { "Content-Type": "application/json" },
      success: (res) => {
        clearApiDownMark();
        resolve(res?.data || {});
      },
      fail: (err) => {
        markApiTemporarilyDown();
        reject(err);
      },
    });
  });
}

function claimEggSlot(slotIndex) {
  if (isApiTemporarilyDown()) return Promise.reject(new Error("api temporarily down"));
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/pet/egg/claim`,
      method: "POST",
      data: { user_id: getUserId(), slot_index: Number(slotIndex) },
      header: { "Content-Type": "application/json" },
      success: (res) => {
        clearApiDownMark();
        resolve(res?.data || {});
      },
      fail: (err) => {
        markApiTemporarilyDown();
        reject(err);
      },
    });
  });
}

function requestCompanionState(mascotId) {
  if (isApiTemporarilyDown()) return Promise.reject(new Error("api temporarily down"));
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/pet/companion/state?user_id=${encodeURIComponent(getUserId())}&mascot_id=${encodeURIComponent(String(mascotId || ""))}`,
      method: "GET",
      success: (res) => {
        clearApiDownMark();
        resolve(res?.data || {});
      },
      fail: (err) => {
        markApiTemporarilyDown();
        reject(err);
      },
    });
  });
}

function postCompanionAction(mascotId, actionType, payload = {}) {
  if (isApiTemporarilyDown()) return Promise.reject(new Error("api temporarily down"));
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/pet/companion/action`,
      method: "POST",
      data: {
        user_id: getUserId(),
        mascot_id: String(mascotId || ""),
        action_type: String(actionType || ""),
        payload: payload || {},
      },
      header: { "Content-Type": "application/json" },
      success: (res) => {
        const sc = Number(res && res.statusCode);
        if (sc >= 200 && sc < 300) {
          clearApiDownMark();
          resolve(res?.data || {});
        } else reject(res || new Error(`HTTP ${sc}`));
      },
      fail: (err) => {
        markApiTemporarilyDown();
        reject(err);
      },
    });
  });
}

function reportCompanionReadXp(mascotId, payload = {}) {
  if (isApiTemporarilyDown()) return Promise.reject(new Error("api temporarily down"));
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/pet/companion/read_xp`,
      method: "POST",
      data: {
        user_id: getUserId(),
        mascot_id: String(mascotId || ""),
        payload: payload || {},
      },
      header: { "Content-Type": "application/json" },
      success: (res) => {
        clearApiDownMark();
        resolve(res?.data || {});
      },
      fail: (err) => {
        markApiTemporarilyDown();
        reject(err);
      },
    });
  });
}

/** 设置展示形态档（1–3），后端校验已解锁 */
function postCompanionSetDisplayForm(mascotId, formTier) {
  if (isApiTemporarilyDown()) return Promise.reject(new Error("api temporarily down"));
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/pet/companion/set_display_form`,
      method: "POST",
      data: {
        user_id: getUserId(),
        mascot_id: String(mascotId || ""),
        form_tier: Math.max(1, Math.min(3, Number(formTier) || 1)),
      },
      header: { "Content-Type": "application/json" },
      success: (res) => {
        const sc = Number(res && res.statusCode);
        if (sc >= 200 && sc < 300) {
          clearApiDownMark();
          resolve(res?.data || {});
        } else reject(res || new Error(`HTTP ${sc}`));
      },
      fail: (err) => {
        markApiTemporarilyDown();
        reject(err);
      },
    });
  });
}

/** 保存某形态 3D 调参（egg / tier1–3），换设备从 companion/state 拉回
 * viewScope: "pet_detail" | "home" | "companion"（伴读页专用，与首页 home 分离）
 */
function postCompanionSetViewTuning(mascotId, formKey, tuning, camera, clearManualCamera, viewScope) {
  if (isApiTemporarilyDown()) return Promise.reject(new Error("api temporarily down"));
  return new Promise((resolve, reject) => {
    const data = {
      user_id: getUserId(),
      mascot_id: String(mascotId || ""),
      form_key: String(formKey || ""),
      view_scope: String(viewScope || "pet_detail"),
      tuning: tuning && typeof tuning === "object" ? tuning : {},
    };
    if (clearManualCamera) data.clear_manual_camera = true;
    else if (camera && typeof camera === "object") data.camera = camera;
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/pet/companion/set_view_tuning`,
      method: "POST",
      data,
      header: { "Content-Type": "application/json" },
      success: (res) => {
        const sc = Number(res && res.statusCode);
        if (sc >= 200 && sc < 300) {
          clearApiDownMark();
          resolve(res?.data || {});
        } else reject(res || new Error(`HTTP ${sc}`));
      },
      fail: (err) => {
        markApiTemporarilyDown();
        reject(err);
      },
    });
  });
}

function yearMonthKey() {
  const d = new Date();
  const m = d.getMonth() + 1;
  return `${d.getFullYear()}-${m < 10 ? "0" : ""}${m}`;
}

module.exports = {
  getUserId,
  isGuestCompanionUserId,
  requestPetState,
  reportPetProgress,
  claimPetHatch,
  requestEggState,
  reportEggProgress,
  claimEggSlot,
  requestCompanionState,
  postCompanionAction,
  reportCompanionReadXp,
  postCompanionSetDisplayForm,
  postCompanionSetViewTuning,
  yearMonthKey,
};
