const app = getApp();
const DEFAULT_BASE_URL = "http://127.0.0.1:9880";
const {
  getUserId,
  requestEggState,
  requestCompanionState,
  postCompanionAction,
  postCompanionSetDisplayForm,
  postCompanionSetViewTuning,
} = require("../../utils/pet-growth.js");
const {
  getPetById,
  getFormTierModelUrl,
  getFormTierPosterUrl,
  getStaticEggModelUrl,
  getEggModelUrl,
  getStaticEggPosterUrl,
} = require("../../utils/pets-catalog.js");

let createScopedThreejs = null;
let registerGLTFLoader = null;
let THREE_IMPORT_ERROR = "";

// 与 companion 页一致：使用 pages/companion 下内置的 three 打包（避免 npm 构建产物在部分工具链下被误解析，报 Missing semicolon / module not defined）
try {
  ({ createScopedThreejs } = require("../companion/threejs-miniprogram.js"));
  ({ registerGLTFLoader } = require("../companion/gltf-loader.js"));
} catch (e) {
  THREE_IMPORT_ERROR = String(e || "");
}

function getApiBaseUrl() {
  return app && app.getApiBaseUrl ? app.getApiBaseUrl() : DEFAULT_BASE_URL;
}

function resolveModelUrl(rel) {
  const s = String(rel || "").trim();
  if (!s) return "";
  if (s.startsWith("http")) return s;
  return `${getApiBaseUrl()}${s.startsWith("/") ? "" : "/"}${s}`;
}

function resolvePosterUrl(rel) {
  const s = String(rel || "").trim();
  if (!s) return "";
  if (s.startsWith("http")) return s;
  if (s.startsWith("/assets/")) {
    const { toMiniprogramAssetUrl } = require("../../utils/asset-url.js");
    return toMiniprogramAssetUrl(s);
  }
  return resolveModelUrl(s);
}

/** 避免 wx.getSystemInfoSync 弃用告警：优先 wx.getWindowInfo / getDeviceInfo */
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

/** 敲蛋「已破壳」本地记忆：需与当前 catalog 蛋资源一致，避免换文件/清缓存后仍误判已破壳 */
const EGG_CRACK_STORAGE_VER = 3;

function petEggCrackedStorageKey(mascotId) {
  const mid = String(mascotId || "").trim();
  return mid ? `petEggCracked:${mid}` : "";
}

function eggCrackAssetSignature(mascotId) {
  const pet = getPetById(String(mascotId || "").trim());
  if (!pet) return "";
  return `${String(getStaticEggModelUrl(pet) || "")}|${String(getEggModelUrl(pet) || "")}`;
}

function readPetEggCrackedFromStorage(mascotId) {
  const key = petEggCrackedStorageKey(mascotId);
  if (!key) return false;
  const expectSig = eggCrackAssetSignature(mascotId);
  try {
    const raw = wx.getStorageSync(key);
    // 清掉旧版标量，避免调试/换动物后仍误判为已破壳
    if (raw === true || raw === 1 || raw === "1" || raw === "true") {
      try {
        wx.removeStorageSync(key);
      } catch (e2) {}
      return false;
    }
    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
      const v = Number(raw.v);
      const okV = v === EGG_CRACK_STORAGE_VER;
      const okSig = expectSig && String(raw.sig || "") === expectSig;
      // v2 及无 sig / sig 不匹配：一律视为无效（重新从闭壳蛋开始）
      if (okV && raw.cracked === true && okSig) return true;
      if (raw.cracked === true && (!okV || !okSig)) {
        try {
          wx.removeStorageSync(key);
        } catch (e3) {}
      }
      return false;
    }
    return false;
  } catch (e) {
    return false;
  }
}

function writePetEggCrackedToStorage(mascotId) {
  const key = petEggCrackedStorageKey(mascotId);
  if (!key) return;
  const sig = eggCrackAssetSignature(mascotId);
  try {
    wx.setStorageSync(key, { v: EGG_CRACK_STORAGE_VER, cracked: true, sig });
  } catch (e) {}
}

function clearPetEggCrackedStorage(mascotId) {
  const key = petEggCrackedStorageKey(mascotId);
  if (!key) return;
  try {
    wx.removeStorageSync(key);
  } catch (e) {}
}

/** 详情页四格状态球：按 mascotId 单独存上次展示值（与后端 users.*.mascot_states[mascot_id] 一致；弱网/首屏用本地兜底） */
const STATUS_SNAPSHOT_VER = 1;

function statusSnapshotStorageKey(mascotId) {
  const mid = String(mascotId || "").trim();
  return mid ? `petDetailStatusSnapshot:${mid}` : "";
}

function readStatusSnapshot(mascotId) {
  const key = statusSnapshotStorageKey(mascotId);
  if (!key) return null;
  try {
    const raw = wx.getStorageSync(key);
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    const v = Number(raw.v);
    if (raw.v != null && v !== STATUS_SNAPSHOT_VER) return null;
    const clamp = (x) => Math.max(0, Math.min(100, Number(x) || 0));
    return {
      hunger: clamp(raw.hunger),
      mood: clamp(raw.mood),
      clean: clamp(raw.clean),
      sleepy: clamp(raw.sleepy),
    };
  } catch (e) {
    return null;
  }
}

function writeStatusSnapshot(mascotId, levels) {
  const key = statusSnapshotStorageKey(mascotId);
  if (!key || !levels || typeof levels !== "object") return;
  try {
    const clamp = (x) => Math.max(0, Math.min(100, Number(x) || 0));
    wx.setStorageSync(key, {
      v: STATUS_SNAPSHOT_VER,
      hunger: clamp(levels.hunger),
      mood: clamp(levels.mood),
      clean: clamp(levels.clean),
      sleepy: clamp(levels.sleepy),
      at: Date.now(),
    });
  } catch (e) {}
}

function mergeCompanionStatLevel(rawStats, snap, key) {
  const raw = rawStats && typeof rawStats === "object" ? rawStats : {};
  const v = raw[key];
  if (v !== undefined && v !== null && v !== "") {
    const n = Number(v);
    if (Number.isFinite(n)) return Math.max(0, Math.min(100, n));
  }
  if (snap && typeof snap === "object") {
    const n2 = Number(snap[key]);
    if (Number.isFinite(n2)) return Math.max(0, Math.min(100, n2));
  }
  return 0;
}

const TUNING = {
  fov: 45,
  camDistMul: 1.2,
  camHeightMul: 0.18,
  lookAtHeightMul: 0.12,
  liftMul: 0.1,
  targetSize: 3.0,
  baseRotYDeg: 0,
};

// 3D 调参（基于 pages/companion 的同款参数规则，但为 pet-detail 独立保存）
const TUNING_LIMITS = {
  fov: { min: 20, max: 90, default: 45 },
  camDistMul: { min: 0.2, max: 8.0, default: 1.2 },
  camHeightMul: { min: 0, max: 1.2, default: 0.18 },
  lookAtHeightMul: { min: 0, max: 0.35, default: 0.12 },
  // 允许负数：否则 liftMul 最低只能回到“基准位姿”，无法把模型继续往下推到画面下半区
  liftMul: { min: -50, max: 0.35, default: 0.1 },
  targetSize: { min: 0.1, max: 200.0, default: 3.0 },
  baseRotYDeg: { min: -180, max: 180, default: 0 },
};

const ACTION_DEBUG = false;
// 动作播放权重：小于 1 会“混合淡入”，减小动作对整体轮廓/占屏的影响
const ACTION_PLAY_WEIGHT = 0.75;

// 旋转自由度约束：
// 对已“定好位置”的形态（staticDisplay && tier>=2），限制 pitch 变化范围，避免用户拖拽后把整体框架破坏。
const ROTATE_PITCH_DELTA_STATIC = 0.12; // 弧度：越小越锁定
const ROTATE_PITCH_MIN = -0.2;
const ROTATE_PITCH_MAX = 1.35;

const DEFAULT_TUNING = { ...TUNING };

function defaultBaseRotYDegForPersona(personaId) {
  const pid = String(personaId || "");
  if (pid === "cute_chick" || pid === "cute_dino") return -90;
  return 0;
}

function valueToPercent(key, value) {
  const lim = TUNING_LIMITS[key];
  if (!lim) return 0;
  const v = Number(value);
  if (!Number.isFinite(v) || lim.max <= lim.min) return 0;
  const p = ((v - lim.min) / (lim.max - lim.min)) * 100;
  return Math.max(0, Math.min(100, Math.round(p)));
}

function percentToValue(key, percent) {
  const lim = TUNING_LIMITS[key];
  if (!lim) return Number(percent) || 0;
  const p = Math.max(0, Math.min(100, Number(percent) || 0));
  return lim.min + ((lim.max - lim.min) * p) / 100;
}

function buildTuningPercent(tuning) {
  const t = tuning || DEFAULT_TUNING;
  return {
    fov: valueToPercent("fov", t.fov),
    camDistMul: valueToPercent("camDistMul", t.camDistMul),
    camHeightMul: valueToPercent("camHeightMul", t.camHeightMul),
    lookAtHeightMul: valueToPercent("lookAtHeightMul", t.lookAtHeightMul),
    liftMul: valueToPercent("liftMul", t.liftMul),
    targetSize: valueToPercent("targetSize", t.targetSize),
    baseRotYDeg: valueToPercent("baseRotYDeg", t.baseRotYDeg),
  };
}

function stageTextOf(stage) {
  const map = {
    tier1: "初阶形态",
    tier2: "中阶形态",
    tier3: "高阶形态",
  };
  return map[String(stage || "tier1")] || "初阶形态";
}

function nowClock() {
  const d = new Date();
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  return `${h}:${m}`;
}

/** 与 companion 页一致：配置了 companion_forms 分档资源时走本地 tier 路径，否则走后端 avatar/config（与伴读 3D 同源） */
function usesCustomFormAssets(pet) {
  // 支持两种“自定义分档资源”：
  // 1) formAssetsRoot: "companion_forms/cute-dog"（按 tier1/2/3.glb 约定拼路径）
  // 2) formTiers: [{tier, modelUrl}]（animal/shiba、animal/fox 等分档 glb）
  if (!pet) return false;
  if (pet.formAssetsRoot && String(pet.formAssetsRoot).trim()) return true;
  if (Array.isArray(pet.formTiers) && pet.formTiers.length) return true;
  return false;
}

function buildModelUrlCandidates(primaryUrl) {
  const u = String(primaryUrl || "").trim();
  if (!u) return [];
  const list = [u];
  if (/\.gltf$/i.test(u)) {
    list.push(u.replace(/\.gltf$/i, ".glb"));
  }
  return list;
}

Page({
  data: {
    loading: true,
    mascotId: "",
    personaId: "default",
    petName: "",
    petEmoji: "",
    posterUrl: "",
    blurb: "",
    tagline: "",
    actions: [],
    modelStageNudge: false,
    viewMode: "3d",
    modelUrl: "",
    modelLoading: false,
    modelFailed: false,
    showUpgradeAnim: false,
    upgradeFromTier: 1,
    upgradeToTier: 1,
    upgradeTitle: "",
    upgradeSub: "",
    // hatch: 孵化中（蛋/破壳蛋） | grow: 成长中（tier1-3） | repair: 修复中（临时 three 异常）
    modelLoadScene: "hatch",
    modelLoadProgress: 0,
    modelLoadStageText: "魔法准备中…",
    modelMagicCount: 0,
    actionHighlight: "",
    activeCareAction: "",
    level: 1,
    stage: "tier1",
    stageText: "初阶形态",
    xp: 0,
    nextStageXp: 120,
    growthPercent: 0,
    displayFormTier: 1,
    stageMemoSelectedTier: 1,
    stageMemoList: [
      { tier: 1, title: "幼年期", range: "Lv.1-2", icon: "🐣" },
      { tier: 2, title: "成长期", range: "Lv.3-5", icon: "🐶" },
      { tier: 3, title: "成熟期", range: "Lv.6-10", icon: "🌟" },
    ],
    eggModelActive: true,
    eggCracked: false,
    // 破壳点击小游戏：第一次点击就预加载碎蛋模型，点击到进度满后再无缝呈现
    hatchTapGoal: 12,
    hatchTapCount: 0,
    hatchProgress: 0,
    hatchRemain: 12,
    hatchPreloadPercent: 0,
    hatchShakeOn: false,
    hatchFlashOn: false,
    formTierList: [
      { tier: 1, label: "初阶", locked: false },
      { tier: 2, label: "中阶", locked: true },
      { tier: 3, label: "高阶", locked: true },
    ],
    leftStats: [],
    rightStats: [],
    hungerLevel: 0,
    moodLevel: 0,
    cleanLevel: 0,
    sleepyLevel: 0,
    clockText: nowClock(),

    // 3D调参（按宠物分别保存）
    showTuning: false,
    tuning: DEFAULT_TUNING,
    tuningPercent: buildTuningPercent(DEFAULT_TUNING),
    // 当前先做“静态展示”：不播放 idle/动作，只负责模型摆放与加载
    staticDisplay: false,

    // 伴宠旁边透明气泡提示（植树式收集气泡）
    showNurtureBubble: false,
    nurtureBubbleAction: "feed", // feed | play | clean
    nurtureBubbleIcon: "zzz",
    nurtureBubbleIconClass: "nurture-bubble-icon-zzz",
    nurtureBubbleLabel: "收集：喂食",
    nurtureBubbleLeft: 90,
    nurtureBubbleTop: 160,
    firstNurtureStep: 0, // 0..3，依次引导 feed -> play -> clean
  },

  onLoad(options) {
    const id = String((options && options.id) || "").trim();
    const pet = getPetById(id);
    if (!pet) {
      wx.showToast({ title: "找不到这位伙伴", icon: "none" });
      setTimeout(() => wx.navigateBack(), 450);
      return;
    }
    wx.setNavigationBarTitle({ title: `${pet.name} · 我的伴宠` });
    const initialTier = 1;
    const stageMemoListInit = [
      { tier: 1, title: "幼年期", range: "Lv.1-2", icon: "🐣" },
      { tier: 2, title: "成长期", range: "Lv.3-5", icon: pet.emoji || "🐾" },
      { tier: 3, title: "成熟期", range: "Lv.6-10", icon: "🌟" },
    ];
    this.setData({
      mascotId: id,
      personaId: pet.personaId,
      petName: pet.name,
      petEmoji: pet.emoji,
      stageMemoList: stageMemoListInit,
      posterUrl: resolvePosterUrl(getStaticEggPosterUrl(pet) || pet.posterUrl),
      // 请求 companion/state 前，先按“首次展示 egg”兜底初始化
      modelUrl: resolveModelUrl(getStaticEggModelUrl(pet)),
      tagline: pet.tagline,
      blurb: pet.blurb,
      actions: pet.actions || [],
      clockText: nowClock(),
    }, () => this._hydrateStatusLevelsFromLocal(id));

    // egg 期：本地记忆是否已完成敲碎（只影响 egg 期展示的模型）
    this.setData({ eggCracked: readPetEggCrackedFromStorage(id) });

    this._initFirstNurtureStepFromStorage(id);

    requestEggState()
      .then((data) => {
        const ok = new Set(data.unlocked_mascot_ids || ["cute-dog"]);
        if (!ok.has(id)) {
          wx.showToast({ title: "先解锁再来看我哦", icon: "none" });
          setTimeout(() => wx.navigateBack(), 500);
          return;
        }
        this.refreshCompanionState();
      })
      .catch(() => {
        wx.showToast({ title: "加载失败", icon: "none" });
        setTimeout(() => wx.navigateBack(), 500);
      });
  },

  onShow() {
    if (this.data.mascotId) this.refreshCompanionState();
    this._startNurtureBubbleLoop();
  },

  _calcModelLoadScene() {
    if (this.data.modelFailed) return "repair";
    if (this.data.eggModelActive) return "hatch";
    // 成长动画只在“动物升级阶段”触发时出现。
    // 其它任何模型加载（例如仅切形态/切视角/重载但非升阶流程）统一用修复/魔法棒动画占位，
    // 防止“魔法棒 + 成长动画”叠在一起。
    if (this._allowGrowSceneOnce) {
      this._allowGrowSceneOnce = false; // 只允许一次：对应一次升级后的模型加载
      return "grow";
    }
    return "repair";
  },

  onUnload() {
    this._autoOrbitEnabled = false;
    if (this._viewTuningSyncTimer) {
      try {
        clearTimeout(this._viewTuningSyncTimer);
      } catch (e) {}
      this._viewTuningSyncTimer = null;
    }
    this._stopNurtureBubbleLoop();
    this.destroyPetThree();
  },

  _hydrateStatusLevelsFromLocal(mascotId) {
    const snap = readStatusSnapshot(mascotId);
    if (!snap) return;
    const { hunger, mood, clean, sleepy } = snap;
    this.setData({
      hungerLevel: hunger,
      moodLevel: mood,
      cleanLevel: clean,
      sleepyLevel: sleepy,
      leftStats: [
        { key: "hunger", emoji: "🍊", label: "食物", value: hunger },
        { key: "mood", emoji: "🙂", label: "开心", value: mood },
      ],
      rightStats: [
        { key: "clean", emoji: "🧼", label: "清洁", value: clean },
        { key: "sleepy", emoji: "😪", label: "困意", value: sleepy },
      ],
    });
  },

  refreshCompanionState() {
    const mid = this.data.mascotId;
    if (!mid) return;
    requestCompanionState(mid)
      .then((data) => {
        this.applyCompanionState(data || {});
        this.setData({ loading: false, clockText: nowClock() });
      })
      .catch(() => {
        this.setData({ loading: false });
      });
  },

  applyCompanionState(data) {
    const rawFvt = data && data.form_view_tuning;
    this._serverFormViewTuning =
      rawFvt && typeof rawFvt === "object" && !Array.isArray(rawFvt) ? { ...rawFvt } : {};
    const prevTier = Number(this.data.displayFormTier) || 1;
    const prevEggActive = !!this.data.eggModelActive;
    const pet = getPetById(this.data.mascotId);
    const rawStats = (data && data.stats) || {};
    const snap = readStatusSnapshot(this.data.mascotId);
    const hungerLevel = mergeCompanionStatLevel(rawStats, snap, "hunger");
    const moodLevel = mergeCompanionStatLevel(rawStats, snap, "mood");
    const cleanLevel = mergeCompanionStatLevel(rawStats, snap, "clean");
    const sleepyLevel = mergeCompanionStatLevel(rawStats, snap, "sleepy");
    writeStatusSnapshot(this.data.mascotId, {
      hunger: hungerLevel,
      mood: moodLevel,
      clean: cleanLevel,
      sleepy: sleepyLevel,
    });
    const xp = Number(data.xp || 0);
    const next = Number(data.next_stage_xp ?? 120);
    const safeGrowth = next > 0 ? Math.max(0, Math.min(100, Math.round((xp / next) * 100))) : 0;
    const growthPercent = data.growth_percent != null ? Number(data.growth_percent) : safeGrowth;
    const dft = Number(data.display_form_tier) || 1;
    const eggActive = !!data.egg_model_active;
    const unlocked = Array.isArray(data.unlocked_form_tiers) && data.unlocked_form_tiers.length
      ? data.unlocked_form_tiers
      : [1];
    const unlockedSet = new Set(unlocked.map((n) => Number(n)));
    const labels = ["初阶", "中阶", "高阶"];
    const formTierList = [1, 2, 3].map((tier) => ({
      tier,
      label: labels[tier - 1],
      locked: !unlockedSet.has(tier),
    }));
    // 顶部可爱小便签：展示“幼年期/成长期/成熟期”，并根据解锁状态标记锁定
    const baseStageMemoList = Array.isArray(this.data.stageMemoList) ? this.data.stageMemoList : [];
    const stageMemoList = [1, 2, 3].map((tier) => {
      const base = baseStageMemoList.find((m) => Number(m.tier) === tier) || {};
      return {
        tier,
        title: base.title || (tier === 1 ? "幼年期" : tier === 2 ? "成长期" : "成熟期"),
        range: base.range || (tier === 1 ? "Lv.1-2" : tier === 2 ? "Lv.3-5" : "Lv.6-10"),
        icon:
          base.icon ||
          (tier === 1 ? "🐣" : tier === 2 ? (pet && pet.emoji) || "🐾" : "🌟"),
        locked: !unlockedSet.has(tier),
      };
    });
    let posterUrl = this.data.posterUrl;
    let modelUrl = this.data.modelUrl;
    if (pet) {
      if (eggActive) {
        // egg 期：未点击孵化=静态蛋；已点击孵化=破壳蛋形态
        // 若正在“敲碎小游戏”并且已开始预加载碎蛋模型，则保持当前 modelUrl（避免被后端刷新覆盖回静态蛋）
        // 敲蛋进行中仍只展示闭壳蛋（与柴犬一致）；碎蛋仅后台预加载，eggCracked 后才切 egg.glb
        if (this._hatchInProgress && !this.data.eggCracked) {
          modelUrl = this.data.modelUrl || resolveModelUrl(getStaticEggModelUrl(pet));
        } else if (this.data.eggCracked) {
          // 已破壳：只用「本会话下载的碎蛋本地路径」或 catalog 的 egg.glb；不要沿用 data.modelUrl（可能是闭壳 URL，导致状态与模型不一致）
          const loc = this._hatchBrokenLocalPath;
          modelUrl = loc && String(loc).length > 0 ? String(loc) : resolveModelUrl(getEggModelUrl(pet));
        } else {
          modelUrl = resolveModelUrl(getStaticEggModelUrl(pet));
        }
        posterUrl = resolvePosterUrl(getStaticEggPosterUrl(pet) || pet.posterUrl);
      } else {
        posterUrl = resolvePosterUrl(getFormTierPosterUrl(pet, dft) || posterUrl);
        modelUrl = resolveModelUrl(getFormTierModelUrl(pet, dft));
      }
    }
    this.setData({
      xp,
      level: Number(data.level || 1),
      stage: String(data.stage || "tier1"),
      stageText: eggActive ? "幼儿孵化" : stageTextOf(data.stage),
      nextStageXp: next,
      growthPercent,
      displayFormTier: dft,
      stageMemoSelectedTier: dft,
      stageMemoList,
      eggModelActive: eggActive,
      formTierList,
      posterUrl,
      modelUrl,
      leftStats: [
        { key: "hunger", emoji: "🍊", label: "食物", value: hungerLevel },
        { key: "mood", emoji: "🙂", label: "开心", value: moodLevel },
      ],
      rightStats: [
        { key: "clean", emoji: "🧼", label: "清洁", value: cleanLevel },
        { key: "sleepy", emoji: "😪", label: "困意", value: sleepyLevel },
      ],
      hungerLevel,
      moodLevel,
      cleanLevel,
      sleepyLevel,
    }, () => {
      // 一旦后端已孵化（egg_model_active=false），清理本地 cracked 标记
      if (!eggActive && this.data.eggCracked) {
        clearPetEggCrackedStorage(this.data.mascotId);
        this.setData({ eggCracked: false });
      }
      // 正式进入成长形态：结束孵化期常驻抚养气泡（此前仅用户点击收集或此处会关闭）
      if (prevEggActive && !eggActive && this.data.showNurtureBubble) {
        try {
          if (this._nurtureBubbleHideTimer) {
            clearTimeout(this._nurtureBubbleHideTimer);
            this._nurtureBubbleHideTimer = null;
          }
        } catch (e) {}
        this.setData({ showNurtureBubble: false });
        const sch0 = this._nurtureSchedule || {};
        const delta0 = Number(sch0.nextBubbleAt) - Date.now();
        this._scheduleNextNurtureBubble(delta0 > 0 ? Math.min(delta0, 60000) : 1500);
      }
      // 若成长导致 display_form_tier 自动变化：播放升级动画（2D/3D 都弹），
      // 同时在 3D 里“动画结束后”再切到下一阶模型。
      if (!this._suppressEnsure) {
        const curTier = Number(this.data.displayFormTier) || 1;
        const tierChanged = curTier !== prevTier;
        const eggActiveChanged = eggActive !== prevEggActive;
        const in3d = this.data.viewMode === "3d";

        const shouldAutoUpgradeAnim =
          tierChanged &&
          !eggActiveChanged && // egg -> hatch 由孵化动画接管，这里只管 tier1->2/3
          curTier > prevTier &&
          !this.data.showUpgradeAnim;

        if (shouldAutoUpgradeAnim) {
          const labels = ["初阶", "中阶", "高阶"];
          const upgradeFrom = labels[prevTier - 1] || "初阶";
          const upgradeTo = labels[curTier - 1] || `Lv.${curTier}`;
          const upgradeToken = (this._upgradeToken = Number(this._upgradeToken || 0) + 1);
          const animMs = 1100;

          // 延后重载：先让用户看到升级动画，再切模型（仅 3D）。
          this._suppressEnsure = true;
          this.setData({
            showUpgradeAnim: true,
            upgradeFromTier: prevTier,
            upgradeToTier: curTier,
            upgradeTitle: `升阶到 ${upgradeTo}`,
            upgradeSub: `小狗正在长大…（${upgradeFrom} → ${upgradeTo}）`,
          });

          setTimeout(() => {
            if (upgradeToken !== this._upgradeToken) return;
            this._suppressEnsure = false;
            this.setData({ showUpgradeAnim: false });

            if (this.data.viewMode !== "3d") return;
            const stillNeedFirst3dInit = !this._threeRenderer || !this._threeRoot;
            this.loadTuningFromStorage(() => {
              // 仅在“升级阶段”的模型加载里允许展示成长动画
              this._allowGrowSceneOnce = true;
              if (stillNeedFirst3dInit) this.ensureThree();
              else this._forceRemountPetThree();
            });
          }, animMs);
        } else if (in3d && (tierChanged || eggActiveChanged)) {
          // 非“自动升级动画”路径：直接刷新模型到新形态
          this.loadTuningFromStorage(() => this._forceRemountPetThree());
        }

        // 首次进入 3D：若 three 还没初始化过，也要主动 ensureThree()
        if (in3d && !this._threeRenderer && !this._threeRoot && !this.data.showUpgradeAnim) {
          this.loadTuningFromStorage(() => this.ensureThree());
        }
      }
    });
  },

  onTapHatchStart() {
    // 破壳小游戏：不允许“点击一下立刻跳转”，而是点到进度满才呈现
    if (!this.data.mascotId) return;
    if (!this.data.eggModelActive) return;
    if (this.data.eggCracked) return;
    const pet = getPetById(this.data.mascotId);
    if (!pet) return;

    // 首次点击：记录“已开始敲碎”，并立刻开始后台预加载碎蛋模型（不切走当前蛋画面）
    const mid = String(this.data.mascotId || "");
    const goal = Number(this.data.hatchTapGoal || 12) || 12;
    const nextCount = Math.min(goal, Number(this.data.hatchTapCount || 0) + 1);
    const brokenUrl = resolveModelUrl(getEggModelUrl(pet));

    this._hatchInProgress = true;
    this._hatchTargetUrl = brokenUrl;

    // 仅第一次点击启动下载任务（后续只叠加点击进度与特效）
    if (!this._hatchDownloadTask && !this._hatchBrokenLocalPath) {
      try {
        const task = wx.downloadFile({
          url: brokenUrl,
          success: (res) => {
            if (res && res.statusCode === 200 && res.tempFilePath) {
              this._hatchBrokenLocalPath = String(res.tempFilePath);
              this.setData({ hatchPreloadPercent: 100 }, () => this._maybeCommitEggCrack());
            }
          },
          fail: () => {},
        });
        this._hatchDownloadTask = task;
        if (task && task.onProgressUpdate) {
          task.onProgressUpdate((p) => {
            const pr = Math.max(0, Math.min(100, Number(p && p.progress)));
            this.setData({ hatchPreloadPercent: pr });
          });
        }
      } catch (e) {}
    }

    this._triggerEggWobble();

    try { wx.setStorageSync(`petEggCrackStarted:${mid}`, 1); } catch (e) {}

    this.setData({
      hatchTapCount: nextCount,
      hatchProgress: Math.floor((nextCount / goal) * 100),
      hatchRemain: Math.max(0, goal - nextCount),
      hatchShakeOn: true,
      hatchFlashOn: true,
      modelMagicCount: nextCount,
      // 不在敲蛋过程中切模型，保持当前蛋画面，等“进度满+预加载完成”再无缝切换
      stageText: "敲碎中",
    }, () => {
      setTimeout(() => this.setData({ hatchShakeOn: false }), 140);
      setTimeout(() => this.setData({ hatchFlashOn: false }), 220);
    });

    // 若点击已满（goal=1 或很小的情况），直接进入“已破壳”状态，
    // 但模型仍会继续加载，加载完成后自然呈现碎蛋（无缝）
    if (nextCount >= goal) {
      // 只标记“准备破壳”，真正呈现碎蛋要等下载完成（无缝）
      this._hatchReadyToCrack = true;
      this._maybeCommitEggCrack();
    }
  },

  _triggerEggWobble() {
    // 让“蛋本体”抖动：通过 three root 在短时间内叠加轻微位移/旋转
    this._eggWobbleUntil = Date.now() + 260;
    this._eggWobbleSeed = (this._eggWobbleSeed || 0) + 1;
  },

  _maybeCommitEggCrack() {
    if (!this._hatchInProgress) return;
    if (!this.data.eggModelActive || this.data.eggCracked) return;
    const goal = Number(this.data.hatchTapGoal || 12) || 12;
    const count = Number(this.data.hatchTapCount || 0) || 0;
    if (count < goal) return;
    // 等碎蛋文件预下载完成，再无缝呈现（避免敲蛋时出现加载动画遮罩影响体验）
    if (!this._hatchBrokenLocalPath) return;

    const mid = String(this.data.mascotId || "");
    this._hatchInProgress = false;
    this._hatchTargetUrl = "";
    this._hatchDownloadTask = null;
    this.setData({ eggCracked: true, stageText: "破壳中", modelUrl: this._hatchBrokenLocalPath }, () => {
      writePetEggCrackedToStorage(mid);
      // 现在再切碎蛋模型：此时文件已在本地，切换几乎瞬时
      if (this.data.viewMode === "3d") this._forceRemountPetThree();
      else this.setData({ viewMode: "3d" }, () => this._forceRemountPetThree());
    });
  },

  _pulseModelStage() {
    this.setData({ modelStageNudge: true });
    setTimeout(() => this.setData({ modelStageNudge: false }), 450);
  },

  _isModelBusy() {
    return !!(this.data.modelLoading || this.data.modelFailed || this.data.showUpgradeAnim);
  },

  _guardModelBusy(title) {
    if (!this._isModelBusy()) return false;
    wx.showToast({ title: title || "模型正在加载中…", icon: "none" });
    return true;
  },

  /**
   * 强制刷新当前 3D canvas，避免 threejs-miniprogram 重建 scene 时出现：
   * `TypeError: Cannot redefine property: style`
   * 并确保蛋期静态蛋 <-> 破壳蛋、tier 切换后模型真的切过去。
   */
  _forceRemountPetThree() {
    if (this.data.viewMode !== "3d") return this.ensureThree();
    this._suppressEnsure = true;
    this._autoOrbitEnabled = true;
    this._autoOrbitSpeed = 0.35;
    try { this.destroyPetThree(); } catch (e) {}
    this.setData(
      {
        viewMode: "2d",
        modelLoading: false,
        modelFailed: false,
        modelLoadProgress: 0,
        modelMagicCount: 0,
      },
      () => {
        setTimeout(() => {
          this.setData({ viewMode: "3d" }, () => {
            setTimeout(() => {
              this._suppressEnsure = false;
              this.ensureThree();
            }, 60);
          });
        }, 30);
      }
    );
  },

  onCareTap(e) {
    const action = String(e.currentTarget.dataset.action || "");
    if (!action || !this.data.mascotId) return;
    if (this._guardModelBusy("模型正在加载中…")) return;
    // egg 期：必须先点击孵化，然后只允许喂养完成首次培养
    if (this.data.eggModelActive) {
      if (!this.data.eggCracked) {
        wx.showToast({ title: "先点击孵化哦～", icon: "none" });
        return;
      }
      if (action !== "feed") {
        wx.showToast({ title: "先喂养完成第一次培养～", icon: "none" });
        return;
      }
    }
    this._pulseModelStage();
    this.setData({ activeCareAction: action });
    postCompanionAction(this.data.mascotId, action)
      .then((data) => {
        const backendData = data || {};
        this.applyCompanionState(backendData);
        this._afterNurtureActionSuccess(action);
        this._maybeAutoUpgradeTierFromBackend(backendData);
      })
      .catch(() => {
        wx.showToast({ title: "操作失败，请重试", icon: "none" });
      })
      .finally(() => {
        setTimeout(() => this.setData({ activeCareAction: "" }), 360);
      });
  },

  _afterNurtureActionSuccess(action) {
    try {
      const act = String(action || "").trim();
      if (!["feed", "play", "clean"].includes(act)) return;
      this._maybeAdvanceFirstNurtureStep(act);
    } catch (e) {}
  },

  _initFirstNurtureStepFromStorage(mascotId) {
    try {
      const key = `petDetailFirstNurtureStep:${String(mascotId || "").trim()}`;
      const raw = wx.getStorageSync(key);
      const n = Number(raw);
      const step = Number.isFinite(n) ? Math.max(0, Math.min(3, Math.floor(n))) : 0;
      this._nurtureFirstStepKey = key;
      this.setData({ firstNurtureStep: step });
    } catch (e) {
      this._nurtureFirstStepKey = `petDetailFirstNurtureStep:${String(mascotId || "").trim()}`;
      this.setData({ firstNurtureStep: 0 });
    }
  },

  _persistFirstNurtureStep(step) {
    try {
      if (!this._nurtureFirstStepKey) return;
      wx.setStorageSync(this._nurtureFirstStepKey, Number(step) || 0);
    } catch (e) {}
  },

  _maybeAdvanceFirstNurtureStep(action) {
    const order = ["feed", "play", "clean"];
    const cur = Number(this.data.firstNurtureStep || 0);
    if (!Number.isFinite(cur) || cur >= 3) return;
    const expected = order[cur];
    if (action !== expected) return;
    const next = Math.min(3, cur + 1);
    this.setData({ firstNurtureStep: next }, () => this._persistFirstNurtureStep(next));
  },

  _startNurtureBubbleLoop() {
    if (this._nurtureBubbleRunning) return;
    this._nurtureBubbleRunning = true;

    // 每天登录先出一批；后续按“间隔几个小时出一批”出泡（持久化到本地存储）
    this._nurtureBubbleConfig = {
      loginCount: 3,
      burstCount: 2,
      burstIntervalMs: 4 * 60 * 60 * 1000, // 4 小时出一批
      inBurstGapMs: 1200, // 同一批内间隔
      maxPerDay: 12,
      bubbleLifetimeMs: 4200, // 需与 CSS 动画接近
      bubbleShowRecheckMs: 1200, // 遮罩/加载期间重试间隔
    };

    this._nurtureBubblePositions = [
      // 顶部上部：避开左上角/右上角（小球在左上 18rpx,18rpx；整体展示框宽度大概 400+rpx）
      { left: 120, top: 150 },
      { left: 190, top: 140 },
      { left: 260, top: 155 },
      { left: 145, top: 120 },
      { left: 230, top: 125 },
    ];

    this._bootstrapNurtureScheduleState();
    this._scheduleNextNurtureBubble(0);
  },

  _stopNurtureBubbleLoop() {
    this._nurtureBubbleRunning = false;
    if (this._nurtureBubbleNextTimer) {
      try { clearTimeout(this._nurtureBubbleNextTimer); } catch (e) {}
      this._nurtureBubbleNextTimer = null;
    }
    if (this._nurtureBubbleHideTimer) {
      try { clearTimeout(this._nurtureBubbleHideTimer); } catch (e) {}
      this._nurtureBubbleHideTimer = null;
    }
    if (this.data.showNurtureBubble) this.setData({ showNurtureBubble: false });
  },

  _bootstrapNurtureScheduleState() {
    const mascotId = String(this.data.mascotId || "").trim();
    const dateKey = (() => {
      const d = new Date();
      const y = d.getFullYear();
      const m = d.getMonth() + 1;
      const day = d.getDate();
      return `${y}-${m < 10 ? "0" : ""}${m}-${day < 10 ? "0" : ""}${day}`;
    })();

    const storageKey = `petDetailNurtureSchedule:${mascotId}`;
    this._nurtureScheduleStorageKey = storageKey;
    const cfg = this._nurtureBubbleConfig || {};

    const load = (() => {
      try {
        const raw = wx.getStorageSync(storageKey);
        if (raw && typeof raw === "object") return raw;
      } catch (e) {}
      return null;
    })();

    const base = {
      dateKey,
      shownToday: 0,
      burstRemaining: cfg.loginCount || 3,
      nextBubbleAt: Date.now(),
    };

    if (!load || load.dateKey !== dateKey || typeof load.nextBubbleAt !== "number") {
      this._nurtureSchedule = base;
      try { wx.setStorageSync(storageKey, base); } catch (e) {}
      return;
    }

    // 限流：如果超过最大值，直接停止当天剩余展示
    if (Number(load.shownToday) >= Number(cfg.maxPerDay || 12)) {
      this._nurtureSchedule = { ...load, burstRemaining: 0, nextBubbleAt: Number.MAX_SAFE_INTEGER };
      return;
    }

    // 如果 nextBubbleAt 在未来，保留；否则允许“补发下一只”
    this._nurtureSchedule = {
      dateKey,
      shownToday: Number(load.shownToday || 0),
      burstRemaining: Number(load.burstRemaining || (cfg.loginCount || 3)),
      nextBubbleAt: Number(load.nextBubbleAt || Date.now()),
    };
  },

  _persistNurtureScheduleState() {
    try {
      if (!this._nurtureScheduleStorageKey) return;
      wx.setStorageSync(this._nurtureScheduleStorageKey, this._nurtureSchedule || {});
    } catch (e) {}
  },

  _scheduleNextNurtureBubble(delayMs) {
    if (!this._nurtureBubbleRunning) return;
    if (this._nurtureBubbleNextTimer) {
      try { clearTimeout(this._nurtureBubbleNextTimer); } catch (e) {}
    }

    const d = Math.max(0, Number(delayMs) || 0);
    this._nurtureBubbleNextTimer = setTimeout(() => this._tryShowNurtureBubble(), d);
  },

  _tryShowNurtureBubble() {
    if (!this._nurtureBubbleRunning) return;

    const cfg = this._nurtureBubbleConfig || {};
    const maxPerDay = Number(cfg.maxPerDay || 12);
    const recheckMs = Number(cfg.bubbleShowRecheckMs || 1200);
    const lifetimeMs = Number(cfg.bubbleLifetimeMs || 4200);

    // 正在显示/遮罩/加载/升级期间不展示气泡（避免叠层与抢事件）
    if (this.data.showNurtureBubble || this.data.modelLoading || this.data.modelFailed || this.data.showUpgradeAnim) {
      this._scheduleNextNurtureBubble(recheckMs);
      return;
    }

    if (!this.data.mascotId) {
      this._scheduleNextNurtureBubble(recheckMs);
      return;
    }

    // 到点了吗？
    const now = Date.now();
    const sch = this._nurtureSchedule || {};
    if (!Number.isFinite(sch.nextBubbleAt)) {
      this._bootstrapNurtureScheduleState();
      this._scheduleNextNurtureBubble(0);
      return;
    }
    if (now < sch.nextBubbleAt) {
      this._scheduleNextNurtureBubble(Math.min(60000, sch.nextBubbleAt - now));
      return;
    }

    // 达到上限就停
    if (Number(sch.shownToday || 0) >= maxPerDay) {
      this._nurtureBubbleRunning = false;
      return;
    }

    // 可用操作门控：egg 未破壳只允许 feed（由 onCareTap 自己再校验也更安全）
    const eggActive = !!this.data.eggModelActive;
    const eggCracked = !!this.data.eggCracked;
    if (eggActive && !eggCracked) {
      // 先等用户点破壳（由 onTapHatchStart 触发）；避免误导
      this._scheduleNextNurtureBubble(1500);
      return;
    }

    const allowed = eggActive ? ["feed"] : ["feed", "play", "clean"];

    // “首次养成”顺序引导：feed -> play -> clean
    const order = ["feed", "play", "clean"];
    const step = Number(this.data.firstNurtureStep || 0);
    let action = "";
    if (Number.isFinite(step) && step < 3) {
      const expected = order[step];
      action = allowed.includes(expected) ? expected : allowed[0] || "";
    } else {
      action = allowed[Math.floor(Math.random() * allowed.length)] || allowed[0] || "";
    }
    if (!action) {
      this._scheduleNextNurtureBubble(recheckMs);
      return;
    }

    const icon = action === "feed" ? "zzz" : action === "play" ? "🎾" : "🧼";
    const label = action === "feed" ? "收集：喂食" : action === "play" ? "收集：玩耍" : "收集：清洁";
    const iconClass = action === "feed" ? "nurture-bubble-icon-zzz" : "";
    const posRaw = (this._nurtureBubblePositions && this._nurtureBubblePositions.length)
      ? this._nurtureBubblePositions[Math.floor(Math.random() * this._nurtureBubblePositions.length)]
      : { left: 190, top: 140 };
    // 蛋期模型占画面中部：把气泡整体上移，避免被蛋挡住、也更容易点到
    let pos = { left: Number(posRaw.left) || 190, top: Number(posRaw.top) || 140 };
    if (eggActive) {
      pos = { left: pos.left, top: Math.max(48, pos.top - 56) };
    }

    // 消耗一次：更新下次显示时间（持久化到本地）
    const consume = () => {
      const curShown = Number(sch.shownToday || 0);
      const curRemain = Number(sch.burstRemaining || 0);
      sch.shownToday = curShown + 1;

      let nextAt = now + Number(cfg.inBurstGapMs || 1200);
      let nextRemain = Math.max(0, curRemain - 1);

      if (nextRemain <= 0) {
        // 下一个“间隔几个小时”的批次
        nextAt = now + Number(cfg.burstIntervalMs || 3 * 60 * 60 * 1000);
        nextRemain = Number(cfg.burstCount || 2);
      }

      sch.burstRemaining = nextRemain;
      sch.nextBubbleAt = nextAt;
      this._nurtureSchedule = sch;
      this._persistNurtureScheduleState();
    };
    consume();

    this.setData({
      showNurtureBubble: true,
      nurtureBubbleAction: action,
      nurtureBubbleIcon: icon,
      nurtureBubbleLabel: label,
      nurtureBubbleIconClass: iconClass,
      nurtureBubbleLeft: Number(pos.left) || 190,
      nurtureBubbleTop: Number(pos.top) || 140,
    });

    if (this._nurtureBubbleHideTimer) {
      try {
        clearTimeout(this._nurtureBubbleHideTimer);
      } catch (e) {}
      this._nurtureBubbleHideTimer = null;
    }
    // 蛋期（首次孵化）：不自动消失；正式进入成长形态后由 applyCompanionState 收起并恢复轮询
    const inEggHatchPhase = !!this.data.eggModelActive;
    if (!inEggHatchPhase) {
      this._nurtureBubbleHideTimer = setTimeout(() => {
        this.setData({ showNurtureBubble: false });
        const delta = (this._nurtureSchedule && this._nurtureSchedule.nextBubbleAt)
          ? this._nurtureSchedule.nextBubbleAt - Date.now()
          : 0;
        this._scheduleNextNurtureBubble(delta > 0 ? Math.min(delta, 60000) : 0);
      }, lifetimeMs);
    }
  },

  onNurtureBubbleCollect(e) {
    const action = String(e.currentTarget.dataset.action || "");
    if (!action) return;
    // 先隐藏气泡，避免连续点
    this.setData({ showNurtureBubble: false });
    try {
      if (this._nurtureBubbleHideTimer) {
        try { clearTimeout(this._nurtureBubbleHideTimer); } catch (e) {}
        this._nurtureBubbleHideTimer = null;
      }
    } catch (e) {}

    // 触发对应抚养功能（与手动按钮一致）
    this.onCareTap({ currentTarget: { dataset: { action } } });

    // 下一轮由持久化 schedule.nextBubbleAt 控制（避免连续过密）
    const sch = this._nurtureSchedule || {};
    const delta = Number(sch.nextBubbleAt) - Date.now();
    this._scheduleNextNurtureBubble(delta > 0 ? Math.min(delta, 60000) : 0);
  },


  _maybeAutoUpgradeTierFromBackend(backendData) {
    try {
      const data = backendData && typeof backendData === "object" ? backendData : {};
      const eggActive = !!data.egg_model_active;
      // egg 期不做形态切换（模型仍为蛋模型）；只在孵化后再自动切形态。
      if (eggActive) return;

      // 自动升阶严格按 XP 阈值判断，不按 unlocked_form_tiers 判断。
      // 原因：测试期可能放开了 unlocked_form_tiers=[1,2,3]，会导致首次喂养直接跳中阶。
      const xp = Number(data.xp || 0) || 0;
      const th = data.form_tier_thresholds || {};
      const t2 = Number(th["2"] || th[2] || 120) || 120;
      const t3 = Number(th["3"] || th[3] || 300) || 300;
      const maxUnlockedByXp = xp >= t3 ? 3 : (xp >= t2 ? 2 : 1);

      const curTier = Number(data.display_form_tier || this.data.displayFormTier || 1) || 1;
      if (maxUnlockedByXp <= curTier) return;

      // 仅自动切到“下一阶”
      const targetTier = Math.min(3, curTier + 1, maxUnlockedByXp);
      if (!Number.isFinite(targetTier) || targetTier <= curTier) return;

      // 若用户正处于手动升级动画/模型加载中，则不叠加触发
      if (this.data.showUpgradeAnim || this._isModelBusy()) return;

      this._autoUpgradeFlowToTier(targetTier, curTier);
    } catch (e) {}
  },

  _autoUpgradeFlowToTier(tier, fromTier) {
    // 这段逻辑与 onTapFormTier 同源：播放升级动画 + 后端 set_display_form + 延后切 3D
    if (this._guardModelBusy("升级中…请稍等加载完成")) return;
    if (!tier || !this.data.mascotId) return;
    const wasIn3d = this.data.viewMode === "3d";
    const labels = ["初阶", "中阶", "高阶"];
    const ft = Number(fromTier || this.data.displayFormTier) || 1;
    const upgradeFrom = labels[ft - 1] || "初阶";
    const upgradeTo = labels[tier - 1] || `Lv.${tier}`;

    const upgradeToken = (this._upgradeToken = Number(this._upgradeToken || 0) + 1);
    const animMs = 1100;

    this.setData({
      showUpgradeAnim: true,
      upgradeFromTier: ft,
      upgradeToTier: tier,
      upgradeTitle: `升阶到 ${upgradeTo}`,
      upgradeSub: `小狗正在长大…（${upgradeFrom} → ${upgradeTo}）`,
    });

    let backendReady = false;
    let animDone = false;
    let backendData = null;

    const tryCommit = () => {
      if (upgradeToken !== this._upgradeToken) return;
      if (!backendReady || !animDone) return;

      this._suppressEnsure = true;
      this._pulseModelStage();
      this.applyCompanionState(backendData || {});

      const go3d = () => {
        this.setData({ viewMode: "3d" }, () => {
          setTimeout(() => {
            if (upgradeToken !== this._upgradeToken) return;
            this._suppressEnsure = false;
            // 升级阶段后一次模型加载：允许展示成长动画（仅限这一轮）
            this._allowGrowSceneOnce = true;
            this.ensureThree();
            this.setData({ showUpgradeAnim: false });
          }, 60);
        });
      };

      if (wasIn3d) {
        this.destroyPetThree();
        this.setData({ viewMode: "2d", modelLoading: false, modelFailed: false }, () => {
          setTimeout(go3d, 30);
        });
      } else {
        go3d();
      }
    };

    setTimeout(() => {
      animDone = true;
      tryCommit();
    }, animMs);

    postCompanionSetDisplayForm(this.data.mascotId, tier)
      .then((data) => {
        backendReady = true;
        backendData = data || {};
        tryCommit();
      })
      .catch(() => {
        if (upgradeToken !== this._upgradeToken) return;
        this.setData({ showUpgradeAnim: false });
        wx.showToast({ title: "切换失败", icon: "none" });
      });
  },

  onTapViewMode(e) {
    const mode = String(e.currentTarget.dataset.mode || "");
    if (!mode || mode === this.data.viewMode) return;
    if (this._guardModelBusy("模型正在加载中…")) return;
    if (mode === "2d") {
      this._autoOrbitEnabled = false;
      this.destroyPetThree();
      this.setData({ viewMode: "2d", modelLoading: false, modelFailed: false });
      return;
    }
    this.setData({ viewMode: "3d" }, () => {
      // 进入 3D：开始缓慢环绕展示（镜头绕模型 pivot 转）
      this._autoOrbitEnabled = true;
      this._autoOrbitSpeed = 0.35; // rad/s（越大转得越快）
      setTimeout(() => {
        const needReload = this._tuningLoadedKey !== this.getTuningStorageKey();
        if (needReload) {
          this.loadTuningFromStorage(() => this.ensureThree());
          return;
        }
        this.ensureThree();
      }, 50);
    });
  },

  /** 与 companion retryModelLoad 一致 */
  retryPetThree() {
    if (this.data.viewMode !== "3d") return;
    this.ensureThree();
  },

  onTapFormTier(e) {
    const tier = Number(e.currentTarget.dataset.tier);
    if (!tier || !this.data.mascotId) return;
    // 允许在“加载失败/修复遮罩”期间继续切换形态做测试：
    // 小程序 webgl canvas 原生层有时会导致遮罩与模型叠层，因此失败时不要阻塞切换。
    if (this.data.showUpgradeAnim) {
      wx.showToast({ title: "升级中…请稍等", icon: "none" });
      return;
    }
    if (this.data.modelLoading || this.data.modelFailed) {
      // 取消当前 in-flight 的 three 构建/加载，避免 token 回写把新切换覆盖掉
      try { this._modelLoadToken = (this._modelLoadToken || 0) + 1; } catch (e) {}
      try { this._threeBuildInFlight = false; } catch (e) {}
      try { this._petThreeTransientRetry = 0; } catch (e) {}
      try { this.destroyPetThree(); } catch (e) {}
      this.setData({ modelLoading: false, modelFailed: false, modelLoadProgress: 0, modelMagicCount: 0 });
    }
    const row = (this.data.formTierList || []).find((x) => x.tier === tier);
    if (row && row.locked) {
      wx.showToast({ title: "该形态尚未解锁", icon: "none" });
      return;
    }
    const wasIn3d = this.data.viewMode === "3d";
    // 仅“切换模型形态”：不播放升级动画。
    // 升级动画只在 XP 解锁升阶时由 applyCompanionState / _autoUpgradeFlowToTier 触发。
    this._pulseModelStage();
    // 非升级切换：禁止 grow 场景（成长动画），只用魔法棒滴滴（repair）占位
    this._allowGrowSceneOnce = false;

    postCompanionSetDisplayForm(this.data.mascotId, tier)
      .then((data) => {
        const backendData = data || {};
        this._suppressEnsure = true;
        this.applyCompanionState(backendData);
        // 如果当前这只就是“已设为陪读”的伴宠，则同步把形态写回全局，确保首页能自动刷新到新形态
        try {
          const selected = String(wx.getStorageSync("selectedMascot") || "").trim();
          if (selected && selected === String(this.data.mascotId || "").trim()) {
            const eggActive = !!(backendData && backendData.egg_model_active);
            const dft = Math.max(1, Math.min(3, Number(backendData && backendData.display_form_tier || tier) || 1));
            const formKey = eggActive ? "egg" : `tier${dft}`;
            wx.setStorageSync("selectedMascotFormKey", formKey);
            wx.setStorageSync("selectedMascotUpdatedAt", Date.now());
          }
        } catch (e2) {}
        // 立即切换模型（丝滑）：不弹升级 overlay，只做 remount
        this.loadTuningFromStorage(() => {
          this._suppressEnsure = false;
          if (wasIn3d) this._forceRemountPetThree();
          else this.setData({ viewMode: "3d", modelLoading: false, modelFailed: false }, () => this.ensureThree());
        });
      })
      .catch(() => {
        wx.showToast({ title: "切换失败", icon: "none" });
      });
  },

  onStageMemoTap(e) {
    const tier = Number(e.currentTarget.dataset.tier);
    if (!tier || !Number.isFinite(tier)) return;
    this.setData({ stageMemoSelectedTier: Math.max(1, Math.min(3, tier)) });
  },

  /**
   * 与 pages/companion/companion.js 同源：默认用 GET /ar_companion/avatar/config 的 model_url；
   * 若 pets-catalog 为该宠配置了 formAssetsRoot，则优先加载 companion_forms 下分档模型。
   */
  ensureThree() {
    // 关键：每次切形态/切档位，都要先确保加载“当前形态专属”的调参/相机存储
    // 否则容易出现：你调完 2/3 后再看 1，1 的相机被错误套用旧档位参数。
    if (this.data.viewMode === "3d") {
      // egg 期未破壳：固定正对用户，不自动环绕
      if (this.data.eggModelActive && !this.data.eggCracked) {
        this._autoOrbitEnabled = false;
      } else {
        // 如果用户当前没有在交互，默认恢复自动环绕展示
        if (!this._camInteract) this._autoOrbitEnabled = true;
      }
      const needKey = this.getTuningStorageKey();
      if (this._tuningLoadedKey !== needKey) {
        return this.loadTuningFromStorage(() => this.ensureThree());
      }
    }

    const pet = getPetById(this.data.mascotId);
    const tier = Number(this.data.displayFormTier) || 1;
    const eggActive = !!this.data.eggModelActive;
    const eggCracked = !!this.data.eggCracked;
    const fallbackUrl = pet
      ? (eggActive
          ? resolveModelUrl(eggCracked ? getEggModelUrl(pet) : getStaticEggModelUrl(pet))
          : resolveModelUrl(getFormTierModelUrl(pet, tier)))
      : (this.data.modelUrl || "").trim();

    if (usesCustomFormAssets(pet)) {
      if (fallbackUrl) {
        this.setData({ modelUrl: fallbackUrl });
        return this.initPetThree(fallbackUrl);
      }
      this.setData({ modelFailed: true, modelLoading: false });
      return;
    }

    this.setData({
      modelLoading: true,
      modelFailed: false,
      modelLoadProgress: 0,
      modelLoadStageText: "魔法准备中…",
      modelMagicCount: 0,
    });
    const personaId = this.data.personaId || "default";
    wx.request({
      url: `${getApiBaseUrl()}/ar_companion/avatar/config?persona_id=${encodeURIComponent(personaId)}&user_id=${encodeURIComponent(getUserId())}`,
      method: "GET",
      success: (res) => {
        const status = res && res.statusCode;
        if (status !== 200) {
          if (fallbackUrl) {
            this.setData({ modelUrl: fallbackUrl });
            this.initPetThree(fallbackUrl);
          } else {
            this.setData({ modelFailed: true, modelLoading: false });
          }
          return;
        }
        const raw = res && res.data;
        const data = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
        const rel = String(data.model_url || "").trim();
        const serverUrl = rel ? (rel.startsWith("http") ? rel : `${getApiBaseUrl()}${rel}`) : "";
        const finalUrl = serverUrl || fallbackUrl;
        this.setData({ modelUrl: finalUrl });
        if (finalUrl) this.initPetThree(finalUrl);
        else this.setData({ modelFailed: true, modelLoading: false });
      },
      fail: () => {
        if (fallbackUrl) {
          this.setData({ modelUrl: fallbackUrl });
          this.initPetThree(fallbackUrl);
        } else {
          this.setData({ modelFailed: true, modelLoading: false });
        }
      },
    });
  },

  initPetThree(modelUrl) {
    const baseUrl = String(modelUrl || "").trim();
    if (!baseUrl) {
      this.setData({ modelLoading: false, modelFailed: true });
      return;
    }
    // 并发保护：three 构建过程中不要重复 initPetThree（否则会反复 destroy/rebuild，触发 style redefine）
    if (this._threeBuildInFlight) {
      if (this._threeBuildBaseUrl === baseUrl) return;
      this._threeBuildQueued = baseUrl;
      return;
    }
    this._threeBuildInFlight = true;
    this._threeBuildBaseUrl = baseUrl;
    this._threeBuildQueued = null;
    this.destroyPetThree();
    this._modelLoadToken = (this._modelLoadToken || 0) + 1;
    const token = this._modelLoadToken;
    this._stopModelProgressFake();
    this.setData(
      {
        modelLoading: true,
        modelFailed: false,
        modelLoadScene: this._calcModelLoadScene(),
        modelLoadProgress: 0,
        modelLoadStageText: "魔法准备中…",
        modelMagicCount: 0,
      },
      () => {
        this._startModelProgressFake(token);
        this._queryPetThreeCanvasAndInit(baseUrl, 0);
      }
    );
  },

  _queryPetThreeCanvasAndInit(baseUrl, attempt) {
    wx.createSelectorQuery()
      .select("#petThreeCanvas")
      .node()
      .exec((res) => {
        const node = res && res[0] ? res[0].node : null;
        if (!node) {
          if (attempt < 12) {
            setTimeout(() => this._queryPetThreeCanvasAndInit(baseUrl, attempt + 1), 50);
            return;
          }
          console.error("[pet-detail] petThreeCanvas node missing after retries");
          this._stopModelProgressFake();
          this.setData({ modelLoading: false, modelFailed: true });
          return;
        }
        this._buildPetThreeScene(node, baseUrl);
      });
  },

  _buildPetThreeScene(node, baseUrl) {
    try {
      const token = this._modelLoadToken;
        if (!createScopedThreejs || !registerGLTFLoader) {
          throw new Error(`three import failed: ${THREE_IMPORT_ERROR || "unknown"}`);
        }
        // 注意：不要缓存 THREE 的“node 绑定”结果，否则在某些重建路径会出现
        // TypeError: Cannot set property 'width' of undefined（WebGLRenderer 取不到正确 canvas）
        const THREE = createScopedThreejs(node);
        this._THREE = THREE;
        registerGLTFLoader(THREE);

        const metrics = getWindowMetrics();
        const pixelRatio = metrics.pixelRatio || 1;
        const width = Math.max(300, metrics.windowWidth - 100);
        const height = Math.max(360, Math.round((680 / 750) * metrics.windowWidth));
        node.width = width * pixelRatio;
        node.height = height * pixelRatio;

        const renderer = new THREE.WebGLRenderer({ canvas: node, antialias: true, alpha: true });
        renderer.setPixelRatio(pixelRatio);
        renderer.setSize(width, height);
        renderer.setClearColor(0x000000, 0);
        const scene = new THREE.Scene();
        scene.background = null;
        const camera = new THREE.PerspectiveCamera(TUNING.fov, width / height, 0.01, 2000);
        camera.position.set(0, 0.8, 3.8);
        scene.add(new THREE.HemisphereLight(0xffffff, 0x666666, 1.2));
        const dir = new THREE.DirectionalLight(0xffffff, 1.1);
        dir.position.set(4, 6, 4);
        scene.add(dir);

        const loader = new THREE.GLTFLoader();
        const candidates = buildModelUrlCandidates(baseUrl);
        let lastErr = "";

        const onGltfLoaded = (gltf, loadedUrl) => {
          // 忽略过期回调（可能由于用户切形态/重复 init 触发并发）
          if (token !== this._modelLoadToken) return false;
          const root = gltf.scene || gltf.scenes?.[0];
          if (!root) {
            lastErr = "empty scene";
            return false;
          }
          const box = new THREE.Box3().setFromObject(root);
          const size = box.getSize(new THREE.Vector3());
          const center = box.getCenter(new THREE.Vector3());
          const maxDim = Math.max(size.x, size.y, size.z) || 1;
          root.position.set(-center.x, -center.y, -center.z);
          // 基准：targetSize=1 的“基准缩放”
          this._fitBaseScale = 1 / maxDim;
          root.scale.set(this._fitBaseScale, this._fitBaseScale, this._fitBaseScale);

          const initDeg = defaultBaseRotYDegForPersona(this.data.personaId);
          this._baseRotY = (initDeg * Math.PI) / 180;
          root.rotation.y = this._baseRotY;

          // 基准：绝对基准位姿（后续调参按“基准 + 目标倍率”计算，避免越调越漂）
          const fitBox = new THREE.Box3().setFromObject(root);
          const fitSize = fitBox.getSize(new THREE.Vector3());
          const fitCenter = fitBox.getCenter(new THREE.Vector3());
          root.position.set(
            root.position.x - fitCenter.x,
            root.position.y - fitCenter.y,
            root.position.z - fitCenter.z
          );
          this._fitBasePos = { x: root.position.x, y: root.position.y, z: root.position.z };
          this._fitBaseSizeY = fitSize.y;
          scene.add(root);
          this._threeRoot = root;
          this._threeRenderer = renderer;
          this._threeScene = scene;
          this._threeCamera = camera;
          // 初始化调参：确保画面不过大/不过小/不裁切
          if (typeof this.applyTuningToScene === "function") {
            const staticDisplay = !!this.data.staticDisplay;
            const tierLocal = Number(this.data.displayFormTier) || 1;
            // 静态展示时：根据模型高度微调垂直观测点，减少“模型偏上/偏下”
            if (staticDisplay && tierLocal >= 2 && !this._tuningFromStorage) {
              const baseY = Number(this._fitBaseSizeY || 1);
              let liftMul = 0.06;
              let lookAtHeightMul = 0.08;
              let camHeightMul = 0.28;
              if (baseY > 2.2) {
                liftMul = 0.03;
                lookAtHeightMul = 0.04;
                camHeightMul = 0.32;
              } else if (baseY < 1.2) {
                liftMul = 0.12;
                lookAtHeightMul = 0.12;
                camHeightMul = 0.42;
              }
              const nextTuning = { ...(this.data.tuning || {}), liftMul, lookAtHeightMul, camHeightMul };
              this.setData(
                { tuning: nextTuning, tuningPercent: buildTuningPercent(nextTuning) },
                () => this.applyTuningToScene()
              );
            } else {
              this.applyTuningToScene();
            }
          }
          this._threeMixer = null;
          this._threeClock = new THREE.Clock();
          this._threeClips = {};
          this._threeClipOrder = [];
          this._threeIdleClipName = "";
          const tier = Number(this.data.displayFormTier) || 1;
          const rawAnim = gltf.animations;
          const anims = Array.isArray(rawAnim) ? rawAnim : [];
          // 记录动画剪辑顺序，便于在 clip.name 不匹配业务 key 时做“兜底映射”
          this._threeClipOrder = anims
            .map((clip) => (clip && clip.name ? String(clip.name) : ""))
            .filter(Boolean);
          const staticDisplay = !!this.data.staticDisplay;
          // 静态展示：不自动播放 idle/动作，只负责渲染模型摆放。
          // 但为了“手动触发动作（按钮/点击动作）”可用，tier>=2 时仍需准备 clips map 与 mixer。
          const shouldPrepareActions = tier >= 2 && anims.length > 0;
          if (anims.length > 0 && shouldPrepareActions) {
            anims.forEach((clip) => {
              if (clip && clip.name) this._threeClips[clip.name] = clip;
            });

            const preferredIdx = anims.findIndex((c) => {
              const name = (c && c.name) ? String(c.name) : "";
              return /idle/i.test(name) || /stand/i.test(name);
            });
            // 只有明确命中 idle/stand 动画时，才自动播放；否则否则会退回 animations[0]
            // 导致“2/3 形态自动先展示非预期动作”。
            const playIdle = !staticDisplay && tier >= 2 && anims.length > 0 && preferredIdx >= 0;
            // 用于动作结束后的“恢复到原始姿态”
            if (preferredIdx >= 0 && anims[preferredIdx] && anims[preferredIdx].name) {
              this._threeIdleClipName = String(anims[preferredIdx].name);
            }
            const idx = preferredIdx >= 0 ? preferredIdx : 0;
            const clipToPlay = anims[idx];

            // 始终准备 mixer，确保手动 action 可执行
            const mixer = new THREE.AnimationMixer(root);
            this._threeMixer = mixer;

            // 仅在非静态展示时自动播放 idle
            if (playIdle && clipToPlay && THREE.AnimationMixer) {
              this._threeIdleClipName = clipToPlay && clipToPlay.name ? String(clipToPlay.name) : "";
              const action = mixer.clipAction(clipToPlay);
              action.enabled = true;
              action.setLoop(THREE.LoopRepeat);
              action.setEffectiveWeight(1);
              action.play();
            }
          }
          this._stopModelProgressFake();
          this._threeBuildInFlight = false;
          this._threeBuildBaseUrl = null;
          this.setData({
            modelLoading: false,
            modelFailed: false,
            modelLoadProgress: 100,
            modelLoadStageText: "孵化完成！",
          }, () => {
            // 敲碎小游戏：若进度已满且碎蛋已预加载完成，则无缝切换
            this._maybeCommitEggCrack();
          });
          // 若中途有人排队了另一个模型，成功后再处理队列
          if (this._threeBuildQueued) {
            const q = this._threeBuildQueued;
            this._threeBuildQueued = null;
            setTimeout(() => this.initPetThree(q), 50);
          }
          const animate = () => {
            if (!this._threeRenderer) return;
            const delta = this._threeClock ? this._threeClock.getDelta() : 0;
          if (this._autoOrbitEnabled && this._threeCamera && this._threeRoot) {
            // 自动环绕：只改相机 yaw，其它保持（radius/pitch 由当前视角计算得到）
            const orbit = this._camGetOrbitBase();
            const yaw = orbit.yaw + (this._autoOrbitSpeed || 0.3) * delta;
            this._camApplyOrbit({ yaw, pitch: orbit.pitch, radius: orbit.radius });
          }

          // 蛋本体短促抖动（不抖外框）：只在 egg 期未破壳时生效
          if (this.data.eggModelActive && !this.data.eggCracked && this._threeRoot) {
            const until = Number(this._eggWobbleUntil || 0);
            if (until && Date.now() < until) {
              const t = (until - Date.now()) / 260; // 1 -> 0
              const k = Math.max(0, Math.min(1, t));
              const seed = Number(this._eggWobbleSeed || 1);
              const wiggle = Math.sin((1 - k) * Math.PI * 10 + seed) * (0.06 * k);
              this._threeRoot.rotation.z = (this._baseRotY ? 0 : 0) + wiggle;
              this._threeRoot.position.x = (this._fitBasePos ? this._fitBasePos.x : 0) + wiggle * 0.18;
            }
          }

          if (this._threeMixer) this._threeMixer.update(delta);
          // 动作期间锁定 tuning：避免动画首帧/骨骼影响造成“位置/大小漂移”
          // 注意：必须在 mixer.update 之后再 applyTuningToScene，否则动画会覆盖 tuning。
          if (this._lockTuningDuringAction && this.data.viewMode === "3d") {
            try {
              this._applyRootTuningToScene();
            } catch (e) {}
          }
            renderer.render(scene, camera);
            node.requestAnimationFrame(animate);
          };
          animate();
          return true;
        };

        const tryLoad = (idx) => {
          if (idx >= candidates.length) {
            console.error("[pet-detail] GLTF 全部候选失败", {
              lastErr: lastErr || "(empty)",
              baseUrl,
              candidatesTried: candidates,
            });
            this._stopModelProgressFake();
            this._threeBuildInFlight = false;
            this._threeBuildBaseUrl = null;
            this.setData({ modelLoading: false, modelFailed: true });
            return;
          }
          const url = candidates[idx];
          // 多候选（例如不同后缀/兼容分支）时，给“解封尝试”一点提示
          this.setData({
            modelLoadStageText: `魔法正在尝试第${idx + 1}种格式…`,
          });
          loader.load(
            url,
            (gltf) => {
              if (!onGltfLoaded(gltf, url)) {
                tryLoad(idx + 1);
              }
            },
            (xhr) => {
              this._syncModelLoadProgressFromXhr(xhr, token);
            },
            (err) => {
              const msg = (err && (err.message || err.errMsg)) || JSON.stringify(err || {});
              lastErr = `${url} => ${msg}`;
              tryLoad(idx + 1);
            },
          );
        };
        tryLoad(0);
    } catch (e) {
      console.error("[pet-detail] _buildPetThreeScene", e);
      const msg = String((e && (e.message || e.errMsg || e.stack || e)) ? (e.message || e.errMsg || e.stack || e) : e || "");
      const isTransientStyleError =
        /Cannot redefine property/i.test(msg) && /style/i.test(msg);

      // 某些机型/版本下三方 three 组件会在首次构建时抛一次 style defineProperty 错误，
      // 但随后重试能成功。此时不展示“加载失败页”，改为自动重试 + 填充交互动画。
      if (isTransientStyleError) {
        this._petThreeTransientRetry = Number(this._petThreeTransientRetry || 0) + 1;
        // 对这种瞬时错误：不展示加载失败页，持续重试直到 three 成功（一般稍等后会恢复）
        this._threeBuildInFlight = false;
        this._threeBuildBaseUrl = null;
        this._stopModelProgressFake();
        const token = this._modelLoadToken;
        const nextP = Math.max(70, Number(this.data.modelLoadProgress || 0));

        // 避免“无限滴滴魔法修复中…”导致用户卡死：
        // 超过上限则切到 modelFailed，让用户可触发 retry。
        const maxTransientRetry = 12;
        if (this._petThreeTransientRetry >= maxTransientRetry) {
          this._petThreeTransientRetry = 0;
          try {
            if (this._petThreeStyleRetryTimer) clearTimeout(this._petThreeStyleRetryTimer);
          } catch (e) {}
          this._petThreeStyleRetryTimer = null;
          this._threeBuildInFlight = false;
          this._threeBuildBaseUrl = null;
          this.setData({
            modelLoading: false,
            modelFailed: true,
            modelLoadScene: "repair",
            modelLoadProgress: nextP,
            modelLoadStageText: "魔法修复卡住了…点点屏幕重试",
          });
          return;
        }

        this.setData({
          modelLoading: true,
          modelFailed: false,
          modelLoadScene: "repair",
          modelLoadProgress: nextP,
          modelLoadStageText: `滴滴魔法修复中…（${this._petThreeTransientRetry}）`,
        }, () => this._startModelProgressFake(token));
        // 逐步加大等待时间，避免热循环
        const delay = Math.min(1600, 320 * this._petThreeTransientRetry);
        clearTimeout(this._petThreeStyleRetryTimer);
        this._petThreeStyleRetryTimer = setTimeout(() => {
          // 仅在本轮 token 仍然有效时才继续重试（否则会导致切形态后仍反复卡在 repair 遮罩）
          if (token !== this._modelLoadToken) return;
          if (this.data.viewMode === "3d") this.initPetThree(baseUrl);
        }, delay);
        return;
      }

      this._petThreeTransientRetry = 0;
      this._threeBuildInFlight = false;
      this._threeBuildBaseUrl = null;
      this._stopModelProgressFake();
      this.setData({ modelLoading: false, modelFailed: true });
    }
  },

  destroyPetThree() {
    // destroy 只负责释放 three 对象
    // 不要在这里强行关掉自动环绕，否则 initPetThree 的内部 destroy 会导致进入 3D 后永远不旋转
    this._stopModelProgressFake();
    if (this._petThreeStyleRetryTimer) {
      try { clearTimeout(this._petThreeStyleRetryTimer); } catch (e) {}
      this._petThreeStyleRetryTimer = null;
    }
    if (this._autoOrbitResumeTimer) {
      clearTimeout(this._autoOrbitResumeTimer);
      this._autoOrbitResumeTimer = null;
    }
    if (this._threeMixer) {
      try { this._threeMixer.stopAllAction(); } catch (e) {}
    }
    this._threeMixer = null;
    this._threeClock = null;
    this._threeClips = null;
    this._threeClipOrder = null;
    this._threeIdleClipName = null;
    this._fitBaseScale = null;
    this._fitBasePos = null;
    this._fitBaseSizeY = null;
    this._baseRotY = null;
    if (this._threeRenderer) {
      try { this._threeRenderer.dispose(); } catch (e) {}
    }
    this._threeRenderer = null;
    this._threeScene = null;
    this._threeCamera = null;
    this._threeRoot = null;
  },

  _scheduleAutoOrbitResume(ms) {
    // 让自动环绕在短暂停顿后恢复，避免刚交互就立刻又转
    const delay = typeof ms === "number" ? ms : 900;
    try {
      if (this._autoOrbitResumeTimer) clearTimeout(this._autoOrbitResumeTimer);
    } catch (e) {}
    this._autoOrbitResumeTimer = setTimeout(() => {
      // 不强依赖 _camInteract（部分端/交互结束后 _camInteract 可能残留），
      // 只要仍在 3d，就恢复自动环绕。
      if (this.data.viewMode === "3d") {
        this._autoOrbitEnabled = true;
      }
    }, delay);
  },

  // ===== 3D 调参（模仿 companion 调参面板）=====
  noopCatchMove() {},
  getTierStorageSuffix() {
    const tier = Number(this.data.displayFormTier) || 1;
    // egg 模型作为独立档位存储（不与 tier1 混写）
    if (this.data.eggModelActive) return "egg";
    return `tier${tier}`;
  },
  getTuningStorageKey() {
    const mid = String(this.data.mascotId || "cute-dog");
    return `petDetail3dTuning:${mid}:${this.getTierStorageSuffix()}`;
  },
  getLegacyTuningStorageKey() {
    const mid = String(this.data.mascotId || "cute-dog");
    // 兼容旧版本：之前没有 tier/egg 后缀
    return `petDetail3dTuning:${mid}`;
  },
  getCameraStorageKey() {
    const mid = String(this.data.mascotId || "cute-dog");
    return `petDetail3dCamera:${mid}:${this.getTierStorageSuffix()}`;
  },
  getLegacyCameraStorageKey() {
    const mid = String(this.data.mascotId || "cute-dog");
    // 兼容旧版本：之前没有 tier/egg 后缀
    return `petDetail3dCamera:${mid}`;
  },
  loadTuningFromStorage(done) {
    // 标记：本次 tuning 是否来自“用户保存的存储”
    // 用于避免静态高阶的自动微调覆盖掉用户保存的 liftMul/camHeight 等参数
    this._tuningFromStorage = false;

    const applyTuningEntry = (rawTuning, manualCam, fromTag) => {
      if (!rawTuning || typeof rawTuning !== "object" || Array.isArray(rawTuning)) return false;
      const safe = this.sanitizeTuningForVisibility(rawTuning);
      const tier = Number(this.data.displayFormTier) || 1;
      if (this.data.staticDisplay && tier >= 2) {
        safe.camHeightMul = Math.max(Number(safe.camHeightMul || 0), 0.75);
        safe.lookAtHeightMul = Math.max(Number(safe.lookAtHeightMul || 0), 0.32);
        safe.camDistMul = Math.max(Number(safe.camDistMul || 1.2), 2.1);
        safe.liftMul = Math.max(Number(safe.liftMul || 0), TUNING_LIMITS.liftMul.min);
      }
      this.setData(
        { tuning: safe, tuningPercent: buildTuningPercent(safe) },
        () => {
          this._tuningLoadedKey = this.getTuningStorageKey();
          this._tuningFromStorage = fromTag === "server" || fromTag === "local";
          this._manualCamera = manualCam;
          if (typeof done === "function") done();
        }
      );
      return true;
    };

    const suffix = this.getTierStorageSuffix();
    const serverSlot = (this._serverFormViewTuning || {})[suffix];
    if (serverSlot && serverSlot.tuning && typeof serverSlot.tuning === "object" && !Array.isArray(serverSlot.tuning)) {
      let cam = null;
      if (serverSlot.camera && typeof serverSlot.camera === "object") {
        const pos = serverSlot.camera.pos || {};
        const lookAt = serverSlot.camera.lookAt || {};
        const px = Number(pos.x);
        const py = Number(pos.y);
        const pz = Number(pos.z);
        const lx = Number(lookAt.x);
        const ly = Number(lookAt.y);
        const lz = Number(lookAt.z);
        if ([px, py, pz, lx, ly, lz].every((v) => Number.isFinite(v))) {
          cam = { pos: { x: px, y: py, z: pz }, lookAt: { x: lx, y: ly, z: lz } };
        }
      }
      if (applyTuningEntry(serverSlot.tuning, cam, "server")) return;
    }

    try {
      const key = this.getTuningStorageKey();
      let raw = wx.getStorageSync(key);
      if ((!raw || typeof raw !== "object" || Array.isArray(raw)) && this.getLegacyTuningStorageKey) {
        raw = wx.getStorageSync(this.getLegacyTuningStorageKey());
      }
      if (raw && typeof raw === "object" && !Array.isArray(raw)) {
        const camLocal = this._loadManualCameraFromStorage();
        if (applyTuningEntry(raw, camLocal, "local")) return;
      }
    } catch (e) {}
    this._tuningLoadedKey = this.getTuningStorageKey();
    this._manualCamera = this._loadManualCameraFromStorage();
    if (typeof done === "function") done();
  },

  _cancelSyncViewTuningToServer() {
    if (this._viewTuningSyncTimer) {
      try {
        clearTimeout(this._viewTuningSyncTimer);
      } catch (e) {}
      this._viewTuningSyncTimer = null;
    }
  },

  _scheduleSyncViewTuningToServer() {
    if (!this.data.mascotId) return;
    if (this._viewTuningSyncTimer) {
      try {
        clearTimeout(this._viewTuningSyncTimer);
      } catch (e) {}
    }
    this._viewTuningSyncTimer = setTimeout(() => {
      this._viewTuningSyncTimer = null;
      this._flushViewTuningToServer().catch(() => {});
    }, 800);
  },

  _flushViewTuningToServer() {
    const mid = String(this.data.mascotId || "").trim();
    if (!mid) return Promise.resolve(null);
    const formKey = this.getTierStorageSuffix();
    const tuning = this.sanitizeTuningForVisibility(this.data.tuning || {});
    const cam = this._manualCamera;
    const clearCam = !(cam && typeof cam === "object");
    return postCompanionSetViewTuning(
      mid,
      formKey,
      tuning,
      clearCam ? undefined : cam,
      clearCam
    )
      .then((data) => {
        const fvt = data && data.form_view_tuning;
        if (fvt && typeof fvt === "object" && !Array.isArray(fvt)) {
          this._serverFormViewTuning = { ...fvt };
        }
        return data;
      });
  },

  _loadManualCameraFromStorage() {
    try {
      const key = this.getCameraStorageKey();
      let raw = wx.getStorageSync(key);
      // 兼容旧数据：如果新 key 没数据，回退到旧 key
      if ((!raw || typeof raw !== "object") && this.getLegacyCameraStorageKey) {
        raw = wx.getStorageSync(this.getLegacyCameraStorageKey());
      }
      if (!raw || typeof raw !== "object") return null;
      const pos = raw.pos || {};
      const lookAt = raw.lookAt || {};
      const px = Number(pos.x), py = Number(pos.y), pz = Number(pos.z);
      const lx = Number(lookAt.x), ly = Number(lookAt.y), lz = Number(lookAt.z);
      if (![px, py, pz, lx, ly, lz].every((v) => Number.isFinite(v))) return null;
      return {
        pos: { x: px, y: py, z: pz },
        lookAt: { x: lx, y: ly, z: lz },
      };
    } catch (e) {
      return null;
    }
  },

  toggleTuning() {
    if (this._guardModelBusy("模型正在加载中…")) return;
    const needReload = this._tuningLoadedKey !== this.getTuningStorageKey();
    if (needReload) {
      return this.loadTuningFromStorage(() => this.setData({ showTuning: !this.data.showTuning }));
    }
    this.setData({ showTuning: !this.data.showTuning });
  },

  clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  },

  _getMouseXY(e) {
    // 微信开发者工具/不同端 mouse 事件的字段不完全一致：
    // - 常见：e.detail.x / e.detail.y
    // - 备选：e.pageX/e.pageY、e.clientX/e.clientY
    const d = (e && e.detail) ? e.detail : {};
    const xCandidates = [
      d && d.x,
      e && e.pageX,
      e && e.clientX,
    ];
    const yCandidates = [
      d && d.y,
      e && e.pageY,
      e && e.clientY,
    ];

    const pick = (arr) => {
      for (let i = 0; i < arr.length; i++) {
        const v = arr[i];
        if (v === undefined || v === null) continue;
        const n = Number(v);
        // 允许 0：不要用 ||，否则 0 会被当成 falsy
        if (Number.isFinite(n)) return n;
      }
      return 0;
    };

    return { x: pick(xCandidates), y: pick(yCandidates) };
  },

  _snapshotPose(tag) {
    // 只用于调试动作展示“为何不能回原位”
    try {
      if (!this._threeRoot || !this._threeCamera) return null;
      const root = this._threeRoot;
      const cam = this._threeCamera;
      const orbit = (typeof this._camGetOrbitBase === "function") ? this._camGetOrbitBase() : null;
      const pos = root.position || { x: 0, y: 0, z: 0 };
      const scale = root.scale || { x: 1, y: 1, z: 1 };
      const cpos = cam.position || { x: 0, y: 0, z: 0 };
      return {
        tag: String(tag || ""),
        rootPos: { x: Number(pos.x), y: Number(pos.y), z: Number(pos.z) },
        rootScale: { x: Number(scale.x), y: Number(scale.y), z: Number(scale.z) },
        camPos: { x: Number(cpos.x), y: Number(cpos.y), z: Number(cpos.z) },
        orbit: orbit ? { radius: orbit.radius, yaw: orbit.yaw, pitch: orbit.pitch, pivot: orbit.pivot } : null,
      };
    } catch (e) {
      return null;
    }
  },

  sanitizeTuningForVisibility(tuning) {
    const t = { ...(tuning || {}) };
    Object.keys(TUNING_LIMITS).forEach((k) => {
      const lim = TUNING_LIMITS[k];
      t[k] = this.clamp(Number(t[k] ?? lim.default), lim.min, lim.max);
    });
    return t;
  },

  resetTuning() {
    const next = { ...DEFAULT_TUNING };
    this.setData({ tuning: next, tuningPercent: buildTuningPercent(next) }, () => {
      this._manualCamera = null;
      this.applyTuningToScene();
      this.saveTuningManual();
    });
  },

  saveTuningToStorage() {
    try {
      const safeTuning = this.sanitizeTuningForVisibility(this.data.tuning || {});
      wx.setStorageSync(this.getTuningStorageKey(), safeTuning);
      this._scheduleSyncViewTuningToServer();
      return true;
    } catch (e) {}
    return false;
  },

  saveTuningManual() {
    const safe = this.sanitizeTuningForVisibility(this.data.tuning || {});
    const eggFront = !!(this.data.eggModelActive && !this.data.eggCracked);
    this.setData({ tuning: safe, tuningPercent: buildTuningPercent(safe) }, () => {
      // 蛋期只用滑条相机，不写入「手动相机」以免下次加载又盖住 targetSize/fov
      if (eggFront) {
        this._manualCamera = null;
        try {
          wx.removeStorageSync(this.getCameraStorageKey());
        } catch (eClear) {}
      } else {
        try {
          if (this._threeCamera && typeof this._camGetOrbitBase === "function") {
            const orbit = this._camGetOrbitBase();
            const camera = this._threeCamera;
            const pivot = orbit && orbit.pivot ? orbit.pivot : null;
            if (pivot && typeof camera.lookAt === "function") {
              this._manualCamera = {
                pos: {
                  x: Number(camera.position.x),
                  y: Number(camera.position.y),
                  z: Number(camera.position.z),
                },
                lookAt: {
                  x: Number(pivot.x),
                  y: Number(pivot.y),
                  z: Number(pivot.z),
                },
              };
              wx.setStorageSync(this.getCameraStorageKey(), this._manualCamera);
            }
          }
        } catch (e) {}
      }

      let ok = false;
      try {
        const safeTuning = this.sanitizeTuningForVisibility(this.data.tuning || {});
        wx.setStorageSync(this.getTuningStorageKey(), safeTuning);
        ok = true;
      } catch (e) {}
      this._cancelSyncViewTuningToServer();
      this.applyTuningToScene();
      if (ok) {
        this._flushViewTuningToServer()
          .then(() => {
            wx.showToast({ title: "已保存并同步", icon: "success" });
          })
          .catch(() => {
            wx.showToast({ title: "已保存在本机，服务器同步失败", icon: "none" });
          });
      } else {
        wx.showToast({ title: "保存失败，请重试", icon: "none" });
      }
    });
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
    // 提前给一个“已经在进行”的观感
    this._modelProgressFakeValue = 6;
    this.setData({ modelLoadProgress: 6, modelLoadStageText: "魔法准备中…" });

    if (this._modelProgressFakeTimer) clearInterval(this._modelProgressFakeTimer);
    this._modelProgressFakeTimer = setInterval(() => {
      // 发生了新的加载/切形态：忽略旧 tick
      if (this._modelProgressFakeToken !== token) return;
      const cur = Number(this.data.modelLoadProgress || 0);
      const base = Math.max(this._modelProgressFakeValue || 0, cur);
      // 伪进度加速有“飘”的感觉（避免每次都线性）
      const step = 0.9 + Math.random() * 1.4; // ~0.9~2.3
      const next = Math.min(98, base + step);
      this._modelProgressFakeValue = next;
      this.setData({
        modelLoadProgress: Math.floor(next * 10) / 10,
        modelLoadStageText: next > 55 ? "魔法正在孵化…" : "魔法正在解封…",
      });
      if (next >= 98) this._stopModelProgressFake();
    }, 120);
  },

  _syncModelLoadProgressFromXhr(xhr, token) {
    // 只处理当前 token 对应的加载
    if (this._modelLoadToken !== token) return;
    const loaded =
      Number(xhr && (typeof xhr.loaded === "number" ? xhr.loaded : xhr.loadedBytes)) || 0;
    const total = Number(xhr && (typeof xhr.total === "number" ? xhr.total : xhr.totalBytes)) || 0;

    // 部分端 onProgress 可能拿不到 total
    if (!total || total <= 0) return;

    let percent = (loaded / total) * 100;
    if (!Number.isFinite(percent)) return;
    percent = Math.max(0, Math.min(99, percent));

    this._modelProgressFakeToken = token; // 保持一致，避免真实进度后伪 tick 仍然在改
    this._modelProgressFakeValue = Math.max(this._modelProgressFakeValue || 0, percent);
    this.setData({
      modelLoadProgress: Math.floor(percent * 10) / 10,
      modelLoadStageText: percent > 55 ? "魔法正在孵化…" : "魔法正在解封…",
    });

    // 当接近完成，停止伪进度（最终 100% 由 onGltfLoaded 决定）
    if (percent >= 98) this._stopModelProgressFake();
  },

  onModelMagicTap() {
    if (!this.data.modelLoading && !this.data.modelFailed) return;
    // 多次点点会让伪进度更快一些（只“加观感”，不强行加速真实下载）
    const nextCount = Number(this.data.modelMagicCount || 0) + 1;
    const curP = Number(this.data.modelLoadProgress || 0);
    const bump = 3 + Math.min(10, nextCount * 1.1); // 每点一次加大一点
    const nextP = Math.min(98, Math.max(curP, curP + bump));

    // egg 期敲碎小游戏：用点击次数推“破壳进度条”
    if (this.data.eggModelActive && !this.data.eggCracked) {
      const goal = Number(this.data.hatchTapGoal || 12) || 12;
      const nextTap = Math.min(goal, Number(this.data.hatchTapCount || 0) + 1);
      this.setData({
        hatchTapCount: nextTap,
        hatchProgress: Math.floor((nextTap / goal) * 100),
        hatchRemain: Math.max(0, goal - nextTap),
      });
      // 每点一下给一点抖动+闪光
      this.setData({ hatchShakeOn: true, hatchFlashOn: true });
      setTimeout(() => this.setData({ hatchShakeOn: false }), 140);
      setTimeout(() => this.setData({ hatchFlashOn: false }), 220);

      // 关键：后续点击发生在遮罩上，这里必须在“满进度”时立即标记 eggCracked，
      // 否则永远不会切到碎蛋模型。
      if (nextTap >= goal) {
        const mid = String(this.data.mascotId || "");
        // 进度满：等待预下载完成后再无缝切换
        this._hatchReadyToCrack = true;
      }

      // 让蛋本体抖动（不是框）
      this._triggerEggWobble();
    }

    this.setData({
      modelMagicCount: nextCount,
      modelLoadProgress: Math.floor(nextP * 10) / 10,
      modelLoadStageText: nextCount % 3 === 0 ? "小魔法命中！" : "点点加速中…",
    });

    // 允许点击直接重试并继续魔法遮罩：
    // - modelFailed：候选模型全失败
    // - modelLoading 且处于 repair 场景：防止用户一直卡在“滴滴魔法修复中…”
    if (this.data.viewMode === "3d" && (this.data.modelFailed || this.data.modelLoadScene === "repair")) {
      this.retryPetThree();
    }

    // 若碎蛋模型已经加载好，且点击进度已满，则无缝切到碎蛋形态
    this._maybeCommitEggCrack();
  },

  onTuningSliderChanging(e) {
    const key = String(e.currentTarget.dataset.key || "");
    const value = Number(e.detail.value);
    if (!key) return;
    // 用户通过滑条改变时，手动相机视角失效，交由 applyTuningToScene 按滑条复现
    this._manualCamera = null;
    const next = { ...this.data.tuning };
    next[key] = this.scaleSliderValue(key, value);
    this.setData({ tuning: next, tuningPercent: buildTuningPercent(next) }, () => this.applyTuningToScene());
  },

  onTuningSliderChange(e) {
    this.onTuningSliderChanging(e);
    this.saveTuningToStorage();
  },

  scaleSliderValue(key, percent) {
    return this.clampTuningNumber(key, percentToValue(key, percent));
  },

  onTuningNumberInput(e) {
    const key = String(e.currentTarget.dataset.key || "");
    if (!key) return;
    const raw = String(e.detail.value || "").trim();
    if (!this._tuningDraft) this._tuningDraft = {};
    this._tuningDraft[key] = raw;
  },

  onTuningNumberConfirm(e) {
    const key = String(e.currentTarget.dataset.key || "");
    const raw = String(e.detail.value || "").trim();
    if (!key) return;
    const v = Number(raw);
    if (!Number.isFinite(v)) {
      wx.showToast({ title: "请输入数字", icon: "none" });
      return;
    }
    const next = { ...this.data.tuning };
    next[key] = this.clampTuningNumber(key, v);
    // 数字输入改变时，同步失效手动相机视角
    this._manualCamera = null;
    this.setData({ tuning: next, tuningPercent: buildTuningPercent(next) }, () => {
      this.applyTuningToScene();
      this.saveTuningToStorage();
    });
  },

  clampTuningNumber(key, v) {
    const lim = TUNING_LIMITS[key];
    if (!lim) return v;
    return this.clamp(v, lim.min, lim.max);
  },

  applyTuningToScene() {
    const root = this._threeRoot;
    const camera = this._threeCamera;
    if (!root || !camera || !this._fitBaseScale || !this._fitBasePos || !this._fitBaseSizeY) return;

    const tier = Number(this.data.displayFormTier) || 1;
    const isStaticHigh = !!this.data.staticDisplay && tier >= 2;

    const isEggFrontStage = !!this.data.eggModelActive && !this.data.eggCracked;
    const defaultBaseRotY = defaultBaseRotYDegForPersona(this.data.personaId);
    // 蛋期与其它形态一样走调参：此前强制 90° 会忽略 baseRotYDeg，且与狐狸等模型默认朝侧向不匹配
    const baseDeg = Number.isFinite(Number(this.data.tuning.baseRotYDeg))
      ? Number(this.data.tuning.baseRotYDeg)
      : defaultBaseRotY;
    this._baseRotY = (baseDeg * Math.PI) / 180;
    root.rotation.y = this._baseRotY;

    const fov = Number(this.data.tuning.fov || 45);
    camera.fov = fov;

    const targetSize = Number(this.data.tuning.targetSize || 3.0);
    const s = this._fitBaseScale * targetSize;
    root.scale.set(s, s, s);

    const fitSizeY = this._fitBaseSizeY * targetSize;
    const fovRad = fov * (Math.PI / 180);
    const camDist = (fitSizeY * 0.5) / Math.tan(fovRad * 0.5);

    // tier2/3 静态展示：强制相机高度/注视高度下限，避免“相机落在模型下面”
    const camHeightMul = isStaticHigh ? Math.max(Number(this.data.tuning.camHeightMul || 0.18), 0.75) : Number(this.data.tuning.camHeightMul || 0.18);
    const lookAtHeightMul = isStaticHigh ? Math.max(Number(this.data.tuning.lookAtHeightMul || 0.12), 0.32) : Number(this.data.tuning.lookAtHeightMul || 0.12);
    const camDistMul = isStaticHigh ? Math.max(Number(this.data.tuning.camDistMul || 1.2), 2.1) : Number(this.data.tuning.camDistMul || 1.2);

    camera.position.set(
      0,
      fitSizeY * camHeightMul,
      camDist * camDistMul
    );
    camera.near = Math.max(0.01, camDist / 200);
    camera.far = Math.max(100, camDist * 20);
    if (typeof camera.lookAt === "function") {
      // 让注视点始终落在“模型自身”附近，避免固定看世界原点导致视角偏低/偏移
      const pivotX = Number(root.position.x || 0);
      // 关键点：不要让“注视点”跟着 liftMul 一起移动
      // 否则 liftMul 主要会被 lookAt 抵消，用户会感觉“调不下去/居中没效果”
      const baseY = Number(this._fitBasePos?.y || 0);
      const pivotY = baseY + fitSizeY * lookAtHeightMul;
      const pivotZ = Number(root.position.z || 0);
      camera.lookAt(pivotX, pivotY, pivotZ);
    }
    if (typeof camera.updateProjectionMatrix === "function") camera.updateProjectionMatrix();

    root.position.x = Number(this._fitBasePos.x || 0);
    root.position.y = Number(this._fitBasePos.y || 0) + fitSizeY * Number(this.data.tuning.liftMul || 0.1);
    root.position.z = Number(this._fitBasePos.z || 0);

    // 若用户曾“保存并复用”过手动相机位置，则优先复现该视角（蛋期除外：否则拖拽/保存的相机会盖住滑条上的 targetSize、fov、camDist 等）
    if (
      !isEggFrontStage &&
      this._manualCamera &&
      this._manualCamera.pos &&
      this._manualCamera.lookAt
    ) {
      const pos = this._manualCamera.pos;
      const la = this._manualCamera.lookAt;
      const px = Number(pos.x), py = Number(pos.y), pz = Number(pos.z);
      const lx = Number(la.x), ly = Number(la.y), lz = Number(la.z);
      if ([px, py, pz, lx, ly, lz].every((v) => Number.isFinite(v)) && typeof camera.lookAt === "function") {
        camera.position.set(px, py, pz);
        camera.lookAt(lx, ly, lz);
        if (typeof camera.updateProjectionMatrix === "function") camera.updateProjectionMatrix();
      }
    }

    // 即便存在“保存并复用”的手动相机，也要保证高阶静态展示时相机不落在地面附近
    if (isStaticHigh && camera.position && Number.isFinite(Number(camera.position.y))) {
      const minCamY = fitSizeY * 0.75;
      if (camera.position.y < minCamY) {
        camera.position.set(camera.position.x, minCamY, camera.position.z);
        if (typeof camera.updateProjectionMatrix === "function") camera.updateProjectionMatrix();
      }
    }
  },

  _applyRootTuningToScene() {
    // 仅更新模型摆放/缩放（不碰相机），用于动作播放期间锁定“你调好的整体大小/位置”
    const root = this._threeRoot;
    if (!root || !this._fitBaseScale || !this._fitBasePos || !this._fitBaseSizeY) return;

    const defaultBaseRotY = defaultBaseRotYDegForPersona(this.data.personaId);
    const baseDeg = Number.isFinite(Number(this.data.tuning.baseRotYDeg))
      ? Number(this.data.tuning.baseRotYDeg)
      : defaultBaseRotY;
    this._baseRotY = (baseDeg * Math.PI) / 180;
    root.rotation.y = this._baseRotY;

    const targetSize = Number(this.data.tuning.targetSize || 3.0);
    const s = this._fitBaseScale * targetSize;
    root.scale.set(s, s, s);

    const fitSizeY = this._fitBaseSizeY * targetSize;
    root.position.x = Number(this._fitBasePos.x || 0);
    root.position.y = Number(this._fitBasePos.y || 0) + fitSizeY * Number(this.data.tuning.liftMul || 0.1);
    root.position.z = Number(this._fitBasePos.z || 0);
  },

  _captureActionBonePose() {
    // 动作 clip 主要修改 skinned mesh 的骨骼姿态。
    // 为了“只要恢复即可”，这里在动作开始前快照骨骼本地变换，结束后强制还原。
    try {
      const root = this._threeRoot;
      if (!root || typeof root.traverse !== "function") return;

      const snapshot = {};
      let count = 0;
      root.traverse((obj) => {
        if (!obj || !obj.isSkinnedMesh) return;
        const sk = obj.skeleton;
        if (!sk || !Array.isArray(sk.bones)) return;
        sk.bones.forEach((bone) => {
          if (!bone || !bone.isBone) return;
          // 确保矩阵与 position/quaternion/scale 同步
          if (typeof bone.updateMatrix === "function") bone.updateMatrix();
          snapshot[bone.uuid] = {
            p: { x: bone.position.x, y: bone.position.y, z: bone.position.z },
            q: { x: bone.quaternion.x, y: bone.quaternion.y, z: bone.quaternion.z, w: bone.quaternion.w },
            s: { x: bone.scale.x, y: bone.scale.y, z: bone.scale.z },
          };
          count++;
        });
      });

      this._actionBonePoseSnapshot = snapshot;
      this._actionBonePoseSnapshotCount = count;
      if (ACTION_DEBUG) console.log("[pet-detail][bone-pose-capture]", { count });
    } catch (e) {}
  },

  _restoreActionBonePose() {
    try {
      const root = this._threeRoot;
      const snap = this._actionBonePoseSnapshot;
      if (!root || !snap) return;

      root.traverse((obj) => {
        if (!obj || !obj.isSkinnedMesh) return;
        const sk = obj.skeleton;
        if (!sk || !Array.isArray(sk.bones)) return;
        sk.bones.forEach((bone) => {
          if (!bone || !bone.isBone) return;
          const bs = snap[bone.uuid];
          if (!bs) return;
          bone.position.set(bs.p.x, bs.p.y, bs.p.z);
          bone.quaternion.set(bs.q.x, bs.q.y, bs.q.z, bs.q.w);
          bone.scale.set(bs.s.x, bs.s.y, bs.s.z);
          if (typeof bone.updateMatrix === "function") bone.updateMatrix();
        });
        if (sk && typeof sk.update === "function") sk.update();
      });

      if (typeof root.updateMatrixWorld === "function") root.updateMatrixWorld(true);
      this._actionBonePoseSnapshot = null;
      this._actionBonePoseSnapshotCount = 0;
    } catch (e) {}
  },

  _captureActionBaseTransforms() {
    // 动作 clip 可能会影响 root 以外的节点（骨骼、局部父节点缩放等）。
    // 为了“恢复到你点动作前的视觉形态”，需要捕获整个层级的本地变换。
    try {
      const root = this._threeRoot;
      if (!root || typeof root.traverse !== "function") return;

      const map = {};
      let count = 0;
      root.traverse((obj) => {
        if (!obj) return;
        map[obj.uuid] = {
          p: { x: obj.position.x, y: obj.position.y, z: obj.position.z },
          q: { x: obj.quaternion.x, y: obj.quaternion.y, z: obj.quaternion.z, w: obj.quaternion.w },
          s: { x: obj.scale.x, y: obj.scale.y, z: obj.scale.z },
          mt: Array.isArray(obj.morphTargetInfluences) ? obj.morphTargetInfluences.slice() : null,
        };
        count++;
      });

      // 有些端/模型中 bones 可能不在 traverse 到的层级里：
      // 直接把 skeleton.bones 强制纳入快照，避免恢复不彻底导致“还缩小一下”
      try {
        root.traverse((obj) => {
          if (!obj || !obj.isSkinnedMesh) return;
          const sk = obj.skeleton;
          if (!sk || !Array.isArray(sk.bones)) return;
          sk.bones.forEach((bone) => {
            if (!bone) return;
            if (!map[bone.uuid]) {
              map[bone.uuid] = {
                p: { x: bone.position.x, y: bone.position.y, z: bone.position.z },
                q: { x: bone.quaternion.x, y: bone.quaternion.y, z: bone.quaternion.z, w: bone.quaternion.w },
                s: { x: bone.scale.x, y: bone.scale.y, z: bone.scale.z },
              };
              count++;
            }
          });
        });
      } catch (e) {}

      this._actionBaseTransforms = map;
      this._actionBaseTransformsCount = count;
      if (ACTION_DEBUG) console.log("[pet-detail][action-transform-capture]", { count });
    } catch (e) {}
  },

  _applyActionBaseTransforms() {
    // 用动作前快照恢复全层级变换，避免只看 rootPos/rootScale 导致恢复不彻底。
    try {
      const root = this._threeRoot;
      const base = this._actionBaseTransforms;
      if (!root || !base || typeof root.traverse !== "function") return false;

      let applied = 0;
      root.traverse((obj) => {
        if (!obj) return;
        const snap = base[obj.uuid];
        if (!snap) return;
        obj.position.set(snap.p.x, snap.p.y, snap.p.z);
        obj.quaternion.set(snap.q.x, snap.q.y, snap.q.z, snap.q.w);
        obj.scale.set(snap.s.x, snap.s.y, snap.s.z);
        if (snap.mt && Array.isArray(obj.morphTargetInfluences)) {
          // 还原 morph 权重（动作可能通过 blendshape 改变轮廓/占屏大小）
          const src = snap.mt;
          for (let i = 0; i < src.length; i++) {
            if (obj.morphTargetInfluences[i] === undefined) break;
            obj.morphTargetInfluences[i] = src[i];
          }
        }
        if (typeof obj.updateMatrix === "function") obj.updateMatrix();
        applied++;
      });

      if (typeof root.updateMatrixWorld === "function") root.updateMatrixWorld(true);

      root.traverse((obj) => {
        if (!obj || !obj.isSkinnedMesh) return;
        if (obj.skeleton) {
          if (typeof obj.skeleton.update === "function") obj.skeleton.update();
          // 进一步刷新 boneMatrices（部分端 update 后仍可能延迟刷新）
          if (typeof obj.skeleton.calculateInverses === "function") obj.skeleton.calculateInverses();
        }
      });

      // 如果 bones 不在 traverse 里，也要显式恢复 skeleton.bones[] 的变换
      try {
        root.traverse((obj) => {
          if (!obj || !obj.isSkinnedMesh) return;
          const sk = obj.skeleton;
          if (!sk || !Array.isArray(sk.bones)) return;
          sk.bones.forEach((bone) => {
            if (!bone) return;
            const snap = base[bone.uuid];
            if (!snap) return;
            bone.position.set(snap.p.x, snap.p.y, snap.p.z);
            bone.quaternion.set(snap.q.x, snap.q.y, snap.q.z, snap.q.w);
            bone.scale.set(snap.s.x, snap.s.y, snap.s.z);
            if (typeof bone.updateMatrix === "function") bone.updateMatrix();
          });
        });
        if (typeof root.updateMatrixWorld === "function") root.updateMatrixWorld(true);
      } catch (e) {}

      if (ACTION_DEBUG) console.log("[pet-detail][action-transform-restore]", { applied, total: this._actionBaseTransformsCount });
      return true;
    } catch (e) {
      return false;
    }
  },

  _captureActionBaseBox() {
    // 记录动作开始时的模型包围盒，用于在动作播放期间做“尺寸/居中”补偿
    try {
      const THREE = this._THREE;
      const root = this._threeRoot;
      if (!THREE || !root) return;
      if (!this._actionBoxTmpSizeVec3) this._actionBoxTmpSizeVec3 = new THREE.Vector3();
      if (!this._actionBoxTmpCenterVec3) this._actionBoxTmpCenterVec3 = new THREE.Vector3();
      if (!this._actionBoxTmpBox) this._actionBoxTmpBox = new THREE.Box3();
      if (!this._actionBoxTmpPointVec3) this._actionBoxTmpPointVec3 = new THREE.Vector3();
      if (!this._actionBoxTmpPointVec3) this._actionBoxTmpPointVec3 = new THREE.Vector3();
      const box = this._actionBoxTmpBox;
      box.makeEmpty();

      root.traverse((obj) => {
        if (!obj) return;
        const isSkinned = !!obj.isSkinnedMesh;
        const isMesh = !!obj.isMesh || isSkinned;
        if (!isMesh) return;

        const matrixWorld = obj.matrixWorld;
        let bb = null;
        if (isSkinned) {
          try {
            if (typeof obj.computeBoundingBox === "function") obj.computeBoundingBox();
          } catch (e) {}
          bb = obj.boundingBox || (obj.geometry && obj.geometry.boundingBox) || null;
        } else if (obj.geometry) {
          if (obj.geometry.boundingBox) bb = obj.geometry.boundingBox;
          else if (typeof obj.geometry.computeBoundingBox === "function") {
            try { obj.geometry.computeBoundingBox(); } catch (e) {}
            bb = obj.geometry.boundingBox || null;
          }
        }

        if (!bb || !bb.min || !bb.max) return;
        const min = bb.min;
        const max = bb.max;
        box.expandByPoint(this._actionBoxTmpPointVec3.set(min.x, min.y, min.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(min.x, min.y, max.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(min.x, max.y, min.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(min.x, max.y, max.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(max.x, min.y, min.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(max.x, min.y, max.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(max.x, max.y, min.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(max.x, max.y, max.z).applyMatrix4(matrixWorld));
      });

      const size = box.getSize(this._actionBoxTmpSizeVec3);
      const center = box.getCenter(this._actionBoxTmpCenterVec3);
      const maxDim = Math.max(size.x, size.y, size.z) || 1;
      this._actionBaseBox = {
        maxDim,
        center: { x: center.x, y: center.y, z: center.z },
        rootPos: { x: root.position.x, y: root.position.y, z: root.position.z },
        rootScale: { x: root.scale.x, y: root.scale.y, z: root.scale.z },
      };
    } catch (e) {}
  },

  _applyActionBoxCompensation() {
    // 让动作播放期间模型的“整体尺寸/居中”尽量不变
    try {
      if (!this._actionBaseBox) return;
      const THREE = this._THREE;
      const root = this._threeRoot;
      if (!THREE || !root) return;
      if (!this._actionBoxTmpSizeVec3) this._actionBoxTmpSizeVec3 = new THREE.Vector3();
      if (!this._actionBoxTmpCenterVec3) this._actionBoxTmpCenterVec3 = new THREE.Vector3();
      if (!this._actionBoxTmpBox) this._actionBoxTmpBox = new THREE.Box3();

      const box = this._actionBoxTmpBox;
      box.makeEmpty();

      root.traverse((obj) => {
        if (!obj) return;
        const isSkinned = !!obj.isSkinnedMesh;
        const isMesh = !!obj.isMesh || isSkinned;
        if (!isMesh) return;

        const matrixWorld = obj.matrixWorld;
        let bb = null;
        if (isSkinned) {
          try {
            if (typeof obj.computeBoundingBox === "function") obj.computeBoundingBox();
          } catch (e) {}
          bb = obj.boundingBox || (obj.geometry && obj.geometry.boundingBox) || null;
        } else if (obj.geometry) {
          if (obj.geometry.boundingBox) bb = obj.geometry.boundingBox;
          else if (typeof obj.geometry.computeBoundingBox === "function") {
            try { obj.geometry.computeBoundingBox(); } catch (e) {}
            bb = obj.geometry.boundingBox || null;
          }
        }

        if (!bb || !bb.min || !bb.max) return;
        const min = bb.min;
        const max = bb.max;
        box.expandByPoint(this._actionBoxTmpPointVec3.set(min.x, min.y, min.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(min.x, min.y, max.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(min.x, max.y, min.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(min.x, max.y, max.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(max.x, min.y, min.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(max.x, min.y, max.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(max.x, max.y, min.z).applyMatrix4(matrixWorld));
        box.expandByPoint(this._actionBoxTmpPointVec3.set(max.x, max.y, max.z).applyMatrix4(matrixWorld));
      });

      const size = box.getSize(this._actionBoxTmpSizeVec3);
      const center = box.getCenter(this._actionBoxTmpCenterVec3);
      const curMaxDim = Math.max(size.x, size.y, size.z) || 1;
      const ratio = this._actionBaseBox.maxDim / curMaxDim;
      if (!Number.isFinite(ratio) || ratio <= 0) return;

      if (ACTION_DEBUG && !this._actionBoxDebugLogged) {
        this._actionBoxDebugLogged = true;
        console.log("[pet-detail][action-box]", {
          baseMaxDim: this._actionBaseBox.maxDim,
          curMaxDim,
          ratio,
          baseCenter: this._actionBaseBox.center,
          curCenter: { x: center.x, y: center.y, z: center.z },
        });
      }

      // 按比例缩放（保持整体尺寸）
      const rs = this._actionBaseBox.rootScale;
      root.scale.set(rs.x * ratio, rs.y * ratio, rs.z * ratio);

      // 按中心对齐（保持居中）
      const bc = this._actionBaseBox.center;
      root.position.set(
        this._actionBaseBox.rootPos.x + (bc.x - center.x),
        this._actionBaseBox.rootPos.y + (bc.y - center.y),
        this._actionBaseBox.rootPos.z + (bc.z - center.z)
      );
    } catch (e) {}
  },

  onCanvasTouchStart(e) {
    this.setData({ canvasInteract: true });
    if (this.data.viewMode !== "3d") return;
    if (!this._threeCamera || !this._threeRoot) return;
    // 用户开始触控交互后，暂停自动环绕展示
    this._autoOrbitEnabled = false;
    const touches = (e && e.touches) ? e.touches : [];
    if (!touches.length) return;

    // 交互仅用于调参面板打开时：模拟 C4D 的“左键旋转 / 右键拖动 / 滚轮缩放”
    // 触屏映射：
    // - 单指拖动：旋转（对应左键旋转）
    // - 双指：捏合缩放 + 拖动平移（对应滚轮缩放 + 右键拖动平移）
    if (!this._camPivotOffset) this._camPivotOffset = { x: 0, y: 0, z: 0 };

    if (touches.length === 1) {
      const t = touches[0];
      const orbit = this._camGetOrbitBase();
      const tierLocal = Number(this.data.displayFormTier) || 1;
      const isLockedPitch = !!this.data.staticDisplay && tierLocal >= 2;
      const pitchDelta = isLockedPitch ? ROTATE_PITCH_DELTA_STATIC : 999;
      const pitchMin = this._clamp(orbit.pitch - pitchDelta, ROTATE_PITCH_MIN, ROTATE_PITCH_MAX);
      const pitchMax = this._clamp(orbit.pitch + pitchDelta, ROTATE_PITCH_MIN, ROTATE_PITCH_MAX);
      this._camInteract = {
        mode: "rotate",
        startX: Number(t.pageX || 0),
        startY: Number(t.pageY || 0),
        startYaw: orbit.yaw,
        startPitch: orbit.pitch,
        pitchMin,
        pitchMax,
      };
      return;
    }

    // 取前两指做缩放/平移
    const t1 = touches[0];
    const t2 = touches[1];
    const dx = Number(t1.pageX || 0) - Number(t2.pageX || 0);
    const dy = Number(t1.pageY || 0) - Number(t2.pageY || 0);
    const startDist = Math.hypot(dx, dy) || 1;
    const midX = (Number(t1.pageX || 0) + Number(t2.pageX || 0)) / 2;
    const midY = (Number(t1.pageY || 0) + Number(t2.pageY || 0)) / 2;

    const orbit = this._camGetOrbitBase();
    this._camInteract = {
      mode: "zoomPan",
      startDist,
      startMidX: midX,
      startMidY: midY,
      startRadius: orbit.radius,
      startPivotOffset: { ...this._camPivotOffset },
    };
  },
  onCanvasTouchMove(e) {
    if (!this._camInteract || this.data.viewMode !== "3d") return;
    const touches = (e && e.touches) ? e.touches : [];
    if (!touches.length) return;
    if (!this._threeCamera || !this._threeRoot) return;

    const mode = this._camInteract.mode;
    if (mode === "rotate" && touches.length === 1) {
      const t = touches[0];
      const x = Number(t.pageX || 0);
      const y = Number(t.pageY || 0);
      const dx = x - this._camInteract.startX;
      const dy = y - this._camInteract.startY;

      const orbit = this._camGetOrbitBase();
      const yaw = this._camInteract.startYaw + dx * 0.005; // 水平旋转灵敏度
      const desiredPitch = this._camInteract.startPitch + dy * 0.004;
      const pitch = this._clamp(
        desiredPitch,
        this._camInteract.pitchMin ?? ROTATE_PITCH_MIN,
        this._camInteract.pitchMax ?? ROTATE_PITCH_MAX
      );

      this._camApplyOrbit({ yaw, pitch, radius: orbit.radius });
      return;
    }

    if (mode === "zoomPan" && touches.length >= 2) {
      const t1 = touches[0];
      const t2 = touches[1];
      const dx2 = Number(t1.pageX || 0) - Number(t2.pageX || 0);
      const dy2 = Number(t1.pageY || 0) - Number(t2.pageY || 0);
      const dist = Math.hypot(dx2, dy2) || 1;
      const ratio = dist / this._camInteract.startDist;
      const radius = this._camInteract.startRadius / Math.max(0.2, ratio); // 捏合放大=>半径变小

      const midX = (Number(t1.pageX || 0) + Number(t2.pageX || 0)) / 2;
      const midY = (Number(t1.pageY || 0) + Number(t2.pageY || 0)) / 2;
      const dMidX = midX - this._camInteract.startMidX;
      const dMidY = midY - this._camInteract.startMidY;

      // 平移：用 world offset 近似映射
      const panScale = radius * 0.001;
      const pivotOffset = {
        x: this._camInteract.startPivotOffset.x - dMidX * panScale,
        y: this._camInteract.startPivotOffset.y + dMidY * panScale,
        z: this._camInteract.startPivotOffset.z,
      };
      this._camPivotOffset = pivotOffset;

      const orbit = this._camGetOrbitBase();
      // 旋转角度保持当前（你只需要缩放+拖动平移）
      this._camApplyOrbit({ yaw: orbit.yaw, pitch: orbit.pitch, radius });
      return;
    }
  },
  onCanvasTouchEnd() {
    this._camInteract = null;
    // 触控交互结束后恢复自动环绕
    this._scheduleAutoOrbitResume(900);
    setTimeout(() => this.setData({ canvasInteract: false }), 200);
  },

  // ===== 电脑端鼠标交互（C4D 风格）=====
  // 左键：旋转；右键：平移；滚轮：缩放
  onMouseDown(e) {
    // 只在“调参模式”时允许鼠标拖拽/缩放交互
    if (!this.data.showTuning) return;
    if (this.data.viewMode !== "3d") return;
    if (!this._threeCamera || !this._threeRoot) return;
    // 用户开始手动交互后，暂停自动环绕展示
    this._autoOrbitEnabled = false;

    // 交互约定：
    // - 左键/右键拖动：平移（拖动摄像头位置 => 对象在画面中平移）
    // - Shift/Ctrl/Meta + 左键拖动：旋转（绕观察点旋转）
    const button = Number(e && (e.button || (e.detail && e.detail.button) || 0));
    const hotRotate = !!(e && (e.shiftKey || e.ctrlKey || e.metaKey || (e.detail && (e.detail.shiftKey || e.detail.ctrlKey))));
    const mode = hotRotate ? "rotate" : "pan";

    const xy = this._getMouseXY(e);
    const x = xy.x;
    const y = xy.y;

    const orbit = this._camGetOrbitBase();
    if (!this._camPivotOffset) this._camPivotOffset = { x: 0, y: 0, z: 0 };

    if (mode === "rotate") {
      const tierLocal = Number(this.data.displayFormTier) || 1;
      const isLockedPitch = !!this.data.staticDisplay && tierLocal >= 2;
      const pitchDelta = isLockedPitch ? ROTATE_PITCH_DELTA_STATIC : 999;
      const pitchMin = this._clamp(orbit.pitch - pitchDelta, ROTATE_PITCH_MIN, ROTATE_PITCH_MAX);
      const pitchMax = this._clamp(orbit.pitch + pitchDelta, ROTATE_PITCH_MIN, ROTATE_PITCH_MAX);
      this._camInteract = {
        mode: "rotate",
        startX: x,
        startY: y,
        startYaw: orbit.yaw,
        startPitch: orbit.pitch,
        pitchMin,
        pitchMax,
      };
      return;
    }

    this._camInteract = {
      mode: "pan",
      startX: x,
      startY: y,
      startPivotOffset: { ...this._camPivotOffset },
      startYaw: orbit.yaw,
      startPitch: orbit.pitch,
      startRadius: orbit.radius,
    };
  },
  onMouseMove(e) {
    // 只在“调参模式”时允许鼠标拖拽/旋转
    if (!this.data.showTuning) return;
    if (!this._camInteract || this.data.viewMode !== "3d") return;

    const xy = this._getMouseXY(e);
    const x = xy.x;
    const y = xy.y;

    if (this._camInteract.mode === "rotate") {
      const dx = x - this._camInteract.startX;
      const dy = y - this._camInteract.startY;
      const yaw = this._camInteract.startYaw + dx * 0.005;
      const desiredPitch = this._camInteract.startPitch + dy * 0.004;
      const pitch = this._clamp(
        desiredPitch,
        this._camInteract.pitchMin ?? ROTATE_PITCH_MIN,
        this._camInteract.pitchMax ?? ROTATE_PITCH_MAX
      );
      const orbit = this._camGetOrbitBase();
      this._camApplyOrbit({ yaw, pitch, radius: orbit.radius });
      return;
    }

    if (this._camInteract.mode === "pan") {
      const dx = x - this._camInteract.startX;
      const dy = y - this._camInteract.startY;
      const panScale = this._camInteract.startRadius * 0.001;
      this._camPivotOffset = {
        x: this._camInteract.startPivotOffset.x - dx * panScale,
        y: this._camInteract.startPivotOffset.y + dy * panScale,
        z: this._camInteract.startPivotOffset.z,
      };
      this._camApplyOrbit({
        yaw: this._camInteract.startYaw,
        pitch: this._camInteract.startPitch,
        radius: this._camInteract.startRadius,
      });
      return;
    }
  },
  onMouseUp() {
    this._camInteract = null;
    // 手动交互结束后，延迟恢复自动环绕
    this._scheduleAutoOrbitResume(800);
  },
  onMouseWheel(e) {
    // 只在“调参模式”时允许鼠标滚轮缩放
    if (!this.data.showTuning) return;
    // 桌面端鼠标滚轮：优先保证 3D 模式下的缩放可用
    // 尽可能阻止事件继续触发页面滚动（微信开发者工具下尤其常见）
    try {
      if (e) {
        if (typeof e.preventDefault === "function") e.preventDefault();
        if (typeof e.stopPropagation === "function") e.stopPropagation();
      }
    } catch (err) {}

    const viewMode = this.data && this.data.viewMode;
    const hasCamera = !!(this._threeCamera && this._threeRoot);
    if (viewMode !== "3d") return;
    if (!hasCamera) return;
    // 用户缩放后，暂停自动环绕展示
    this._autoOrbitEnabled = false;

    const deltaY = (() => {
      // 兼容不同环境下字段名
      try {
        const d = e && e.detail ? e.detail : {};
        if (d.deltaY !== undefined && d.deltaY !== null) return Number(d.deltaY);
        if (d.delta !== undefined && d.delta !== null) return Number(d.delta);
        if (d.dy !== undefined && d.dy !== null) return Number(d.dy);
        if (d.wheelDelta !== undefined && d.wheelDelta !== null) return Number(d.wheelDelta);
        if (d.wheelDeltaY !== undefined && d.wheelDeltaY !== null) return Number(d.wheelDeltaY);
        if (d.scrollDelta !== undefined && d.scrollDelta !== null) return Number(d.scrollDelta);
        if (e && e.deltaY !== undefined && e.deltaY !== null) return Number(e.deltaY);
        if (e && e.delta !== undefined && e.delta !== null) return Number(e.delta);
        if (e && e.dy !== undefined && e.dy !== null) return Number(e.dy);
        if (e && e.wheelDelta !== undefined && e.wheelDelta !== null) return Number(e.wheelDelta);
        return Number(0);
      } catch (err) {
        return Number(0);
      }
    })();

    if (!Number.isFinite(deltaY) || deltaY === 0) return;

    const orbit = this._camGetOrbitBase();
    const factor = Math.pow(1.001, deltaY);
    const radius = Math.max(0.2, Math.min(50, orbit.radius / factor));
    this._camApplyOrbit({ yaw: orbit.yaw, pitch: orbit.pitch, radius });

    this._scheduleAutoOrbitResume(800);
    return false;
  },

  _clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  },
  _camGetBasePivot() {
    const root = this._threeRoot;
    if (!root) return { x: 0, y: 0, z: 0 };
    const targetSize = Number(this.data.tuning.targetSize || 3.0);
    const fitSizeY = (Number(this._fitBaseSizeY || 1) * targetSize);
    const lookAtHeightMul = Number(this.data.tuning.lookAtHeightMul || 0.12);
    return {
      x: Number(root.position.x || 0),
      // 关键点：注视点 y 不跟着 liftMul 被“抵消”
      y: Number(this._fitBasePos?.y || 0) + fitSizeY * lookAtHeightMul,
      z: Number(root.position.z || 0),
    };
  },
  _camGetOrbitBase() {
    const camera = this._threeCamera;
    if (!camera) return { radius: 1, yaw: 0, pitch: 0 };
    const basePivot = this._camGetBasePivot();
    const off = this._camPivotOffset || { x: 0, y: 0, z: 0 };
    const pivot = { x: basePivot.x + off.x, y: basePivot.y + off.y, z: basePivot.z + off.z };
    const relX = camera.position.x - pivot.x;
    const relY = camera.position.y - pivot.y;
    const relZ = camera.position.z - pivot.z;
    const radius = Math.hypot(relX, relY, relZ) || 1;
    const yaw = Math.atan2(relX, relZ);
    const horizontal = Math.hypot(relX, relZ) || 1;
    const pitch = Math.atan2(relY, horizontal);
    return { radius, yaw, pitch, pivot };
  },
  _camApplyOrbit({ yaw, pitch, radius }) {
    const camera = this._threeCamera;
    if (!camera) return;
    const basePivot = this._camGetBasePivot();
    const off = this._camPivotOffset || { x: 0, y: 0, z: 0 };
    const pivot = { x: basePivot.x + off.x, y: basePivot.y + off.y, z: basePivot.z + off.z };

    const cosPitch = Math.cos(pitch);
    const sinPitch = Math.sin(pitch);
    const xz = radius * cosPitch;

    camera.position.set(
      pivot.x + xz * Math.sin(yaw),
      pivot.y + radius * sinPitch,
      pivot.z + xz * Math.cos(yaw)
    );
    if (typeof camera.lookAt === "function") camera.lookAt(pivot.x, pivot.y, pivot.z);
    if (typeof camera.updateProjectionMatrix === "function") camera.updateProjectionMatrix();
  },

  _resolveClipForAction(actionKey, tier) {
    if (!this._threeClips || !this._threeClipOrder) return null;
    const key = String(actionKey || "").trim();
    if (!key) return null;

    // 1) 精确匹配 clip.name
    if (this._threeClips[key]) return this._threeClips[key];

    const keyLower = key.toLowerCase();
    const regexMap = {
      idle: [/idle/i, /stand/i, /wait/i, /rest/i],
      wave: [/wave/i, /招手/i, /wag/i, /tail/i, /hand/i, /waggle/i],
      happy: [/happy/i, /smile/i, /celebr/i, /laugh/i, /spin/i, /circle/i],
      listen: [/listen/i, /hear/i, /ear/i, /关注/i],
    };

    const regs = regexMap[keyLower] || [];
    // 2) 模糊匹配 clip.name（优先匹配剪辑命名）
    if (regs.length) {
      for (const name of this._threeClipOrder) {
        if (!name) continue;
        for (const rg of regs) {
          if (rg.test(name)) return this._threeClips[name];
        }
      }
    }

    // 3) 兜底：用“非 idle 剪辑”的顺序映射到动作 key
    const nonIdle = this._threeClipOrder.filter((n) => n && !/idle|stand/i.test(n));
    const idleName = this._threeIdleClipName || this._threeClipOrder.find((n) => n && /idle|stand/i.test(n)) || "";

    const c0 = nonIdle[0];
    const c1 = nonIdle[1];
    const c2 = nonIdle[2];

    if (keyLower === "idle") return idleName ? this._threeClips[idleName] : null;
    if (keyLower === "wave") return c0 ? this._threeClips[c0] : (idleName ? this._threeClips[idleName] : null);
    if (keyLower === "happy") return c1 ? this._threeClips[c1] : (c0 ? this._threeClips[c0] : (idleName ? this._threeClips[idleName] : null));
    if (keyLower === "listen") return c2 ? this._threeClips[c2] : (c1 ? this._threeClips[c1] : (c0 ? this._threeClips[c0] : (idleName ? this._threeClips[idleName] : null)));

    return c0 ? this._threeClips[c0] : (idleName ? this._threeClips[idleName] : null);
  },

  _playActionClipByKey(actionKey, tier) {
    const key = String(actionKey || "").trim();
    if (!key) return;
    const allowSetMap = {
      1: new Set(), // 初阶无动作
      2: new Set(["idle", "wave"]), // 中阶
      3: new Set(["idle", "wave", "happy", "listen"]), // 高阶
    };
    const allowSet = allowSetMap[tier] || new Set();

    if (!allowSet.has(key)) {
      wx.showToast({ title: "该档未解锁该动作", icon: "none" });
      return;
    }
    if (!this._threeMixer || !this._threeClips || !this._THREE) return;

    // ===== 调试：跟踪动作展示是否真的回到“原始静态姿态” =====
    const seq = (this._actionDebugSeq = (this._actionDebugSeq || 0) + 1);
    const beforePose = ACTION_DEBUG ? this._snapshotPose("before_" + seq) : null;
    if (ACTION_DEBUG) {
      console.log("[pet-detail][action:before]", {
        seq,
        key,
        tier,
        tuning: this.data.tuning,
        rootPos: beforePose ? beforePose.rootPos : null,
        rootScale: beforePose ? beforePose.rootScale : null,
        camPos: beforePose ? beforePose.camPos : null,
        orbit: beforePose ? beforePose.orbit : null,
      });
    }

    // 动作展示期间不做 pet-stage-nudge（否则会出现你看到的“先缩小”视觉跳变）
    // 仅锁定模型摆放/大小，不重置相机（避免你手动对齐后动作期间相机跳走）
    this._applyRootTuningToScene();
    this._captureActionBonePose();
    // 记录动作开始时的包围盒，用于动作播放期间的“尺寸/居中”补偿
    // （回滚：先禁用 action box compensation，避免在某些 skinned mesh 上出现“消失/闪空”）
    this.setData({ actionHighlight: key });
    setTimeout(() => this.setData({ actionHighlight: "" }), 500);

    // 动作开始：暂停自动环绕，让展示更“稳定”
    this._autoOrbitEnabled = false;
    this._lockTuningDuringAction = true;
    if (this._actionRestoreTimer) {
      try { clearTimeout(this._actionRestoreTimer); } catch (e) {}
      this._actionRestoreTimer = null;
    }

    const clip = this._resolveClipForAction(key, tier);
    if (!clip) {
      wx.showToast({ title: "动作资源未匹配", icon: "none" });
      return;
    }

    const action = this._threeMixer.clipAction(clip);
    action.enabled = true;
    // 略慢播放 => 单次动作展示时间更长
    try {
      if (typeof action.timeScale === "number") action.timeScale = 0.85;
    } catch (e) {}
    // 关键：用淡入让首帧变化从权重 0 平滑过渡，保持静态位置/大小
    try {
      if (typeof action.setEffectiveWeight === "function") action.setEffectiveWeight(ACTION_PLAY_WEIGHT);
    } catch (e) {}
    action.setLoop(this._THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    action.reset().play();
    // 动作结束后恢复到原始姿态：优先用 mixer finished 事件（更准）
    const mixer = this._threeMixer;
    let restored = false;
    const restoreOnce = (reason) => {
      if (restored) return;
      restored = true;
      if (this._actionRestoreTimer) {
        try { clearTimeout(this._actionRestoreTimer); } catch (e) {}
        this._actionRestoreTimer = null;
      }
      this._lockTuningDuringAction = false;
      this._actionBaseBox = null;
      try { if (mixer && typeof mixer.removeEventListener === "function") mixer.removeEventListener("finished", onFinished); } catch (e) {}
      if (ACTION_DEBUG) {
        const midPose = this._snapshotPose("restore_" + seq + "_" + String(reason || "unknown"));
        console.log("[pet-detail][action:restore]", {
          seq,
          reason,
          rootPos: midPose ? midPose.rootPos : null,
          rootScale: midPose ? midPose.rootScale : null,
          camPos: midPose ? midPose.camPos : null,
          orbit: midPose ? midPose.orbit : null,
        });
      }
      this._restoreToIdlePose();
      // 恢复“原始姿态”后，再刷一遍 tuning（仅模型摆放/大小），避免漂移
      this._applyRootTuningToScene();
      if (ACTION_DEBUG) {
        const afterPose = this._snapshotPose("after_" + seq);
        const bp = beforePose || {};
        const brp = (bp && bp.rootPos) ? bp.rootPos : {};
        const arp = (afterPose && afterPose.rootPos) ? afterPose.rootPos : {};
        const brs = (bp && bp.rootScale) ? bp.rootScale : {};
        const ars = (afterPose && afterPose.rootScale) ? afterPose.rootScale : {};
        const bcp = (bp && bp.camPos) ? bp.camPos : {};
        const acp = (afterPose && afterPose.camPos) ? afterPose.camPos : {};
        const diff = {
          dRootX: Number(arp.x || 0) - Number(brp.x || 0),
          dRootY: Number(arp.y || 0) - Number(brp.y || 0),
          dRootZ: Number(arp.z || 0) - Number(brp.z || 0),
          dScaleX: Number(ars.x || 0) - Number(brs.x || 0),
          dScaleY: Number(ars.y || 0) - Number(brs.y || 0),
          dScaleZ: Number(ars.z || 0) - Number(brs.z || 0),
          dCamX: Number(acp.x || 0) - Number(bcp.x || 0),
          dCamY: Number(acp.y || 0) - Number(bcp.y || 0),
          dCamZ: Number(acp.z || 0) - Number(bcp.z || 0),
        };
        console.log("[pet-detail][action:after]", {
          seq,
          rootPos: afterPose ? afterPose.rootPos : null,
          rootScale: afterPose ? afterPose.rootScale : null,
          camPos: afterPose ? afterPose.camPos : null,
          orbit: afterPose ? afterPose.orbit : null,
          diff,
        });

        // 额外输出数值，避免 DevTools 折叠导致看不到 diff
        console.log(
          "[pet-detail][action:diff-num]",
          "seq=" + seq,
          "dRoot=(" + diff.dRootX.toFixed(4) + "," + diff.dRootY.toFixed(4) + "," + diff.dRootZ.toFixed(4) + ")",
          "dScale=(" + diff.dScaleX.toFixed(4) + "," + diff.dScaleY.toFixed(4) + "," + diff.dScaleZ.toFixed(4) + ")",
          "dCam=(" + diff.dCamX.toFixed(4) + "," + diff.dCamY.toFixed(4) + "," + diff.dCamZ.toFixed(4) + ")"
        );
      }
      this._scheduleAutoOrbitResume(700);
    };

    const onFinished = (ev) => {
      // three 的 finished 事件里通常有 ev.action
      if (ev && ev.action === action) restoreOnce("finished_event");
    };

    try {
      if (mixer && typeof mixer.addEventListener === "function") {
        mixer.addEventListener("finished", onFinished);
      }
    } catch (e) {}

    // 兜底：用定时器（如果 finished 事件在某些端不触发）
    const clipDurationSec = Number(clip.duration || 1) || 1;
    const timeScaleAbs = 0.85;
    const restoreMs = Math.max(650, (clipDurationSec * 1000 * 1.35) / timeScaleAbs);
    this._actionRestoreTimer = setTimeout(() => restoreOnce("timer_fallback"), restoreMs);
  },

  _restoreToIdlePose() {
    if (!this._threeMixer || !this._THREE) return;
    // 关键：用 stopAllAction + update(0) 回到 glTF 的 bind pose（也就是你调参时看到的“原始位置/大小”）。
    // 不要再播放某个 clip 首帧，否则很可能首帧 pose 与 bind pose 不一致，导致你看到“无法恢复到原样/对不齐”。
    try { this._threeMixer.stopAllAction(); } catch (e) {}
    try { this._threeMixer.update(0); } catch (e) {}

    // 强制还原动作前的骨骼姿态（只对 skinned mesh 生效）
    this._restoreActionBonePose();
  },

  onActionTap(e) {
    const key = String(e.currentTarget.dataset.key || "");
    if (!key) return;
    if (this._guardModelBusy("模型正在加载中…")) return;

    const tier = Number(this.data.displayFormTier) || 1;
    this._playActionClipByKey(key, tier);
  },

  onActionShowcaseTap() {
    const tier = Number(this.data.displayFormTier) || 1;
    if (tier < 2) return;
    if (this.data.viewMode !== "3d") return;
    if (this._guardModelBusy("模型正在加载中…")) return;

    const availableKeys = (this.data.actions || []).map((a) => String(a && a.key || ""));
    const candidates = tier === 2 ? ["wave"] : ["wave", "happy", "listen", "idle"];
    const key = candidates.find((k) => availableKeys.includes(k)) || candidates[0];

    this._playActionClipByKey(key, tier);
  },

  // 展示框右上角：快速触发一个“可用动作”
  onQuickActionTap() {
    const tier = Number(this.data.displayFormTier) || 1;
    if (tier < 2) return;
    if (this.data.viewMode !== "3d") return;
    if (this._guardModelBusy("动作加载中…")) return;

    const availableKeys = (this.data.actions || []).map((a) => String(a && a.key || ""));
    const candidates = tier === 2 ? ["wave"] : ["wave", "happy", "listen", "idle"];
    const key = candidates.find((k) => availableKeys.includes(k)) || availableKeys.find((k) => !!k) || candidates[0] || "idle";

    this._playActionClipByKey(key, tier);
  },

  setAsCompanion() {
    const id = this.data.mascotId;
    if (!id) return;
    const eggActive = !!this.data.eggModelActive;
    const tier = Math.max(1, Math.min(3, Number(this.data.displayFormTier || 1) || 1));
    const formKey = eggActive ? "egg" : `tier${tier}`;
    try {
      wx.setStorageSync("selectedMascot", id);
      // 关键：同时保存“形态信息”，让首页能展示指定形态的模型
      wx.setStorageSync("selectedMascotFormKey", formKey);
      // 变更时间戳：让首页监听即使“值相同”也能触发一次刷新
      wx.setStorageSync("selectedMascotUpdatedAt", Date.now());
    } catch (e) {
      wx.showToast({ title: "保存失败", icon: "none" });
      return;
    }
    wx.showToast({ title: `已选 ${this.data.petName} 陪读`, icon: "success" });
  },
});
