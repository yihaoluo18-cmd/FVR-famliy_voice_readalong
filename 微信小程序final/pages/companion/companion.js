const app = getApp();
const { resolveApiBase } = require("../../utils/api-base.js");
const COMPANION_SCENE_KEY = "companion";
const {
  getUserId: getCompanionScopeUserId,
  isGuestCompanionUserId,
  requestEggState,
  requestCompanionState,
  postCompanionSetDisplayForm,
  postCompanionSetViewTuning,
} = require("../../utils/pet-growth.js");
const { getPetById, getFormTierModelUrl, getStaticEggModelUrl, getEggModelUrl } = require("../../utils/pets-catalog.js");
const { toMiniprogramAssetUrl } = require("../../utils/asset-url.js");
const { reportAmusementParkTaskDone } = require("../../utils/amusement-park-stars.js");
let createScopedThreejs = null;
let registerGLTFLoader = null;
let THREE_IMPORT_ERROR = "";

try {
  ({ createScopedThreejs } = require("threejs-miniprogram"));
  ({ registerGLTFLoader } = require("./gltf-loader.js"));
} catch (e) {
  THREE_IMPORT_ERROR = String(e || "");
}

function resolveModelUrl(rel) {
  const s = String(rel || "").trim();
  if (!s) return "";
  if (s.startsWith("http")) return s;
  return `${getApiBaseUrl()}${s.startsWith("/") ? "" : "/"}${s}`;
}

function getApiBaseUrl() {
  return resolveApiBase(app);
}

function getWindowMetrics() {
  let windowWidth = 375;
  let pixelRatio = 1;
  try {
    const w = typeof wx.getWindowInfo === "function" ? wx.getWindowInfo() || {} : {};
    const d = typeof wx.getDeviceInfo === "function" ? wx.getDeviceInfo() || {} : {};
    windowWidth = Number(w.windowWidth || d.windowWidth || 375) || 375;
    pixelRatio = Number(d.pixelRatio || w.pixelRatio || 1) || 1;
  } catch (e) {}
  return { windowWidth, pixelRatio };
}

const QUICK_REPLIES = [
  { icon: "👋", text: "你好呀" },
  { icon: "🎨", text: "我们来玩颜色游戏" },
  { icon: "📚", text: "给我讲个短故事" },
  { icon: "💪", text: "夸夸我今天的表现" },
  { icon: "😴", text: "我有点困了" },
  { icon: "🥳", text: "我今天超开心" },
];

function pickContextQuickReplies(text) {
  const clean = String(text || "").trim();
  if (!clean) return QUICK_REPLIES;
  if (/故事|讲|童话|绘本/.test(clean)) {
    return [
      { icon: "📖", text: "继续讲下去" },
      { icon: "🎭", text: "换个角色声音" },
      { icon: "✨", text: "结局更惊喜一点" },
      QUICK_REPLIES[0],
      QUICK_REPLIES[3],
      QUICK_REPLIES[5],
    ];
  }
  if (/困|睡|累/.test(clean)) {
    return [
      { icon: "🌙", text: "来一句晚安鼓励" },
      { icon: "🧘", text: "做个放松呼吸" },
      QUICK_REPLIES[2],
      QUICK_REPLIES[3],
      QUICK_REPLIES[0],
      QUICK_REPLIES[5],
    ];
  }
  if (/开心|棒|会了|完成/.test(clean)) {
    return [
      { icon: "🏆", text: "再夸夸我一次" },
      { icon: "🎉", text: "给我一个庆祝任务" },
      QUICK_REPLIES[2],
      QUICK_REPLIES[1],
      QUICK_REPLIES[0],
      QUICK_REPLIES[4],
    ];
  }
  return QUICK_REPLIES;
}

function detectMoodClass(text) {
  const clean = String(text || "");
  if (/棒|太好|厉害|真赞|开心|太棒|完成|进步/.test(clean)) return "mood-cheer";
  if (/困|累|难过|害怕|不想|生气|烦/.test(clean)) return "mood-calm";
  return "mood-default";
}

function buildWelcomeText(companionName) {
  const n = String(companionName || "小伙伴").trim() || "小伙伴";
  return `嗨，我是${n}～你可以按住说话，或者打字、点下面小按钮跟我聊哦。`;
}

function classifyCompanionErrorReason(text) {
  const lower = String(text || "").toLowerCase();
  if (!lower) return "";
  if (
    lower.includes("provider_arrearage") ||
    lower.includes("arrearage") ||
    lower.includes("insufficient_balance") ||
    lower.includes("quota") ||
    lower.includes("欠费") ||
    lower.includes("余额不足")
  ) {
    return "provider_arrearage";
  }
  if (
    lower.includes("provider_auth_error") ||
    lower.includes("invalid api key") ||
    lower.includes("apikey") ||
    lower.includes("api key") ||
    lower.includes("unauthorized") ||
    lower.includes("authentication") ||
    lower.includes("forbidden") ||
    lower.includes("鉴权") ||
    lower.includes("密钥")
  ) {
    return "provider_auth_error";
  }
  return "";
}

function parseCompanionBackendError(payload, statusCode, networkFail = false) {
  if (networkFail) {
    return { reason: "network_error", message: "网络有点忙，请稍后重试。", raw: "" };
  }

  const data = payload && typeof payload === "object" ? payload : {};
  const detail = data.detail;
  let reason = "";
  let message = "";
  let raw = "";

  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    reason = String(detail.reason || "").trim();
    message = String(detail.message || "").trim();
    raw = String(detail.detail || detail.raw || "").trim();
  } else if (typeof detail === "string") {
    raw = detail.trim();
  }

  if (!message && typeof data.message === "string") message = data.message.trim();
  if (!raw && typeof data.error === "string") raw = data.error.trim();

  const merged = [reason, message, raw].filter(Boolean).join(" ");
  if (!reason) reason = classifyCompanionErrorReason(merged);

  if (!message) {
    if (reason === "provider_arrearage") {
      message = "当前 AI 服务账号欠费，伴宠暂时无法回复。";
    } else if (reason === "provider_auth_error") {
      message = "当前 AI 服务密钥或鉴权异常，伴宠暂时无法回复。";
    } else if (Number(statusCode || 0) >= 500) {
      message = "伴宠 AI 暂时不可用，请稍后重试。";
    } else {
      message = raw || "请求失败，请稍后重试。";
    }
  }

  return { reason, message, raw };
}

function buildCompanionErrorUi(reason, message) {
  if (reason === "provider_arrearage") {
    return {
      bubble: "我现在连不上云端大脑啦：AI 服务账号欠费。请联系管理员处理后，我们马上继续聊～",
      hint: "AI账号欠费，待处理",
      toast: "AI欠费",
    };
  }
  if (reason === "provider_auth_error") {
    return {
      bubble: "我这边的 AI 鉴权配置出了点问题，暂时不能正常陪聊。请联系管理员检查密钥配置。",
      hint: "AI鉴权异常",
      toast: "密钥异常",
    };
  }
  if (reason === "network_error") {
    return {
      bubble: "网络有点忙，我们稍后再试一次吧～",
      hint: "网络有点忙，再试试",
      toast: "网络繁忙",
    };
  }
  return {
    bubble: message || "伴宠 AI 暂时不可用，我们稍后再试一次吧～",
    hint: "伴宠AI暂不可用",
    toast: "AI暂不可用",
  };
}


const AVATAR_OPTIONS = [
  { personaId: "default", label: "柴柴小星", emoji: "🐕" },
  { personaId: "cute_chick", label: "嘎嘎小黄", emoji: "🐥" },
];

const MASCOT_TO_PERSONA = {
  "cute-dog": { personaId: "default", displayName: "柴柴小星", emoji: "🐶", wallpaper: "/assets/images/小狗.png" },
  "cute-fox": { personaId: "cute_fox", displayName: "狐狸小橙", emoji: "🦊", wallpaper: "/assets/images/狐狸.png" },
  "cute-dino": { personaId: "cute_dino", displayName: "恐龙小绿", emoji: "🦕", wallpaper: "/assets/images/恐龙.png" },
  "cute-cat": { personaId: "cute_cat", displayName: "小猫咪咪", emoji: "🐱", wallpaper: "/assets/images/小猫.png" },
  "cute-bunny": { personaId: "cute_bunny", displayName: "兔兔小白", emoji: "🐰", wallpaper: "/assets/images/小兔.png" },
  "cute-squirrel": { personaId: "cute_squirrel", displayName: "松鼠栗栗", emoji: "🐿️", wallpaper: "/assets/images/松鼠.png" },
  "cute-chick": { personaId: "cute_chick", displayName: "嘎嘎小黄", emoji: "🐥", wallpaper: "/assets/images/小狗.png" },
  "cute-panda": { personaId: "cute_panda", displayName: "熊猫萌萌", emoji: "🐼", wallpaper: "/assets/images/小狗.png" },
  "cute-koala": { personaId: "cute_koala", displayName: "考拉困困", emoji: "🐨", wallpaper: "/assets/images/小狗.png" },
  "cute-penguin": { personaId: "cute_penguin", displayName: "企鹅摇摇", emoji: "🐧", wallpaper: "/assets/images/小狗.png" },
};

const MASCOT_AVATARS_ALL = [
  { id: "cute-dog", name: "柴小汪", url: "/assets/images/柴犬封面.png", emoji: "🐶" },
  { id: "cute-fox", name: "小狐狸", url: "/assets/images/狐狸.png", emoji: "🦊" },
  { id: "cute-dino", name: "恐龙", url: "/assets/images/恐龙.png", emoji: "🦕" },
  { id: "cute-cat", name: "猫小咪", url: "/assets/images/小猫封面.png", emoji: "🐱" },
  { id: "cute-bunny", name: "兔小白", url: "/assets/images/兔子封面.png", emoji: "🐰" },
  { id: "cute-squirrel", name: "小松鼠", url: "/assets/images/松鼠封面.png", emoji: "🐿️" },
  { id: "cute-chick", name: "鸭嘎嘎", url: "/assets/images/小鸭封面.png", emoji: "🐥" },
  { id: "cute-panda", name: "熊墩墩", url: "/assets/images/熊猫封面.png", emoji: "🐼" },
  { id: "cute-koala", name: "考拉", url: "/assets/images/小狗.png", emoji: "🐨" },
  { id: "cute-penguin", name: "企鹅", url: "/assets/images/企鹅封面.png", emoji: "🐧" },
];

function mapAvatarsWithLock(unlockedList) {
  const unlocked = new Set(unlockedList && unlockedList.length ? unlockedList : ["cute-dog"]);
  return MASCOT_AVATARS_ALL.map((m) => ({
    ...m,
    url: toMiniprogramAssetUrl(m.url),
    locked: !unlocked.has(m.id),
  }));
}

const PERSONA_TO_MASCOT = {
  default: "cute-dog",
  cute_fox: "cute-fox",
  cute_dino: "cute-dino",
  cute_cat: "cute-cat",
  cute_bunny: "cute-bunny",
  cute_squirrel: "cute-squirrel",
  cute_chick: "cute-chick",
  cute_panda: "cute-panda",
  cute_koala: "cute-koala",
  cute_penguin: "cute-penguin",
};

// 完全对齐首页 home 的调参语义：位置X/Y/Z + 缩放 + 旋转Y
const HOME_TUNING_BASE_TARGET_SIZE = 3.0;
const HOME_TUNING_BASE_LIFT_MUL = 0.1;
const HOME_TUNING_LIFT_MUL_MIN = -100.0;
const HOME_TUNING_LIFT_MUL_MAX = 2.0;
const HOME_TUNING_DEFAULTS = {
  fov: 45,
  camDistMul: 1.2,
  camHeightMul: 0.18,
  lookAtHeightMul: 0.12,
};

Page({
  data: {
    companionName: "柴柴小星",
    welcomeText: buildWelcomeText("柴柴小星"),
    modelHint: "3D形象按选中伙伴与 catalog 加载",
    modelUrl: "",
    modelLoading: false,
    companionForceLoadCover: false,
    modelReady: false,
    modelFailed: false,
    modelLoadScene: "repair",
    modelLoadProgress: 0,
    modelLoadStageText: "魔法准备中…",
    modelMagicCount: 0,
    quickReplies: QUICK_REPLIES,
    chatInput: "",
    chatLoading: false,
    chatList: [],
    isTypingReply: false,
    typingReplyText: "",
    chatMoodClass: "mood-default",
    liveQuickReplies: QUICK_REPLIES,
    speechHint: "",
    chatScrollInto: "",
    companionSessionId: "",
    isRecording: false,
    recordHint: "按住说话",
    audioWaveActive: false,
    avatarOptions: AVATAR_OPTIONS,
    selectedPersonaId: "default",
    selectedMascotId: "cute-dog",
    currentMascotEmoji: "🐶",
    mascotWallpaperUrl: toMiniprogramAssetUrl("/assets/images/小狗.png"),

    // 首页同款 3D 调参（开发用）
    showTuning: false,
    homeTunePosX: 0,
    homeTunePosY: 0,
    homeTunePosYText: "0",
    homeTunePosZ: 0,
    homeTuneScalePct: 100,
    homeTuneRotY: 0,

    showCompanionSwitchModal: false,
    companionSwitchStep: "menu",
    mascotAvatarsForSwitch: [],
    companionUnlockedFormTiers: [1],
    companionSwitchPosterMascot: {
      id: "cute-dog",
      name: "柴小汪",
      url: toMiniprogramAssetUrl("/assets/images/柴犬封面.png"),
    },
    companionThreeSwitching: false,
    /** 当前 3D 形态键，与后端 form_key（egg / tier1–3）一致；保存调参依赖此字段 */
    companionFormKey: "",
  },

  onLoad() {
    this._hasUserMessagedThisChat = false;
    this._redirectFormalUserIfEggOnly(() => {
      this.enforceEggUnlockThen(() => {
        this.applyPersonaFromHomeSelection(() => {
          this.loadHomeTuningFromStorage(() => {
            this._initRecorder();
            this.setData({
              chatList: [{ role: "assistant", text: this.data.welcomeText }],
              liveQuickReplies: QUICK_REPLIES,
            });
            this.createCompanionSession();
            this.syncCompanion3DFromGlobal();
            setTimeout(() => this._scrollChatToBottom(), 120);
          });
        });
      });
    });
  },

  onShow() {
    this._redirectFormalUserIfEggOnly(() => {
      this.enforceEggUnlockThen(() => {
        this.applyPersonaFromHomeSelection(() => {
          if (this.data.companionSessionId) {
            this.syncCompanion3DFromGlobal();
          } else {
            this.createCompanionSession();
            this.syncCompanion3DFromGlobal();
          }
        });
      });
    });
  },

  _redirectFormalUserIfEggOnly(done) {
    const uid = getCompanionScopeUserId();
    if (isGuestCompanionUserId(uid)) {
      if (typeof done === "function") done();
      return;
    }
    requestCompanionState("cute-dog")
      .then((state) => {
        const d =
          state && typeof state === "object"
            ? state.data && typeof state.data === "object"
              ? state.data
              : state
            : {};
        if (d.egg_model_active) {
          wx.showToast({ title: "请先孵化蛋蛋后再来找小伙伴哦", icon: "none", duration: 2200 });
          setTimeout(() => {
            wx.redirectTo({ url: "/pages/pet-system/pet-system" });
          }, 80);
          return;
        }
        if (typeof done === "function") done();
      })
      .catch(() => {
        if (typeof done === "function") done();
      });
  },

  enforceEggUnlockThen(done) {
    requestEggState()
      .then((data) => {
        const ok = new Set(data.unlocked_mascot_ids || ["cute-dog"]);
        let mid = "";
        try {
          mid = String(wx.getStorageSync("selectedMascot") || "").trim();
        } catch (e) {}
        if (!mid || !ok.has(mid)) {
          const hadInvalid = !!(mid && !ok.has(mid));
          try {
            wx.setStorageSync("selectedMascot", "cute-dog");
          } catch (e2) {}
          if (hadInvalid) {
            wx.showToast({ title: "未解锁的伙伴不能在伴读中使用", icon: "none" });
          }
        }
        if (typeof done === "function") done();
      })
      .catch(() => {
        if (typeof done === "function") done();
      });
  },

  goToPetSystem() {
    wx.navigateTo({ url: "/pages/pet-system/pet-system" });
  },

  _persistCompanionHomeSelection(mascotId, formKey) {
    try {
      const mid = String(mascotId || "").trim();
      const fk = String(formKey || "").trim();
      if (mid) wx.setStorageSync("selectedMascot", mid);
      if (fk) wx.setStorageSync("selectedMascotFormKey", fk);
      wx.setStorageSync("selectedMascotUpdatedAt", Date.now());
      if (app && app.globalData) {
        if (mid) app.globalData.selectedMascot = mid;
        if (fk) app.globalData.selectedMascotFormKey = fk;
        app.globalData.selectedMascotUpdatedAt = Date.now();
      }
    } catch (e) {}
  },

  _refreshCompanionSwitchAvatars() {
    requestEggState()
      .then((data) => {
        const unlocked = data.unlocked_mascot_ids || ["cute-dog"];
        this.setData({ mascotAvatarsForSwitch: mapAvatarsWithLock(unlocked) });
      })
      .catch(() => {
        this.setData({ mascotAvatarsForSwitch: mapAvatarsWithLock(["cute-dog"]) });
      });
  },

  syncCompanion3DFromGlobal() {
    let mascotId = "cute-dog";
    try {
      mascotId = String(wx.getStorageSync("selectedMascot") || "").trim() || mascotId;
    } catch (e) {}
    let preferredFormKey = String(wx.getStorageSync("selectedMascotFormKey") || "").trim();
    this.setData({ companionThreeSwitching: true });
    requestCompanionState(mascotId)
      .then((state) => {
        const d = state && typeof state === "object" ? (state.data && typeof state.data === "object" ? state.data : state) : {};
        const rawPet =
          d.form_view_tuning && typeof d.form_view_tuning === "object" && !Array.isArray(d.form_view_tuning)
            ? d.form_view_tuning
            : {};
        const rawHome =
          d.form_view_tuning_home && typeof d.form_view_tuning_home === "object" && !Array.isArray(d.form_view_tuning_home)
            ? d.form_view_tuning_home
            : {};
        const rawCmp =
          d.form_view_tuning_companion &&
          typeof d.form_view_tuning_companion === "object" &&
          !Array.isArray(d.form_view_tuning_companion)
            ? d.form_view_tuning_companion
            : {};
        // 伴读专用条目不设时，依次回退 home / pet_detail，便于首次升级前后观感连续；保存只写 companion
        this._companionServerFormViewTuning = { ...rawPet, ...rawHome, ...rawCmp };
        let eggActive = !!d.egg_model_active;
        let displayTier = Math.max(1, Math.min(3, Number(d.display_form_tier || 1) || 1));
        const guestUid = isGuestCompanionUserId(getCompanionScopeUserId());
        if (!guestUid && eggActive) {
          preferredFormKey = "egg";
          try {
            wx.setStorageSync("selectedMascotFormKey", "egg");
            if (app && app.globalData) app.globalData.selectedMascotFormKey = "egg";
          } catch (e2) {}
        }
        if (preferredFormKey === "egg") {
          if (guestUid || !!d.egg_model_active) eggActive = true;
        } else if (/^tier[123]$/.test(preferredFormKey)) {
          eggActive = false;
          displayTier = Math.max(1, Math.min(3, Number(preferredFormKey.replace("tier", "")) || 1));
        }
        let unlocked = Array.isArray(d.unlocked_form_tiers) && d.unlocked_form_tiers.length ? d.unlocked_form_tiers : [1];
        unlocked = [...new Set(unlocked.map((n) => Math.max(1, Math.min(3, Number(n) || 1))))].sort((a, b) => a - b);
        const pet = getPetById(mascotId);
        if (!pet) throw new Error("unknown pet");
        const formKey = eggActive ? "egg" : `tier${displayTier}`;
        const rawMap = this._companionServerFormViewTuning || {};
        const slot = rawMap && typeof rawMap === "object" ? (rawMap[formKey] || rawMap) : {};
        const tuning = slot && slot.tuning && typeof slot.tuning === "object" ? slot.tuning : slot;
        if (tuning && typeof tuning === "object" && Object.keys(tuning).length) {
          this._serverCompanionTuning = { ...tuning };
        } else {
          this._serverCompanionTuning = {};
        }
        this._loadHomeTuningFromServer({ applyStoredPosition: true });
        let modelRel = getFormTierModelUrl(pet, displayTier);
        if (eggActive) {
          modelRel = getStaticEggModelUrl(pet) || getEggModelUrl(pet) || modelRel;
        }
        const modelUrl = resolveModelUrl(modelRel);
        if (!modelUrl) throw new Error("empty model url");
        const hit = MASCOT_TO_PERSONA[mascotId] || MASCOT_TO_PERSONA["cute-dog"];
        const av = MASCOT_AVATARS_ALL.find((x) => x.id === mascotId) || MASCOT_AVATARS_ALL[0];
        const displayName = hit.displayName || "小伙伴";
        const welcome = buildWelcomeText(displayName);
        const patch = {
          selectedMascotId: mascotId,
          selectedPersonaId: hit.personaId,
          companionName: displayName,
          currentMascotEmoji: hit.emoji,
          mascotWallpaperUrl: toMiniprogramAssetUrl(hit.wallpaper),
          modelHint: `形象: ${mascotId} · ${formKey}`,
          modelUrl,
          companionUnlockedFormTiers: unlocked,
          companionSwitchPosterMascot: { id: av.id, name: av.name, url: toMiniprogramAssetUrl(av.url) },
          companionFormKey: formKey,
        };
        const list = this.data.chatList || [];
        if (!this._hasUserMessagedThisChat && list.length === 1 && list[0] && list[0].role === "assistant") {
          patch.chatList = [{ role: "assistant", text: welcome }];
          patch.welcomeText = welcome;
        }
        this.setData(patch, () => {
          this.initThreeRenderer(modelUrl);
          this.migrateLocalTuningToBackendIfNeeded();
        });
      })
      .catch(() => {
        this.loadAvatarConfig();
      })
      .finally(() => {
        this.setData({ companionThreeSwitching: false });
      });
  },

  onCompanionOpenSwitch() {
    this._refreshCompanionSwitchAvatars();
    const mid = this.data.selectedMascotId || "cute-dog";
    const av = MASCOT_AVATARS_ALL.find((x) => x.id === mid) || MASCOT_AVATARS_ALL[0];
    this.setData({
      showCompanionSwitchModal: true,
      companionSwitchStep: "menu",
      companionSwitchPosterMascot: { id: av.id, name: av.name, url: toMiniprogramAssetUrl(av.url) },
    });
  },

  onCompanionCloseSwitch() {
    this.setData({ showCompanionSwitchModal: false, companionSwitchStep: "menu" });
  },

  onCompanionSwitchPickMascot() {
    this.setData({ companionSwitchStep: "mascot" });
  },

  onCompanionSwitchPickForm() {
    const mid = this.data.selectedMascotId || "cute-dog";
    const av = MASCOT_AVATARS_ALL.find((x) => x.id === mid) || MASCOT_AVATARS_ALL[0];
    this.setData({
      companionSwitchStep: "form",
      companionSwitchPosterMascot: { id: av.id, name: av.name, url: toMiniprogramAssetUrl(av.url) },
    });
  },

  onCompanionSwitchBack() {
    this.setData({ companionSwitchStep: "menu" });
  },

  onCompanionSelectMascotFromModal(e) {
    const mascot = e && e.currentTarget && e.currentTarget.dataset ? e.currentTarget.dataset.mascot : null;
    if (!mascot || mascot.locked) return;
    let fk = "tier1";
    try {
      const curFk = String(wx.getStorageSync("selectedMascotFormKey") || "").trim();
      if (curFk) fk = curFk;
    } catch (err) {}
    this._persistCompanionHomeSelection(mascot.id, fk);
    this.setData({ showCompanionSwitchModal: false, companionSwitchStep: "menu" }, () => {
      this.createCompanionSession();
      this.syncCompanion3DFromGlobal();
    });
  },

  onCompanionSelectFormTier(e) {
    const tier = Number(e && e.currentTarget && e.currentTarget.dataset ? e.currentTarget.dataset.tier : 0);
    if (!tier) return;
    const unlocked = new Set((this.data.companionUnlockedFormTiers || []).map((n) => Number(n)));
    if (!unlocked.has(tier)) return;
    const mid = this.data.selectedMascotId || "cute-dog";
    const fk = `tier${tier}`;
    this._persistCompanionHomeSelection(mid, fk);
    this.setData({ showCompanionSwitchModal: false, companionSwitchStep: "menu" }, () => {
      this.syncCompanion3DFromGlobal();
    });
    postCompanionSetDisplayForm(mid, tier).catch(() => {});
  },

  onCompanionTips() {
    wx.showModal({
      title: "小提示",
      content: "按住说话、打字或点快捷语都能和我聊天。点右侧「切换模型」可打开与首页相同的小伙伴/形态选择。更多玩法可在「指南」里查看～",
      showCancel: false,
    });
  },

  onCompanionGuide() {
    wx.navigateTo({ url: "/pages/pet-system/pet-system" });
  },

  onUnload() {
    this.destroyThreeRenderer();
    this.setInteractionActive(false);
    if (this.recorderManager) {
      this.recorderManager.stop();
    }
    if (this.innerAudioContext) {
      this.innerAudioContext.destroy();
      this.innerAudioContext = null;
    }
    if (this._typingTimer) {
      clearInterval(this._typingTimer);
      this._typingTimer = null;
    }
  },

  createCompanionSession() {
    const personaId = this.data.selectedPersonaId || "default";
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/session/create`,
      method: "POST",
      data: { user_id: getCompanionScopeUserId(), persona_id: personaId },
      success: (res) => {
        const statusCode = Number(res?.statusCode || 0);
        if (statusCode < 200 || statusCode >= 300) {
          wx.showToast({ title: "陪伴服务异常", icon: "none" });
          return;
        }
        const sid = res?.data?.session_id || "";
        if (sid) {
          this.setData({ companionSessionId: sid });
          this.wakeupCompanion();
          return;
        }
        wx.showToast({ title: "会话创建失败", icon: "none" });
      },
      fail: () => wx.showToast({ title: "陪伴服务连接失败", icon: "none" }),
    });
  },

  loadAvatarConfig() {
    const personaId = this.data.selectedPersonaId || "default";
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/avatar/scene_config?persona_id=${encodeURIComponent(personaId)}&user_id=${encodeURIComponent(getCompanionScopeUserId())}&scene_key=${encodeURIComponent(COMPANION_SCENE_KEY)}`,
      method: "GET",
      success: (res) => {
        const data = res?.data || {};
        const relModelUrl = String(data.model_url || "").trim();
        const serverPreset = (data.camera_preset && typeof data.camera_preset === "object" && !Array.isArray(data.camera_preset))
          ? data.camera_preset
          : null;
        const modelUrl = relModelUrl
          ? (relModelUrl.startsWith("http") ? relModelUrl : `${getApiBaseUrl()}${relModelUrl}`)
          : "";
        this._serverCompanionTuning = serverPreset || {};
        const displayName = data.display_name || this.data.companionName || "小伙伴";
        const welcome = buildWelcomeText(displayName);
        const patch = {
          companionName: displayName,
          welcomeText: welcome,
          modelHint: `3D形象资源: ${relModelUrl || "(empty)"}`,
          modelUrl,
        };
        const list = this.data.chatList || [];
        if (!this._hasUserMessagedThisChat && list.length === 1 && list[0] && list[0].role === "assistant") {
          patch.chatList = [{ role: "assistant", text: welcome }];
        }
        this.setData(patch);
        this._loadHomeTuningFromServer({ applyStoredPosition: true });
        if (modelUrl) {
          this.initThreeRenderer(modelUrl);
        }
        // 若后端当前还是 preset 且本地有历史缓存，自动迁移一次到后端
        if (data.tuning_source !== "user" && data.tuning_source !== "user_scene") {
          this.migrateLocalTuningToBackendIfNeeded();
        }
      },
      fail: () => {
        this.loadAvatarConfigFallback();
      },
    });
  },

  loadAvatarConfigFallback() {
    const personaId = this.data.selectedPersonaId || "default";
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/avatar/config?persona_id=${encodeURIComponent(personaId)}&user_id=${encodeURIComponent(getCompanionScopeUserId())}`,
      method: "GET",
      success: (res) => {
        const data = res?.data || {};
        const relModelUrl = String(data.model_url || "").trim();
        const serverPreset = (data.camera_preset && typeof data.camera_preset === "object" && !Array.isArray(data.camera_preset))
          ? data.camera_preset
          : null;
        const modelUrl = relModelUrl
          ? (relModelUrl.startsWith("http") ? relModelUrl : `${getApiBaseUrl()}${relModelUrl}`)
          : "";
        this._serverCompanionTuning = serverPreset || {};
        const displayName = data.display_name || this.data.companionName || "小伙伴";
        const welcome = buildWelcomeText(displayName);
        const patch = {
          companionName: displayName,
          welcomeText: welcome,
          modelHint: `3D形象资源: ${relModelUrl || "(empty)"}`,
          modelUrl,
        };
        const list = this.data.chatList || [];
        if (!this._hasUserMessagedThisChat && list.length === 1 && list[0] && list[0].role === "assistant") {
          patch.chatList = [{ role: "assistant", text: welcome }];
        }
        this.setData(patch);
        this._loadHomeTuningFromServer({ applyStoredPosition: true });
        if (modelUrl) this.initThreeRenderer(modelUrl);
      },
      fail: () => {},
    });
  },

  initThreeRenderer(modelUrl) {
    this._threeLoadToken = (this._threeLoadToken || 0) + 1;
    const loadToken = this._threeLoadToken;
    // 与 pet-detail 一致：先停掉 rAF。否则加载态仍为 true 时可能已向 WebGL 提交新模型帧，原生层会穿透普通 view 遮罩叠在魔法动画上
    this._threeLoopActive = false;
    this._stopModelProgressFake();
    this.setData(
      {
        modelLoading: true,
        companionForceLoadCover: false,
        modelFailed: false,
        modelReady: false,
        modelLoadScene: "repair",
        modelLoadProgress: 0,
        modelLoadStageText: "魔法准备中…",
        modelMagicCount: 0,
      },
      () => {
        this._startModelProgressFake(loadToken);
        this._queryCompanionThreeCanvas(String(modelUrl || "").trim(), loadToken, 0);
      }
    );
  },

  _queryCompanionThreeCanvas(modelUrl, loadToken, attempt) {
    if (!modelUrl) {
      this._stopModelProgressFake();
      this.setData({ modelLoading: false, modelFailed: true, companionForceLoadCover: false });
      return;
    }
    wx.createSelectorQuery()
      .select("#threeCanvas")
      .node()
      .exec((res) => {
        const node = res && res[0] ? res[0].node : null;
        if (!node) {
          if (attempt < 12) {
            setTimeout(() => this._queryCompanionThreeCanvas(modelUrl, loadToken, attempt + 1), 50);
            return;
          }
          this._stopModelProgressFake();
          this.setData({ modelLoading: false, modelFailed: true, companionForceLoadCover: false });
          return;
        }
        try {
          if (!createScopedThreejs || !registerGLTFLoader) {
            throw new Error(`three static import failed: ${THREE_IMPORT_ERROR || "unknown"}`);
          }
          const metrics = getWindowMetrics();
          const pixelRatio = metrics.pixelRatio || 1;
          const width = Math.max(160, Math.round((360 / 750) * metrics.windowWidth));
          const height = Math.max(180, Math.round((404 / 750) * metrics.windowWidth));
          node.width = width * pixelRatio;
          node.height = height * pixelRatio;

          let THREE = this._threeTHREE;
          let renderer = this._threeRenderer;
          let scene = this._threeScene;
          let camera = this._threeCamera;
          const firstBoot = !THREE || !renderer || !scene || !camera;

          if (firstBoot) {
            THREE = createScopedThreejs(node);
            registerGLTFLoader(THREE);
            renderer = new THREE.WebGLRenderer({ canvas: node, antialias: true, alpha: true });
            renderer.setClearColor(0x000000, 0);
            scene = new THREE.Scene();
            scene.background = null;
            camera = new THREE.PerspectiveCamera(HOME_TUNING_DEFAULTS.fov, width / height, 0.01, 2000);
            camera.position.set(0, 0.8, 3.8);
            scene.add(new THREE.HemisphereLight(0xffffff, 0x666666, 1.2));
            const dir = new THREE.DirectionalLight(0xffffff, 1.1);
            dir.position.set(4, 6, 4);
            scene.add(dir);
            this._threeTHREE = THREE;
            this._threeRenderer = renderer;
            this._threeScene = scene;
            this._threeCamera = camera;
          }

          this._threeCanvasNode = node;
          renderer.setPixelRatio(pixelRatio);
          renderer.setSize(width, height);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();

          this._detachCurrentThreeModel();
          const loader = new THREE.GLTFLoader();
          const candidates = [modelUrl];
          if (modelUrl.endsWith(".gltf")) {
            candidates.push(modelUrl.replace(/\.gltf$/i, ".glb"));
          }
          let lastErr = "";
          const tryLoad = (idx) => {
            if (loadToken !== this._threeLoadToken) return;
            if (idx >= candidates.length) {
              this._stopModelProgressFake();
              this.setData({ modelLoading: false, modelFailed: true, companionForceLoadCover: false });
              return;
            }
            const url = candidates[idx];
            loader.load(
              url,
              (gltf) => {
                if (loadToken !== this._threeLoadToken) {
                  const stale = gltf.scene || gltf.scenes?.[0];
                  if (stale) this._disposeThreeObjectTree(stale);
                  return;
                }
                const root = gltf.scene || gltf.scenes?.[0];
                if (!root) {
                  lastErr = `empty scene from ${url}`;
                  if (loadToken === this._threeLoadToken) tryLoad(idx + 1);
                  return;
                }
                if (loadToken !== this._threeLoadToken) {
                  this._disposeThreeObjectTree(root);
                  return;
                }
                this._detachCurrentThreeModel();
                // Auto-fit model into camera view to avoid clipping/cut-off.
                const box = new THREE.Box3().setFromObject(root);
                const size = box.getSize(new THREE.Vector3());
                const center = box.getCenter(new THREE.Vector3());
                const maxDim = Math.max(size.x, size.y, size.z) || 1;
                this._fitMaxDim = maxDim;
                this._fitBaseY = null;
                this._fitBaseScale = 1 / maxDim;

                // Move model center to origin.
                root.position.set(-center.x, -center.y, -center.z);

                // 基准尺度：后续调参始终基于这套“初始位姿”绝对计算，避免二次叠加漂移。
                root.scale.set(this._fitBaseScale, this._fitBaseScale, this._fitBaseScale);
                this._fitScale = this._fitBaseScale;
                this._userScale = 1;
                this._userRotX = 0;
                this._userRotY = 0;
                // 默认朝向：小鸭模型初始转到面朝用户，其余保持原朝向。
                const defaultBaseRotY = (this.data.selectedPersonaId === "cute_chick" || this.data.selectedPersonaId === "cute_dino") ? -90 : 0;
                const deg = Number(this.data.homeTuneRotY);
                const baseDeg = Number.isFinite(deg) ? deg : defaultBaseRotY;
                this._baseRotY = (baseDeg * Math.PI) / 180;
                this._idleMotion = {
                  active: false,
                  startAt: 0,
                  durationMs: 0,
                  ampX: 0,
                  ampY: 0,
                  nextAt: Date.now() + 3500,
                };

                // Recalculate bounds after scale and recenter.
                const fitBox = new THREE.Box3().setFromObject(root);
                const fitSize = fitBox.getSize(new THREE.Vector3());
                const fitCenter = fitBox.getCenter(new THREE.Vector3());
                root.position.set(root.position.x - fitCenter.x, root.position.y - fitCenter.y, root.position.z - fitCenter.z);
                this._fitBasePos = { x: root.position.x, y: root.position.y, z: root.position.z };
                this._fitBaseSizeY = fitSize.y;
                // 与首页 _buildHomeThreeScene 一致：先不把 root 挂进 scene，等 setData 关掉加载态后再 add，避免 WebGL 已画出一帧却仍在「解封」遮罩下
                this._threeRoot = null;
                this._threeMixer = null;
                this._threeLastTickMs = Date.now();
                const clips = Array.isArray(gltf.animations) ? gltf.animations : [];
                if (clips.length > 0 && THREE.AnimationMixer) {
                  try {
                    const mixer = new THREE.AnimationMixer(root);
                    // 更接近“单个形象动作预览”：优先播放 idle 之类的 clip
                    const preferredIdx = clips.findIndex((c) => {
                      const name = (c && c.name) ? String(c.name) : "";
                      return /idle/i.test(name) || /stand/i.test(name);
                    });
                    const clipIdx = preferredIdx >= 0 ? preferredIdx : 0;
                    const preferredClip = clips[clipIdx];
                    const action = preferredClip ? mixer.clipAction(preferredClip) : null;
                    if (action) {
                      action.enabled = true;
                      action.setLoop(THREE.LoopRepeat);
                      action.setEffectiveWeight(1);
                      action.play();
                    }
                    this._threeMixer = mixer;
                    this._idleMotion = null;
                  } catch (mixerErr) {}
                }
                if (loadToken !== this._threeLoadToken) {
                  this._disposeThreeObjectTree(root);
                  this._threeRoot = null;
                  this._threeMixer = null;
                  return;
                }
                this._stopModelProgressFake();
                this.setData(
                  {
                    modelLoading: false,
                    companionForceLoadCover: true,
                    modelReady: true,
                    modelFailed: false,
                    modelLoadProgress: 100,
                    modelLoadStageText: "加载完成",
                  },
                  () => {
                    if (loadToken !== this._threeLoadToken) {
                      try {
                        scene.remove(root);
                      } catch (eRm) {}
                      this._disposeThreeObjectTree(root);
                      this._threeRoot = null;
                      this._threeMixer = null;
                      return;
                    }
                    try {
                      scene.add(root);
                    } catch (eAdd) {}
                    this._threeRoot = root;
                    this._applyHomeTuningToRoot();
                    this._startThreeRenderLoop();
                    if (this._companionRevealTimer) {
                      clearTimeout(this._companionRevealTimer);
                      this._companionRevealTimer = null;
                    }
                    this._companionRevealTimer = setTimeout(() => {
                      this._companionRevealTimer = null;
                      if (loadToken !== this._threeLoadToken) return;
                      this.setData({ companionForceLoadCover: false }, () => {
                        this._resizeCompanionThreeCanvasIfNeeded();
                      });
                    }, 168);
                  }
                );
              },
              (xhr) => {
                this._syncCompanionModelLoadProgressFromXhr(xhr, loadToken);
              },
              (err) => {
                if (loadToken !== this._threeLoadToken) return;
                const msg = (err && (err.message || err.errMsg)) || JSON.stringify(err || {});
                lastErr = `${url} => ${msg}`;
                tryLoad(idx + 1);
              }
            );
          };
          tryLoad(0);
        } catch (e) {
          this._stopModelProgressFake();
          this.setData({ modelLoading: false, modelFailed: true, companionForceLoadCover: false });
        }
      });
  },

  _resizeCompanionThreeCanvasIfNeeded() {
    const node = this._threeCanvasNode;
    const renderer = this._threeRenderer;
    const camera = this._threeCamera;
    if (!node || !renderer || !camera) return;
    try {
      const metrics = getWindowMetrics();
      const pixelRatio = metrics.pixelRatio || 1;
      const width = Math.max(160, Math.round((360 / 750) * metrics.windowWidth));
      const height = Math.max(180, Math.round((404 / 750) * metrics.windowWidth));
      node.width = width * pixelRatio;
      node.height = height * pixelRatio;
      renderer.setPixelRatio(pixelRatio);
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    } catch (e) {}
  },

  destroyThreeRenderer() {
    if (this._companionRevealTimer) {
      clearTimeout(this._companionRevealTimer);
      this._companionRevealTimer = null;
    }
    this.setData({ companionForceLoadCover: false });
    this._threeLoadToken = (this._threeLoadToken || 0) + 1;
    this._stopModelProgressFake();
    this._detachCurrentThreeModel();
    this._threeLoopActive = false;
    if (this._threeRenderer) {
      try {
        this._threeRenderer.dispose();
      } catch (e) {}
    }
    this._threeTHREE = null;
    this._threeRenderer = null;
    this._threeScene = null;
    this._threeCamera = null;
    this._threeCanvasNode = null;
    this._threeRoot = null;
    this._threeMixer = null;
    this._threeLastTickMs = 0;
    this._baseRotY = 0;
    this._threeFit = null;
    this._fitMaxDim = 0;
    this._fitBaseY = null;
    this._fitBaseScale = 0;
    this._fitBasePos = null;
    this._fitBaseSizeY = 0;
    this._mixerPulse = null;
    if (this._interactionTimer) {
      clearTimeout(this._interactionTimer);
      this._interactionTimer = null;
    }
    this._touchMode = "";
    this._lastTouchX = 0;
    this._lastTouchY = 0;
    this._pinchStartDistance = 0;
    this._pinchStartScale = 1;
    this._idleMotion = null;
  },

  _detachCurrentThreeModel() {
    const scene = this._threeScene;
    const root = this._threeRoot;
    if (scene && root) {
      try {
        scene.remove(root);
      } catch (e) {}
      try {
        root.traverse((obj) => {
          if (!obj || !obj.isMesh) return;
          try {
            if (obj.geometry && obj.geometry.dispose) obj.geometry.dispose();
          } catch (e2) {}
          try {
            if (obj.material) {
              if (Array.isArray(obj.material)) obj.material.forEach((m) => m && m.dispose && m.dispose());
              else if (obj.material.dispose) obj.material.dispose();
            }
          } catch (e3) {}
        });
      } catch (e4) {}
    }
    this._threeRoot = null;
    this._threeMixer = null;
  },

  _disposeThreeObjectTree(root) {
    if (!root) return;
    try {
      root.traverse((obj) => {
        if (!obj || !obj.isMesh) return;
        try {
          if (obj.geometry && obj.geometry.dispose) obj.geometry.dispose();
        } catch (e2) {}
        try {
          if (obj.material) {
            if (Array.isArray(obj.material)) obj.material.forEach((m) => m && m.dispose && m.dispose());
            else if (obj.material.dispose) obj.material.dispose();
          }
        } catch (e3) {}
      });
    } catch (e4) {}
  },

  _stopModelProgressFake() {
    if (this._modelProgressFakeTimer) {
      clearInterval(this._modelProgressFakeTimer);
      this._modelProgressFakeTimer = null;
    }
    this._modelProgressFakeToken = null;
    this._modelProgressFakeValue = 0;
  },

  _startModelProgressFake(token) {
    this._modelProgressFakeToken = token;
    this._modelProgressFakeValue = 6;
    this.setData({ modelLoadProgress: 6, modelLoadStageText: "魔法准备中…" });

    if (this._modelProgressFakeTimer) clearInterval(this._modelProgressFakeTimer);
    this._modelProgressFakeTimer = setInterval(() => {
      if (this._modelProgressFakeToken !== token) return;
      const cur = Number(this.data.modelLoadProgress || 0);
      const base = Math.max(this._modelProgressFakeValue || 0, cur);
      const step = 0.9 + Math.random() * 1.4;
      const next = Math.min(98, base + step);
      this._modelProgressFakeValue = next;
      this.setData({
        modelLoadProgress: Math.floor(next * 10) / 10,
        modelLoadStageText: next > 55 ? "模型处理中…" : "魔法正在解封…",
      });
      if (next >= 98) this._stopModelProgressFake();
    }, 120);
  },

  _syncCompanionModelLoadProgressFromXhr(xhr, token) {
    if (token !== this._threeLoadToken) return;
    const loaded =
      Number(xhr && (typeof xhr.loaded === "number" ? xhr.loaded : xhr.loadedBytes)) || 0;
    const total = Number(xhr && (typeof xhr.total === "number" ? xhr.total : xhr.totalBytes)) || 0;
    if (!total || total <= 0) return;
    let percent = (loaded / total) * 100;
    if (!Number.isFinite(percent)) return;
    percent = Math.max(0, Math.min(99, percent));
    this._modelProgressFakeToken = token;
    this._modelProgressFakeValue = Math.max(this._modelProgressFakeValue || 0, percent);
    this.setData({
      modelLoadProgress: Math.floor(percent * 10) / 10,
      modelLoadStageText: percent > 55 ? "模型处理中…" : "魔法正在解封…",
    });
    if (percent >= 98) this._stopModelProgressFake();
  },

  onModelMagicTap() {
    if (!this.data.modelLoading && !this.data.modelFailed) return;
    const nextCount = Number(this.data.modelMagicCount || 0) + 1;
    const curP = Number(this.data.modelLoadProgress || 0);
    const bump = 3 + Math.min(10, nextCount * 1.1);
    const nextP = Math.min(98, Math.max(curP, curP + bump));
    this.setData({
      modelMagicCount: nextCount,
      modelLoadProgress: Math.floor(nextP * 10) / 10,
      modelLoadStageText: nextCount % 3 === 0 ? "小魔法命中！" : "点点加速中…",
    });
    if (this.data.modelFailed) {
      this.retryModelLoad();
    }
  },

  _startThreeRenderLoop() {
    if (this._threeLoopActive) return;
    this._threeLoopActive = true;
    const tick = () => {
      if (!this._threeLoopActive || !this._threeRenderer || !this._threeScene || !this._threeCamera || !this._threeCanvasNode) {
        this._threeLoopActive = false;
        return;
      }
      if (this._threeRoot) {
        if (this._threeMixer) {
          this.updateMixerMotionState();
          const now = Date.now();
          const dt = Math.max(0, Math.min((now - (this._threeLastTickMs || now)) / 1000, 0.05));
          this._threeLastTickMs = now;
          this._threeMixer.update(dt);
        } else {
          this.updateIdleMotion();
        }
        this._threeRenderer.render(this._threeScene, this._threeCamera);
      }
      this._threeCanvasNode.requestAnimationFrame(tick);
    };
    this._threeCanvasNode.requestAnimationFrame(tick);
  },

  onCanvasTouchStart(e) {
    const touches = (e && e.touches) || [];
    if (!this._threeRoot) return;
    if (touches.length >= 2) {
      this._touchMode = "pinch";
      this._pinchStartDistance = this.getTouchDistance(touches[0], touches[1]);
      this._pinchStartScale = this._userScale || 1;
      this.pauseIdleMotion();
      return;
    }
    if (touches.length === 1) {
      this._touchMode = "rotate";
      this._lastTouchX = touches[0].x;
      this._lastTouchY = touches[0].y;
      this.pauseIdleMotion();
    }
  },

  onCanvasTouchMove(e) {
    const touches = (e && e.touches) || [];
    if (!this._threeRoot) return;
    if (this._touchMode === "pinch" && touches.length >= 2) {
      const dist = this.getTouchDistance(touches[0], touches[1]);
      const start = this._pinchStartDistance || dist || 1;
      const ratio = dist / start;
      const nextScale = (this._pinchStartScale || 1) * ratio;
      this._userScale = this.clamp(nextScale, 0.6, 2.4);
      this.applyModelTransform();
      return;
    }
    if (this._touchMode === "rotate" && touches.length === 1) {
      const x = touches[0].x;
      const y = touches[0].y;
      const dx = x - this._lastTouchX;
      const dy = y - this._lastTouchY;
      this._lastTouchX = x;
      this._lastTouchY = y;
      this._userRotY = (this._userRotY || 0) + dx * 0.012;
      this._userRotX = this.clamp((this._userRotX || 0) + dy * 0.008, -0.55, 0.55);
      this.applyModelTransform();
    }
  },

  onCanvasTouchEnd() {
    this._touchMode = "";
  },

  applyModelTransform() {
    if (!this._threeRoot) return;
    const s = (this._fitScale || 1) * (this._userScale || 1);
    this._threeRoot.scale.set(s, s, s);
    this._threeRoot.rotation.y = (this._baseRotY || 0) + (this._userRotY || 0);
    this._threeRoot.rotation.x = this._userRotX || 0;
  },

  getTouchDistance(a, b) {
    const dx = (a.x || 0) - (b.x || 0);
    const dy = (a.y || 0) - (b.y || 0);
    return Math.sqrt(dx * dx + dy * dy);
  },

  clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  },

  applyPersonaFromHomeSelection(done) {
    let mascotId = "cute-dog";
    try {
      const cached = String(wx.getStorageSync("selectedMascot") || "").trim();
      if (cached) mascotId = cached;
    } catch (e) {}
    const hit = MASCOT_TO_PERSONA[mascotId] || MASCOT_TO_PERSONA["cute-dog"];
    const prevPid = this.data.selectedPersonaId;
    const displayName = hit.displayName || this.data.companionName || "小伙伴";
    const welcome = buildWelcomeText(displayName);
    const patch = {
      selectedMascotId: mascotId,
      selectedPersonaId: hit.personaId,
      companionName: displayName,
      welcomeText: welcome,
      currentMascotEmoji: hit.emoji || "🐶",
      mascotWallpaperUrl: toMiniprogramAssetUrl(hit.wallpaper || "/assets/images/小狗.png"),
    };
    if (prevPid !== hit.personaId) {
      this._hasUserMessagedThisChat = false;
      patch.chatList = [{ role: "assistant", text: welcome }];
    }
    this.setData(patch, () => {
      if (typeof done === "function") done();
    });
  },

  pauseIdleMotion() {
    if (!this._idleMotion) return;
    this._idleMotion.active = false;
    this._idleMotion.nextAt = Date.now() + 3000;
  },

  updateIdleMotion() {
    const root = this._threeRoot;
    const motion = this._idleMotion;
    if (!root || !motion) return;
    if (this._touchMode) return;

    const now = Date.now();
    if (!motion.active && now >= motion.nextAt) {
      motion.active = true;
      motion.startAt = now;
      motion.durationMs = 650 + Math.floor(Math.random() * 550);
      motion.ampX = (Math.random() * 0.06) + 0.02;
      motion.ampY = (Math.random() * 0.12) + 0.05;
    }
    if (!motion.active) return;

    const p = (now - motion.startAt) / motion.durationMs;
    if (p >= 1) {
      motion.active = false;
      motion.nextAt = now + 5000 + Math.floor(Math.random() * 4500);
      this.applyModelTransform();
      return;
    }
    const envelope = Math.sin(Math.PI * p);
    const addX = motion.ampX * envelope;
    const addY = motion.ampY * envelope * Math.sin(2 * Math.PI * p);

    const s = (this._fitScale || 1) * (this._userScale || 1);
    root.scale.set(s, s, s);
    root.rotation.x = (this._userRotX || 0) + addX;
    root.rotation.y = (this._baseRotY || 0) + (this._userRotY || 0) + addY;
  },

  _scrollChatToBottom() {
    this.setData({ chatScrollInto: "chat-anchor-bottom" });
    setTimeout(() => {
      this.setData({ chatScrollInto: "" });
    }, 280);
  },

  onStartNewChat() {
    if (this.data.chatLoading || this.data.isTypingReply) {
      wx.showToast({ title: "等回复结束后再新建吧", icon: "none" });
      return;
    }
    this._hasUserMessagedThisChat = false;
    const w = buildWelcomeText(this.data.companionName);
    this.setData({
      welcomeText: w,
      chatList: [{ role: "assistant", text: w }],
      chatInput: "",
      speechHint: "",
      liveQuickReplies: QUICK_REPLIES,
    });
    this.createCompanionSession();
    setTimeout(() => this._scrollChatToBottom(), 100);
  },

  wakeupCompanion() {
    if (!this.data.companionSessionId) return;
    this.setInteractionActive(true, 2500);
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/session/wakeup`,
      method: "POST",
      data: { session_id: this.data.companionSessionId, wake_word: "你好小伴" },
    });
  },

  onChatInput(e) {
    this.setData({ chatInput: e.detail.value || "" });
  },

  sendInputText() {
    const text = (this.data.chatInput || "").trim();
    if (!text) return;
    this.setData({ chatInput: "" });
    this.sendTextMessage(text);
  },

  tapQuickReply(e) {
    const text = e.currentTarget.dataset.text || "";
    if (text) this.sendTextMessage(text);
  },

  sendTextMessage(text) {
    if (this.data.chatLoading) return;
    this.setInteractionActive(true, 4200);
    const sid = this.data.companionSessionId;
    if (!sid) {
      this.createCompanionSession();
      wx.showToast({ title: "正在唤醒伙伴，再点一次", icon: "none" });
      return;
    }
    this._hasUserMessagedThisChat = true;
    const next = this.data.chatList.concat([{ role: "user", text }]);
    this.setData(
      {
        chatList: next,
        chatLoading: true,
        isTypingReply: false,
        typingReplyText: "",
        speechHint: "让我想一想...",
        chatMoodClass: "mood-default",
        liveQuickReplies: pickContextQuickReplies(text),
      },
      () => this._scrollChatToBottom()
    );
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/chat/text`,
      method: "POST",
      data: { session_id: sid, text, use_tts: true },
      success: (res) => {
        const statusCode = Number(res?.statusCode || 0);
        if (statusCode < 200 || statusCode >= 300) {
          this._handleCompanionBackendChatError(parseCompanionBackendError(res?.data || {}, statusCode));
          return;
        }

        const reply = res?.data?.assistant_text || "我听到啦，我们继续聊～";
        const audioUrl = res?.data?.tts_audio_url || "";
        this.typeAssistantReply(reply, () => {
          this.setData({
            chatLoading: false,
            speechHint: reply.slice(0, 14) || "我来回答你啦～",
            chatMoodClass: detectMoodClass(reply),
          });
          this.playTts(audioUrl);
          reportAmusementParkTaskDone(app, "companion");
        });
      },
      fail: () => {
        this._handleCompanionBackendChatError(parseCompanionBackendError({}, 0, true));
      },
    });
  },

  _handleCompanionBackendChatError(errInfo) {
    const ui = buildCompanionErrorUi(errInfo?.reason || "", errInfo?.message || "");
    const list = (this.data.chatList || []).concat([{ role: "assistant", text: ui.bubble }]);
    this.setData(
      {
        chatList: list,
        chatLoading: false,
        speechHint: ui.hint,
        isTypingReply: false,
        typingReplyText: "",
      },
      () => this._scrollChatToBottom()
    );
    wx.showToast({ title: ui.toast || "请求失败", icon: "none" });
  },

  playTts(audioUrl) {
    const raw = String(audioUrl || "").trim();
    if (!raw || raw.includes("placeholder_reply.wav")) return;
    const finalUrl = raw.startsWith("http") ? raw : `${getApiBaseUrl()}${raw}`;
    if (!this.innerAudioContext) {
      this.innerAudioContext = wx.createInnerAudioContext();
      this.innerAudioContext.onError(() => {
        this.setInteractionActive(false);
        this.setData({ speechHint: "" });
      });
      this.innerAudioContext.onEnded(() => {
        this.setInteractionActive(false);
        setTimeout(() => this.setData({ speechHint: "" }), 300);
      });
    }
    this.setInteractionActive(true, 4500);
    this.setData({ speechHint: "我来说给你听～" });
    this.innerAudioContext.src = finalUrl;
    this.innerAudioContext.play();
  },

  _initRecorder() {
    try {
      this.recorderManager = wx.getRecorderManager();
      this.recorderManager.onStart(() => {
        this.setInteractionActive(true, 3500);
        this.setData({ isRecording: true, audioWaveActive: true, recordHint: "正在听你说...", speechHint: "我在认真听你说话～" });
      });
      this.recorderManager.onStop((res) => {
        this.setData({ isRecording: false, audioWaveActive: false, recordHint: "按住说话", speechHint: "让我想一想..." });
        const tempFilePath = res?.tempFilePath || "";
        if (tempFilePath) {
          this.sendVoiceMessage(tempFilePath);
          return;
        }
        const duration = Math.max(Math.round((res.duration || 0) / 1000), 1);
        this.sendTextMessage(`我刚刚说了一段${duration}秒语音`);
      });
      this.recorderManager.onError(() => {
        this.setInteractionActive(false);
        this.setData({ isRecording: false, audioWaveActive: false, recordHint: "录音失败，请重试", speechHint: "我没听清，再说一次吧～" });
      });
    } catch (e) {}
  },

  startRecord() {
    if (!this.recorderManager || this.data.chatLoading) return;
    this.wakeupCompanion();
    this.recorderManager.start({
      duration: 12000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 96000,
      format: "mp3",
    });
  },

  stopRecord() {
    if (!this.recorderManager || !this.data.isRecording) return;
    this.recorderManager.stop();
  },

  sendVoiceMessage(filePath) {
    if (this.data.chatLoading) return;
    this.setInteractionActive(true, 4200);
    const sid = this.data.companionSessionId;
    if (!sid) {
      this.createCompanionSession();
      wx.showToast({ title: "正在唤醒伙伴，再试一次", icon: "none" });
      return;
    }
    this._hasUserMessagedThisChat = true;
    const next = this.data.chatList.concat([{ role: "user", text: "（语音消息）" }]);
    this.setData(
      { chatList: next, chatLoading: true, speechHint: "收到语音啦，正在理解...", isTypingReply: false, typingReplyText: "" },
      () => this._scrollChatToBottom()
    );
    wx.uploadFile({
      url: `${getApiBaseUrl()}/ar_companion/chat/voice_upload`,
      filePath,
      name: "audio_file",
      formData: {
        session_id: sid,
        use_tts: "true",
        audio_format: "mp3",
      },
      success: (res) => {
        let body = {};
        try {
          body = JSON.parse(res.data || "{}");
        } catch (e) {
          body = {};
        }

        const statusCode = Number(res?.statusCode || 0);
        if (statusCode < 200 || statusCode >= 300) {
          this._handleCompanionBackendChatError(parseCompanionBackendError(body, statusCode));
          return;
        }

        const userText = body.user_text || "（语音已发送）";
        const reply = body.assistant_text || "我听到啦，我们继续聊～";
        const replaced = this.data.chatList.slice(0, -1).concat([{ role: "user", text: userText }]);
        this.setData({ chatList: replaced, liveQuickReplies: pickContextQuickReplies(userText) }, () => this._scrollChatToBottom());
        this.typeAssistantReply(reply, () => {
          this.setData({
            chatLoading: false,
            speechHint: reply.slice(0, 14) || "我来回答你啦～",
            chatMoodClass: detectMoodClass(reply),
          });
          this.playTts(body.tts_audio_url || "");
          reportAmusementParkTaskDone(app, "companion");
        });
      },
      fail: () => {
        this.setInteractionActive(false);
        this._handleCompanionBackendChatError(parseCompanionBackendError({}, 0, true));
      },
    });
  },

  setInteractionActive(active, holdMs = 2800) {
    this._isInteracting = !!active;
    if (this._interactionTimer) {
      clearTimeout(this._interactionTimer);
      this._interactionTimer = null;
    }
    if (active && holdMs > 0) {
      this._interactionTimer = setTimeout(() => {
        this._isInteracting = false;
        this._interactionTimer = null;
      }, holdMs);
    }
  },

  updateMixerMotionState() {
    const mixer = this._threeMixer;
    if (!mixer) return;
    const now = Date.now();
    if (!this._mixerPulse) {
      this._mixerPulse = { activeUntil: 0, nextAt: now + 2600 + Math.floor(Math.random() * 2800) };
    }
    // 交互时动作更明显
    if (this._isInteracting) {
      mixer.timeScale = 1.18;
      return;
    }
    // 非交互时：大部分时间慢速，偶发小脉冲，形成“间歇移动”
    if (now >= this._mixerPulse.nextAt) {
      this._mixerPulse.activeUntil = now + 900 + Math.floor(Math.random() * 700);
      this._mixerPulse.nextAt = this._mixerPulse.activeUntil + 2600 + Math.floor(Math.random() * 3500);
    }
    mixer.timeScale = now < this._mixerPulse.activeUntil ? 0.42 : 0.1;
  },

  retryModelLoad() {
    this.syncCompanion3DFromGlobal();
  },

  // 阻止调参面板区域触摸滑动触发页面滚动（不影响 slider 本身拖动）
  noopCatchMove() {},

  _currentCompanionFormKey() {
    let fk = String(this.data.companionFormKey || "").trim();
    if (fk === "egg" || /^tier[123]$/.test(fk)) return fk;
    try {
      fk = String(wx.getStorageSync("selectedMascotFormKey") || "").trim();
    } catch (e) {}
    if (fk === "egg" || /^tier[123]$/.test(fk)) return fk;
    return "tier1";
  },

  getCompanionHomeTuningStorageKey() {
    const mid = String(this.data.selectedMascotId || "cute-dog");
    return `companionHomeTune:${mid}:${this._currentCompanionFormKey()}`;
  },

  loadHomeTuningFromStorage(done) {
    try {
      let raw = wx.getStorageSync(this.getCompanionHomeTuningStorageKey());
      if ((!raw || typeof raw !== "object" || Array.isArray(raw)) && this._currentCompanionFormKey() === "tier1") {
        try {
          const legacy = wx.getStorageSync(`companionHomeTune:${String(this.data.selectedMascotId || "cute-dog")}`);
          if (legacy && typeof legacy === "object" && !Array.isArray(legacy)) raw = legacy;
        } catch (e2) {}
      }
      if (raw && typeof raw === "object" && !Array.isArray(raw)) {
        const py = this.clamp(Number(raw.homeTunePosY || 0) || 0, -10000, 200);
        this.setData({
          homeTunePosX: Number(raw.homeTunePosX || 0) || 0,
          homeTunePosY: py,
          homeTunePosYText: String(py),
          homeTunePosZ: Number(raw.homeTunePosZ || 0) || 0,
          homeTuneScalePct: this.clamp(Number(raw.homeTuneScalePct || 100) || 100, 20, 300),
          homeTuneRotY: this.clamp(Number(raw.homeTuneRotY || 0) || 0, -180, 180),
        }, () => {
          if (typeof done === "function") done();
        });
        return;
      }
    } catch (e) {}
    if (typeof done === "function") done();
  },

  saveHomeTuningToStorage() {
    try {
      wx.setStorageSync(this.getCompanionHomeTuningStorageKey(), {
        homeTunePosX: Number(this.data.homeTunePosX || 0) || 0,
        homeTunePosY: Number(this.data.homeTunePosY || 0) || 0,
        homeTunePosZ: Number(this.data.homeTunePosZ || 0) || 0,
        homeTuneScalePct: this.clamp(Number(this.data.homeTuneScalePct || 100) || 100, 20, 300),
        homeTuneRotY: this.clamp(Number(this.data.homeTuneRotY || 0) || 0, -180, 180),
      });
      return true;
    } catch (e) {
      return false;
    }
  },

  _loadHomeTuningFromServer(options = {}) {
    const applyStoredPosition = !!(options && options.applyStoredPosition);
    const raw = this._serverCompanionTuning && typeof this._serverCompanionTuning === "object" ? this._serverCompanionTuning : {};
    const n = (v, d) => (Number.isFinite(Number(v)) ? Number(v) : d);
    const targetSize = n(raw.targetSize, HOME_TUNING_BASE_TARGET_SIZE);
    const rawLiftMul = n(raw.liftMul, HOME_TUNING_BASE_LIFT_MUL);
    const liftMul = rawLiftMul < HOME_TUNING_LIFT_MUL_MIN || rawLiftMul > HOME_TUNING_LIFT_MUL_MAX
      ? HOME_TUNING_BASE_LIFT_MUL
      : rawLiftMul;
    const baseRotYDeg = n(raw.baseRotYDeg, 0);
    const nextScalePct = applyStoredPosition ? this.clamp((targetSize / HOME_TUNING_BASE_TARGET_SIZE) * 100, 20, 300) : 100;
    const nextPosY = applyStoredPosition
      ? this.clamp((liftMul - HOME_TUNING_BASE_LIFT_MUL) * 100, -10000, 200)
      : 0;
    const nextRotY = applyStoredPosition ? this.clamp(baseRotYDeg, -180, 180) : 0;
    this.setData({
      homeTunePosX: applyStoredPosition ? n(raw.position_x, 0) : 0,
      homeTunePosY: nextPosY,
      homeTunePosYText: String(nextPosY),
      homeTunePosZ: applyStoredPosition ? n(raw.position_z, 0) : 0,
      homeTuneScalePct: nextScalePct,
      homeTuneRotY: nextRotY,
    }, () => this._applyHomeTuningToRoot());
  },

  toggleTuning() {
    const next = !this.data.showTuning;
    this.setData({ showTuning: next }, () => {
      if (next) this._loadHomeTuningFromServer({ applyStoredPosition: true });
    });
  },

  onHomeTuningSlider(e) {
    const key = e && e.currentTarget && e.currentTarget.dataset ? e.currentTarget.dataset.key : "";
    let v = Number(e && e.detail ? e.detail.value : 0);
    if (!key) return;
    if (key === "homeTunePosY") v = this.clamp(v, -10000, 200);
    const update = { [key]: v };
    if (key === "homeTunePosY") update.homeTunePosYText = String(v);
    this.setData(update, () => this._applyHomeTuningToRoot());
  },

  onHomeTunePosYTextInput(e) {
    const raw = (e && e.detail && typeof e.detail.value === "string" ? e.detail.value : "").trim();
    this.setData({ homeTunePosYText: raw });
    if (!raw) return;
    const v = Number(raw);
    if (!Number.isFinite(v)) return;
    const clamped = this.clamp(v, -10000, 200);
    this.setData({ homeTunePosY: clamped, homeTunePosYText: String(clamped) }, () => this._applyHomeTuningToRoot());
  },

  onHomeMouseWheel(e) {
    if (!this.data.showTuning) return;
    if (!this._threeRoot) return;
    try {
      if (e) {
        if (typeof e.preventDefault === "function") e.preventDefault();
        if (typeof e.stopPropagation === "function") e.stopPropagation();
      }
    } catch (err) {}
    const d = (e && e.detail) || {};
    const deltaY = Number(d.deltaY ?? d.delta ?? d.dy ?? d.wheelDelta ?? d.wheelDeltaY ?? d.scrollDelta ?? e?.deltaY ?? 0);
    if (!Number.isFinite(deltaY) || deltaY === 0) return;
    const cur = Number(this.data.homeTuneScalePct || 100) || 100;
    const factor = Math.pow(1.001, deltaY);
    const next = Math.round(cur / factor);
    const clamped = this.clamp(next, 20, 300);
    if (clamped === cur) return false;
    this.setData({ homeTuneScalePct: clamped }, () => this._applyHomeTuningToRoot());
    return false;
  },

  resetTuning() {
    this.setData({
      homeTunePosX: 0,
      homeTunePosY: 0,
      homeTunePosYText: "0",
      homeTunePosZ: 0,
      homeTuneScalePct: 100,
      homeTuneRotY: 0,
    }, () => {
      this._applyHomeTuningToRoot();
      this.saveHomeTuningToStorage();
    });
  },

  saveTuningManual() {
    this._applyHomeTuningToRoot();
    const ok = this.saveHomeTuningToStorage();
    if (!ok) {
      wx.showToast({ title: "保存失败，请重试", icon: "none" });
      return;
    }
    this.pushHomeTuningToBackend(undefined, (success, payload) => {
      if (success) {
        this._serverCompanionTuning = { ...(payload || {}) };
        this._loadHomeTuningFromServer({ applyStoredPosition: true });
        wx.showToast({ title: "已保存到后端", icon: "success" });
      } else {
        wx.showToast({ title: "后端保存失败", icon: "none" });
      }
    });
  },

  migrateLocalTuningToBackendIfNeeded() {
    try {
      const raw = wx.getStorageSync(this.getCompanionHomeTuningStorageKey());
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) return;
      this.pushHomeTuningToBackend(raw);
    } catch (e) {}
  },

  pushHomeTuningToBackend(localRaw, done) {
    const raw = localRaw && typeof localRaw === "object" ? localRaw : this.data;
    const sp = this.clamp(Number(raw.homeTuneScalePct || 100) || 100, 20, 300);
    const targetSize = this.clamp((sp / 100) * HOME_TUNING_BASE_TARGET_SIZE, 0.1, 200.0);
    const deltaLiftMul = (Number(raw.homeTunePosY || 0) || 0) / 100;
    const liftMul = this.clamp(HOME_TUNING_BASE_LIFT_MUL + deltaLiftMul, HOME_TUNING_LIFT_MUL_MIN, HOME_TUNING_LIFT_MUL_MAX);
    const payload = {
      ...HOME_TUNING_DEFAULTS,
      liftMul,
      targetSize,
      baseRotYDeg: this.clamp(Number(raw.homeTuneRotY || 0) || 0, -180, 180),
      position_x: Number(raw.homeTunePosX || 0) || 0,
      position_z: Number(raw.homeTunePosZ || 0) || 0,
    };
    const mascotId = String(this.data.selectedMascotId || "cute-dog");
    const formKey = this._currentCompanionFormKey();
    postCompanionSetViewTuning(mascotId, formKey, payload, undefined, true, "companion")
      .then(() => {
        if (typeof done === "function") done(true, payload);
      })
      .catch(() => {
        if (typeof done === "function") done(false, payload);
      });
  },

  typeAssistantReply(reply, done) {
    const text = String(reply || "").trim();
    if (!text) {
      if (typeof done === "function") done();
      return;
    }
    if (this._typingTimer) {
      clearInterval(this._typingTimer);
      this._typingTimer = null;
    }
    let idx = 0;
    this.setData({ isTypingReply: true, typingReplyText: "" }, () => this._scrollChatToBottom());
    this._typingTimer = setInterval(() => {
      idx += 1;
      const nextText = text.slice(0, idx);
      const finished = idx >= text.length;
      this.setData({ typingReplyText: nextText });
      if (finished) {
        clearInterval(this._typingTimer);
        this._typingTimer = null;
        const nextList = this.data.chatList.concat([{ role: "assistant", text }]);
        this.setData({ chatList: nextList, isTypingReply: false, typingReplyText: "" }, () => {
          this._scrollChatToBottom();
          if (typeof done === "function") done();
        });
      }
    }, 34);
  },

  _applyHomeTuningToRoot() {
    if (!this._threeRoot || !this._fitBasePos || !this._fitBaseScale || !this._fitBaseSizeY) return;
    const px = Number(this.data.homeTunePosX || 0) || 0;
    const py = Number(this.data.homeTunePosY || 0) || 0;
    const pz = Number(this.data.homeTunePosZ || 0) || 0;
    const sp = this.clamp(Number(this.data.homeTuneScalePct || 100) || 100, 20, 300);
    const ry = this.clamp(Number(this.data.homeTuneRotY || 0) || 0, -180, 180);
    const targetSize = (sp / 100) * HOME_TUNING_BASE_TARGET_SIZE;
    this._fitScale = this._fitBaseScale * targetSize;
    const fitSizeY = Number(this._fitBaseSizeY || 1) * targetSize;
    const deltaLiftMul = py / 100;
    const dy = fitSizeY * deltaLiftMul;
    this._threeRoot.position.x = Number(this._fitBasePos.x || 0) + px;
    this._threeRoot.position.y = Number(this._fitBasePos.y || 0) + dy;
    this._threeRoot.position.z = Number(this._fitBasePos.z || 0) + pz;
    this._baseRotY = (ry * Math.PI) / 180;
    this.applyModelTransform();
  },
});

