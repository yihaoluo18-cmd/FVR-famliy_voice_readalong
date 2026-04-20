const app = getApp();
const {
  getUserId,
  isGuestCompanionUserId,
  requestEggState,
  reportEggProgress,
  yearMonthKey,
  requestCompanionState,
  postCompanionSetDisplayForm,
  postCompanionSetViewTuning,
} = require("../../utils/pet-growth.js");
const {
  getPetById,
  getPetCoverUrl,
  getPetFormPosterUrls,
  getFormTierModelUrl,
  getFormTierPosterUrl,
  getStaticEggModelUrl,
  getEggModelUrl,
} = require("../../utils/pets-catalog.js");
const { toMiniprogramAssetUrl, getMiniprogramStaticBase } = require("../../utils/asset-url.js");
const { isMainDone, markMainDone } = require("../../utils/guide-flow.js");

const DEFAULT_BASE_URL = "http://127.0.0.1:9880";

function buildMascotPhotoList(mascotId) {
  return getPetFormPosterUrls(mascotId).map((u) => toMiniprogramAssetUrl(u));
}

function mascotWithResolvedUrl(m) {
  if (!m) return m;
  return { ...m, url: toMiniprogramAssetUrl(m.url) };
}
let createScopedThreejs = null;
let registerGLTFLoader = null;
let THREE_IMPORT_ERROR = "";

try {
  ({ createScopedThreejs } = require("../companion/threejs-miniprogram.js"));
  ({ registerGLTFLoader } = require("../companion/gltf-loader.js"));
} catch (e) {
  THREE_IMPORT_ERROR = String(e || "");
}

function getApiBaseUrl() {
  return app && app.getApiBaseUrl ? app.getApiBaseUrl() : DEFAULT_BASE_URL;
}

function getWindowMetrics() {
  let windowWidth = 375;
  let pixelRatio = 1;
  try {
    const w = (typeof wx.getWindowInfo === "function") ? (wx.getWindowInfo() || {}) : {};
    const d = (typeof wx.getDeviceInfo === "function") ? (wx.getDeviceInfo() || {}) : {};
    windowWidth = Number(w.windowWidth || d.windowWidth || 375) || 375;
    pixelRatio = Number(d.pixelRatio || w.pixelRatio || 1) || 1;
  } catch (e) {}
  return { windowWidth, pixelRatio };
}

function resolveModelUrl(rel) {
  const s = String(rel || "").trim();
  if (!s) return "";
  if (s.startsWith("http")) return s;
  return `${getApiBaseUrl()}${s.startsWith("/") ? "" : "/"}${s}`;
}

function clamp(v, min, max) {
  const n = Number(v);
  if (!Number.isFinite(n)) return min;
  return Math.max(min, Math.min(max, n));
}

// 与 pet-detail/companion 调参面板保持一致的“后端 tuning schema”
// home 这里的 UI 值做映射：位置 Y 约 (-10000~200)、缩放 20~300% 等，与伴读页后端 liftMul 范围对齐。
const HOME_TUNING_BASE_TARGET_SIZE = 3.0; // slider 默认 100% 对应的 targetSize
const HOME_TUNING_BASE_LIFT_MUL = 0.1; // slider 默认 homeTunePosY=0 对应的 liftMul
const HOME_TUNING_LIFT_MUL_MIN = -100.0; // 首页允许更大幅度下移（homeTunePosY=-10000 -> delta=-100）
const HOME_TUNING_LIFT_MUL_MAX = 2.0; // 首页卡片展示可接受的垂直偏移上限
const HOME_TUNING_LAST_SAVED_KEY = "home_tuning_last_saved";
const HOME_TUNING_DEFAULTS = {
  fov: 45,
  camDistMul: 1.2,
  camHeightMul: 0.18,
  lookAtHeightMul: 0.12,
};

// 伴宠三形态展示名（同一只伴宠，不同“阶段昵称”）
function getMascotFormDisplayName(mascotId, baseName, formKey) {
  const id = String(mascotId || "").trim();
  const fk = String(formKey || "").trim() || "tier1";
  const base = baseName || "";
  const MAP = {
    "cute-dog": {
      egg: "小狗·软萌蛋壳期",
      tier1: "小狗·暖萌新手",
      tier2: "小狗·元气小队长",
      tier3: "小狗·银河守护者",
    },
    "cute-fox": {
      egg: "小狐·晨雾幼崽",
      tier1: "小狐·森林萌新",
      tier2: "小狐·月光信使",
      tier3: "小狐·星影旅者",
    },
    "cute-dino": {
      egg: "小羊·棉花蛋壳期",
      tier1: "小羊·软萌新手",
      tier2: "小羊·勇气小队员",
      tier3: "小羊·星光守护者",
    },
    "cute-cat": {
      egg: "小猫·盒子打呼噜",
      tier1: "小猫·窗边做梦家",
      tier2: "小猫·夜色巡逻员",
      tier3: "小猫·星轨领航员",
    },
    "cute-bunny": {
      egg: "小兔·毛绒团子",
      tier1: "小兔·胡萝卜收藏家",
      tier2: "小兔·云端跳跳队员",
      tier3: "小兔·黎明引路人",
    },
    "cute-squirrel": {
      egg: "松鼠·树洞打盹中",
      tier1: "松鼠·橡果搬运工",
      tier2: "松鼠·树梢滑翔手",
      tier3: "松鼠·风之记事官",
    },
    "cute-chick": {
      egg: "小黄鸡·壳里数星星",
      tier1: "小黄鸡·晨光报时员",
      tier2: "小黄鸡·村口小号手",
      tier3: "小黄鸡·云端指挥家",
    },
    "cute-panda": {
      egg: "熊猫·竹林滚滚球",
      tier1: "熊猫·竹林午睡王",
      tier2: "熊猫·凉亭美食家",
      tier3: "熊猫·山谷守梦人",
    },
    "cute-koala": {
      egg: "仓鼠·口袋蛋壳期",
      tier1: "仓鼠·坚果收藏家",
      tier2: "仓鼠·句子小管家",
      tier3: "仓鼠·星星储蓄官",
    },
    "cute-penguin": {
      egg: "企鹅·雪球乘客",
      tier1: "企鹅·雪地溜冰手",
      tier2: "企鹅·浪尖冲浪员",
      tier3: "企鹅·极光远行者",
    },
  };
  const perMascot = MAP[id] || null;
  if (perMascot && perMascot[fk]) return perMascot[fk];
  // 兜底：用基础名 + 简洁阶段后缀
  const short = fk === "egg" ? "蛋壳期" : fk === "tier2" ? "进阶期" : fk === "tier3" ? "高阶期" : "初阶期";
  return base ? `${base}·${short}` : short;
}

function _readHomeTuningLastSaved() {
  try {
    const raw = wx.getStorageSync(HOME_TUNING_LAST_SAVED_KEY);
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
    return raw;
  } catch (e) {
    return {};
  }
}

function _writeHomeTuningLastSaved(mascotId, formKey) {
  try {
    const map = _readHomeTuningLastSaved();
    const mid = String(mascotId || "").trim();
    const fk = String(formKey || "").trim();
    if (!mid || !fk) return;
    if (!map[mid] || typeof map[mid] !== "object" || Array.isArray(map[mid])) map[mid] = {};
    map[mid][fk] = Date.now();
    wx.setStorageSync(HOME_TUNING_LAST_SAVED_KEY, map);
  } catch (e) {}
}

function _shouldApplyStoredPositionFromLocalFlag(mascotId, formKey) {
  try {
    const map = _readHomeTuningLastSaved();
    const mid = String(mascotId || "").trim();
    const fk = String(formKey || "").trim();
    return !!(map[mid] && map[mid][fk]);
  } catch (e) {
    return false;
  }
}

// 与后端 pet_egg 槽位一致的 10 个小伙伴（暂未单独插图的用小图标占位图）
const MASCOT_AVATARS_ALL = [
  { id: "cute-dog", name: "柴小汪", url: getPetCoverUrl("cute-dog"), emoji: "🐶" },
  { id: "cute-fox", name: "小狐狸", url: getPetCoverUrl("cute-fox"), emoji: "🦊" },
  { id: "cute-dino", name: "小绵羊", url: getPetCoverUrl("cute-dino"), emoji: "🐑" },
  { id: "cute-cat", name: "猫小咪", url: getPetCoverUrl("cute-cat"), emoji: "🐱" },
  { id: "cute-bunny", name: "兔小白", url: getPetCoverUrl("cute-bunny"), emoji: "🐰" },
  { id: "cute-squirrel", name: "小松鼠", url: getPetCoverUrl("cute-squirrel"), emoji: "🐿️" },
  { id: "cute-chick", name: "鸭嘎嘎", url: getPetCoverUrl("cute-chick"), emoji: "🐥" },
  { id: "cute-panda", name: "熊墩墩", url: getPetCoverUrl("cute-panda"), emoji: "🐼" },
  { id: "cute-koala", name: "小仓鼠", url: getPetCoverUrl("cute-koala"), emoji: "🐹" },
  { id: "cute-penguin", name: "企鹅", url: getPetCoverUrl("cute-penguin"), emoji: "🐧" },
];
function mapAvatarsWithLock(unlockedList) {
  const unlocked = new Set(unlockedList && unlockedList.length ? unlockedList : ["cute-dog"]);
  return MASCOT_AVATARS_ALL.map((m) => ({
    ...m,
    url: toMiniprogramAssetUrl(m.url),
    locked: !unlocked.has(m.id),
  }));
}

function shouldUnlockAmusementGamesByEggState(data) {
  const d = data && typeof data === "object" ? data : {};
  const unlocked = Array.isArray(d.unlocked_mascot_ids) ? d.unlocked_mascot_ids : [];
  if (unlocked.length > 0) return true;
  if (d.has_ready_to_claim) return true;
  const slots = Array.isArray(d.slots) ? d.slots : [];
  return slots.some((s) => {
    const st = String((s && s.ui_state) || "").trim();
    return st === "ready" || st === "incubating" || st === "claimed";
  });
}

/** 首页 3D 展示框内背景：按伴宠主色做柔和渐变，与模型气质呼应 */
function homePetStageBackgroundCss(mascotId) {
  const id = String(mascotId || "").trim() || "cute-dog";
  const MAP = {
    "cute-dog":
      "linear-gradient(165deg, #fff8f0 0%, #ffe8d6 38%, #ffd4a8 100%)",
    "cute-fox":
      "linear-gradient(165deg, #fff5f0 0%, #ffe4dc 40%, #ffd0c0 100%)",
    "cute-dino":
      "linear-gradient(165deg, #f0fdf6 0%, #dcfce7 42%, #bbf7d0 100%)",
    "cute-cat":
      "linear-gradient(165deg, #faf5ff 0%, #f3e8ff 45%, #e9d5ff 100%)",
    "cute-bunny":
      "linear-gradient(165deg, #fff5f7 0%, #fce7f3 48%, #fbcfe8 100%)",
    "cute-squirrel":
      "linear-gradient(165deg, #fffbeb 0%, #fde68a 35%, #fcd34d 100%)",
    "cute-chick":
      "linear-gradient(165deg, #fffbeb 0%, #fef9c3 45%, #fde047 100%)",
    "cute-panda":
      "linear-gradient(165deg, #f9fafb 0%, #f3f4f6 48%, #e5e7eb 100%)",
    "cute-koala":
      "linear-gradient(165deg, #f0fdf4 0%, #ecfccb 40%, #d9f99d 100%)",
    "cute-penguin":
      "linear-gradient(165deg, #f0f9ff 0%, #e0f2fe 42%, #bae6fd 100%)",
  };
  return MAP[id] || MAP["cute-dog"];
}

Page({
  data: {
    dogPhotoList: [],
    foxPhotoList: [],
    // 其他动物默认用小狗的3D图（后续可扩展）
    currentPhotoList: [],
    currentIndex: 0,
    currentImage: "",
    startX: 0,
    isMoving: false,
    homeModelUrl: "",
    homeDisplayFormTier: 1,
    homeEggModelActive: false,
    homeThreeLoading: false,
    homeThreeFailed: false,
    // 加载遮罩（照搬 pet-detail 的“魔法加载”观感）
    homeModelLoadProgress: 0,
    homeModelLoadStageText: "魔法准备中…",
    homeModelMagicCount: 0,
    hungerLevel: 0,
    cleanLevel: 0,
    moodLevel: 0,
    sleepyLevel: 0,
    readingMinutesToday: 0,
    readingGoalMinutes: 40,
    readingProgress: 0,
    starsToday: 0,
    starsGoalToday: 20,
    starsProgress: 0,
    homeQuickGames: [],
    showHomeTuning: false,
    homeTunePosX: 0,
    homeTunePosY: 0,
    // input[type=text] 的“文本草稿”，避免输入过程中 Number/浮点格式导致无法继续输入小数
    homeTunePosYText: "0",
    homeTunePosZ: 0,
    homeTuneScalePct: 100,
    homeTuneRotY: 0,

    userData: {},
    sessionLoggedIn: false,
    stars: 0,
    level: 1,
    levelTitle: '初级读者',
    levelIcon: '📖',
    
    // 吉祥物相关（未解锁项 locked，仅宠物蛋领取后可用）
    mascotAvatars: mapAvatarsWithLock(["cute-dog"]),
    currentMascot: mascotWithResolvedUrl(MASCOT_AVATARS_ALL[0]),
    homePetStageBg: homePetStageBackgroundCss("cute-dog"),
    mpAssetIconBase: getMiniprogramStaticBase(),
    homeMascotFormTitle: "小狗·暖萌新手",
    showAvatarPicker: false,
    showHomeSwitchModal: false,
    homeSwitchStep: "menu", // menu | mascot | form
    homeUnlockedFormTiers: [1],
    homeFormPosterUrls: [],
    floatingClass: 'floatingClass',
    bubbleClass: 'bubbleClass',
    petEntryBadge: false,
    
    // 当前书籍（项目已移除内置测试绘本：从最近阅读或书架进入）
    currentBook: null,
    
    // 菜单项
    menuItems: [
      {
        id: "books",
        title: "看绘本",
        color: "bg-blue-100",
        route: "/books",
        emoji: "📚",
      },
      {
        id: "voice",
        title: "克隆魔法音",
        color: "bg-purple-100",
        route: "/voice",
        subtitle: "核心功能",
        emoji: "🎤",
      },
      {
        id: "play",
        title: "玩游戏",
        color: "bg-pink-100",
        route: "/play",
        emoji: "🎮",
      },
    ],
    showGuide: false,
    guideSteps: [],
    guideStepIndex: 0,
    guideHighlight: "",
    guideTitle: "",
    guideDesc: "",
  },

  onLoad() {
    const dogPhotoList = buildMascotPhotoList("cute-dog");
    const foxPhotoList = buildMascotPhotoList("cute-fox");
    this.setData({
      dogPhotoList,
      foxPhotoList,
      currentPhotoList: dogPhotoList,
      currentImage: dogPhotoList[0] || "",
      homeFormPosterUrls: buildMascotPhotoList("cute-dog"),
      mpAssetIconBase: getMiniprogramStaticBase(),
    });
    this.loadData();
    this.syncEggState();
    this._autoYaw = 0;
    this._dragYaw = 0;
    this._dragging = false;
    this._dragStartX = 0;
    this._dragYawAtStart = 0;
    this._lastDragTs = 0;
    this._homeThreeToken = 0;
    this._homeThreeInFlight = false;
    this._homeRoot = null;
    this._homeRenderer = null;
    this._homeScene = null;
    this._homeCamera = null;
    this._homeCanvas = null;
    this._homeRaf = null;
    this._homeServerFormViewTuning = {};
    this._homeBasePos = null;
    this._homeBaseScale = 1;
    this._homeBaseRotY = 0;
    this._homeModelProgressFakeTimer = null;
    this._homeModelProgressFakeToken = null;
    this._homeModelProgressFakeValue = 0;
    this._homeSelectionWatchTimer = null;
    this._homeSelectionSig = "";
    this._homeSelectionPendingSig = "";
    this._homeStyleRetryTimer = null;
    this._homeTransientStyleRetry = 0;
    this._loadAndBuildHomeThree();
    this._refreshHomeQuickGames();
    this._refreshTodayMetrics();
  },

  _stopHomeModelProgressFake() {
    if (this._homeModelProgressFakeTimer) {
      clearInterval(this._homeModelProgressFakeTimer);
      this._homeModelProgressFakeTimer = null;
    }
    this._homeModelProgressFakeToken = null;
    this._homeModelProgressFakeValue = 0;
  },

  _startHomeModelProgressFake(token) {
    this._homeModelProgressFakeToken = token;
    this._homeModelProgressFakeValue = 6;
    this.setData({ homeModelLoadProgress: 6, homeModelLoadStageText: "魔法准备中…", homeModelMagicCount: 0 });

    if (this._homeModelProgressFakeTimer) clearInterval(this._homeModelProgressFakeTimer);
    this._homeModelProgressFakeTimer = setInterval(() => {
      if (this._homeModelProgressFakeToken !== token) return;
      const cur = Number(this.data.homeModelLoadProgress || 0);
      const base = Math.max(this._homeModelProgressFakeValue || 0, cur);
      const step = 0.9 + Math.random() * 1.4;
      const next = Math.min(98, base + step);
      this._homeModelProgressFakeValue = next;
      this.setData({
        homeModelLoadProgress: Math.floor(next * 10) / 10,
        homeModelLoadStageText: next > 55 ? "魔法正在孵化…" : "魔法正在解封…",
      });
      if (next >= 98) this._stopHomeModelProgressFake();
    }, 120);
  },

  onHomeModelMagicTap() {
    if (!this.data.homeThreeLoading && !this.data.homeThreeFailed) return;
    const nextCount = Number(this.data.homeModelMagicCount || 0) + 1;
    const curP = Number(this.data.homeModelLoadProgress || 0);
    const bump = 3 + Math.min(10, nextCount * 1.1);
    const nextP = Math.min(98, Math.max(curP, curP + bump));
    this.setData({
      homeModelMagicCount: nextCount,
      homeModelLoadProgress: Math.floor(nextP * 10) / 10,
      homeModelLoadStageText: nextCount % 3 === 0 ? "小魔法命中！" : "点点加速中…",
    });
    // 失败时允许点遮罩直接重试
    if (this.data.homeThreeFailed) {
      this._loadAndBuildHomeThree();
    }
  },

  // 3D触摸开始
  onTouchStart(e) {
    this.setData({
      startX: e.touches[0].clientX,
      isMoving: false
    });
  },

  // 3D触摸移动（切换角度）
  onTouchMove(e) {
    const { startX, currentPhotoList, currentIndex } = this.data;
    const moveX = e.touches[0].clientX;
    const diffX = moveX - startX;

    // 滑动距离太小不触发
    if (Math.abs(diffX) < 10) return;
    // 防止快速滑动重复触发
    if (this.data.isMoving) return;

    this.setData({ isMoving: true });

    let newIndex = currentIndex;
    // 左滑：下一张
    if (diffX < 0) {
      newIndex = (currentIndex + 1) % currentPhotoList.length;
    } else {
      // 右滑：上一张
      newIndex = (currentIndex - 1 + currentPhotoList.length) % currentPhotoList.length;
    }

    this.setData({
      currentIndex: newIndex,
      currentImage: currentPhotoList[newIndex],
      startX: moveX
    }, () => {
      setTimeout(() => {
        this.setData({ isMoving: false });
      }, 50);
    });
  },

  // 选择吉祥物（核心：只保留这一个！）
  selectMascot(e) {
    const mascot = e.currentTarget.dataset.mascot;
    if (mascot && mascot.locked) {
      wx.showToast({ title: "先去宠物蛋乐园解锁哦", icon: "none" });
      wx.navigateTo({ url: "/pages/pet-system/pet-system" });
      return;
    }
    const newPhotoList = buildMascotPhotoList(mascot.id);

    this.setData({
      currentMascot: mascot,
      homePetStageBg: homePetStageBackgroundCss(mascot.id),
      showAvatarPicker: false,
      currentIndex: 0, // 重置到第一张图
      currentPhotoList: newPhotoList,
      currentImage: newPhotoList[0] || "", // 显示对应动物的第一张形态图
      homeFormPosterUrls: newPhotoList
    }, () => this._loadAndBuildHomeThree());
    
    // 保存选择（全局）：伴宠 + 更新时间戳，确保首页能立即刷新
    // 切换伴宠时沿用当前选中的形态（默认 tier1）
    let fk = "tier1";
    try {
      fk = String(wx.getStorageSync("selectedMascotFormKey") || "").trim() || "tier1";
    } catch (e) {}
    this._persistHomeSelection(mascot.id, fk);
  },

  onShow() {
    this.loadData();
    this.syncEggState();
    this._loadAndBuildHomeThree();
    this._startHomeSelectionWatcher();
    this._refreshHomeQuickGames();
    this._refreshTodayMetrics();
    this.initHomeGuide();
  },

  onHide() {
    this._stopHomeSelectionWatcher();
    this._destroyHomeThree();
  },

  onUnload() {
    this._stopHomeSelectionWatcher();
    if (this._homeStyleRetryTimer) {
      try { clearTimeout(this._homeStyleRetryTimer); } catch (e) {}
      this._homeStyleRetryTimer = null;
    }
    this._destroyHomeThree();
  },

  _getHomeSelectionSig() {
    try {
      const mid = String(wx.getStorageSync("selectedMascot") || "").trim() || "cute-dog";
      const fk = String(wx.getStorageSync("selectedMascotFormKey") || "").trim() || "";
      const ts = String(wx.getStorageSync("selectedMascotUpdatedAt") || "").trim() || "";
      return `${mid}::${fk}::${ts}`;
    } catch (e) {
      return "";
    }
  },

  _startHomeSelectionWatcher() {
    if (this._homeSelectionWatchTimer) return;
    this._homeSelectionSig = this._getHomeSelectionSig();
    // 轮询监听：避免部分端返回 tabbar 时 onShow 不稳定，确保模型区域能自动刷新到最新选择
    this._homeSelectionWatchTimer = setInterval(() => {
      const sig = this._getHomeSelectionSig();
      if (!sig || sig === this._homeSelectionSig) return;
      this._homeSelectionSig = sig;
      // 若当前正在加载 3D，先记录“待刷新”，等加载结束再触发
      if (this.data.homeThreeLoading) {
        this._homeSelectionPendingSig = sig;
        return;
      }
      this._loadAndBuildHomeThree();
    }, 800);
  },

  _stopHomeSelectionWatcher() {
    if (this._homeSelectionWatchTimer) {
      clearInterval(this._homeSelectionWatchTimer);
      this._homeSelectionWatchTimer = null;
    }
    this._homeSelectionPendingSig = "";
  },

  syncEggState() {
    const total = app.globalData.totalCheckInsThisMonth || 0;
    reportEggProgress("checkin_month_sync", {
      total_check_ins_this_month: total,
      year_month: yearMonthKey(),
    }).catch(() => {});
    requestEggState()
      .then((data) => {
        const list = mapAvatarsWithLock(data.unlocked_mascot_ids);
        this.setData({
          mascotAvatars: list,
          petEntryBadge: !!data.has_ready_to_claim,
        });
        this._clampSelectedMascot(new Set(data.unlocked_mascot_ids || ["cute-dog"]));
      })
      .catch(() => {});
  },

  _clampSelectedMascot(unlockedSet) {
    try {
      let saved = wx.getStorageSync("selectedMascot");
      if (!saved || !unlockedSet.has(saved)) {
        saved = "cute-dog";
        wx.setStorageSync("selectedMascot", saved);
      }
      const mascot = MASCOT_AVATARS_ALL.find((m) => m.id === saved);
      if (!mascot) return;
      const newPhotoList = buildMascotPhotoList(mascot.id);
      this.setData({
        currentMascot: mascotWithResolvedUrl(mascot),
        homePetStageBg: homePetStageBackgroundCss(mascot.id),
        currentPhotoList: newPhotoList,
        currentIndex: 0,
        currentImage: newPhotoList[0] || "",
        homeFormPosterUrls: newPhotoList,
      }, () => this._loadAndBuildHomeThree());
    } catch (e) {}
  },

  _refreshHomeQuickGames() {
    // 与游乐园 pages/play/play.js 的前四项一致；
    // 规则：游客全开；正式账号在“宠物蛋已有进度（可领/孵化中/已拥有）”后开放其余入口
    const guest = isGuestCompanionUserId(getUserId());
    const all = [
      { id: "speaker", title: "演说家", iconEmoji: "🎤", route: "/pages/speaker/speaker" },
      { id: "color", title: "涂色", iconEmoji: "🖍️", route: "/pages/color/color" },
      { id: "companion", title: "小柴伙伴", iconEmoji: "🐶", route: "/pages/companion/companion" },
      { id: "petEggGarden", title: "宠物蛋", iconEmoji: "🥚", route: "/pages/pet-system/pet-system" },
    ];
    const applyGames = (unlockedOthers) => {
      const homeQuickGames = all.map((g) => ({
        ...g,
        locked: !guest && !unlockedOthers && g.id !== "petEggGarden",
      }));
      this.setData({ homeQuickGames });
    };

    if (guest) {
      applyGames(true);
      return;
    }

    requestEggState()
      .then((data) => {
        applyGames(shouldUnlockAmusementGamesByEggState(data));
      })
      .catch(() => {
        // 网络失败时保守回退：仅宠物蛋可用，避免误解锁
        applyGames(false);
      });
  },

  _dateKey() {
    const d = new Date();
    const m = d.getMonth() + 1;
    const day = d.getDate();
    const mm = m < 10 ? `0${m}` : `${m}`;
    const dd = day < 10 ? `0${day}` : `${day}`;
    return `${d.getFullYear()}-${mm}-${dd}`;
  },

  _refreshTodayMetrics() {
    const key = this._dateKey();
    let minutes = 0;
    let goalMin = 40;
    let starsToday = 0;
    let starsGoal = 20;
    try {
      minutes = Number(wx.getStorageSync(`readingMinutes.${key}`) || 0) || 0;
      goalMin = Math.max(5, Math.min(180, Number(wx.getStorageSync("dailyReadingGoalMinutes") || 40) || 40));
      starsToday = Number(wx.getStorageSync(`todayStars.${key}`) || 0) || 0;
      starsGoal = Math.max(1, Math.min(999, Number(wx.getStorageSync("todayStarsGoal") || 20) || 20));
    } catch (e) {}
    const readingProgress = Math.max(0, Math.min(100, Math.round((minutes / Math.max(1, goalMin)) * 100)));
    const starsProgress = Math.max(0, Math.min(100, Math.round((starsToday / Math.max(1, starsGoal)) * 100)));
    this.setData({
      readingMinutesToday: minutes,
      readingGoalMinutes: goalMin,
      readingProgress,
      starsToday,
      starsGoalToday: starsGoal,
      starsProgress,
    });
  },

  onQuickGameTap(e) {
    const game = e && e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.game;
    const route = game && game.route ? String(game.route) : "";
    if (!route) return;
    if (game.locked) {
      wx.showToast({ title: "破壳养成后再来玩哦", icon: "none" });
      return;
    }
    wx.navigateTo({ url: route });
  },

  goToVoice() {
    wx.switchTab({ url: "/pages/voice/voice" });
  },

  noop() {},

  onHomeThreeTouchStart(e) {
    const x = Number(e && e.touches && e.touches[0] && e.touches[0].clientX) || 0;
    this._dragging = true;
    this._dragStartX = x;
    this._dragYawAtStart = Number(this._dragYaw || 0);
    this._lastDragTs = Date.now();
  },

  onHomeThreeTouchMove(e) {
    if (!this._dragging) return;
    const x = Number(e && e.touches && e.touches[0] && e.touches[0].clientX) || 0;
    const dx = x - this._dragStartX;
    const next = this._dragYawAtStart + dx * 0.25;
    this._dragYaw = Math.max(-30, Math.min(30, next));
    this._lastDragTs = Date.now();
  },

  onHomeThreeTouchEnd() {
    this._dragging = false;
    this._lastDragTs = Date.now();
  },

  onHomeTunePosYTextInput(e) {
    const raw = (e && e.detail && typeof e.detail.value === "string" ? e.detail.value : "").trim();
    this.setData({ homeTunePosYText: raw });
    // 允许输入过程中出现空/非数字：只在能解析成有限数时才更新模型
    if (!raw) return;
    const v = Number(raw);
    if (!Number.isFinite(v)) return;
    const clamped = Math.max(-10000, Math.min(200, v));
    this.setData(
      { homeTunePosY: clamped, homeTunePosYText: String(clamped) },
      () => this._applyHomeTuningToRoot()
    );
  },

  onHomeMouseWheel(e) {
    // 仅在首页“调参面板”打开时允许滚轮缩放（避免影响正常页面滚动）
    if (!this.data.showHomeTuning) return;
    if (!this._homeRoot) return;

    // 尽可能阻止事件继续触发页面滚动（开发者工具/桌面端更常见）
    try {
      if (e) {
        if (typeof e.preventDefault === "function") e.preventDefault();
        if (typeof e.stopPropagation === "function") e.stopPropagation();
      }
    } catch (err) {}

    const deltaY = (() => {
      // 兼容不同环境下字段名（参考 pet-detail 页的滚轮兼容逻辑）
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

    const cur = Number(this.data.homeTuneScalePct || 100) || 100;
    // 与 pet-detail 类似的指数缩放手感：滚轮向下(deltaY>0) => 缩小；向上 => 放大
    const factor = Math.pow(1.001, deltaY);
    const next = Math.round(cur / factor);
    const clamped = Math.max(20, Math.min(300, next));
    if (clamped === cur) return false;

    this.setData({ homeTuneScalePct: clamped }, () => this._applyHomeTuningToRoot());
    return false;
  },

  async _loadAndBuildHomeThree() {
    let mascotId = (this.data.currentMascot && this.data.currentMascot.id) || "cute-dog";
    let preferredFormKey = "";
    try {
      const savedMascotId = String(wx.getStorageSync("selectedMascot") || "").trim();
      if (savedMascotId) mascotId = savedMascotId;
      preferredFormKey = String(wx.getStorageSync("selectedMascotFormKey") || "").trim();
    } catch (e) {}

    // 同步 currentMascot（头像/名字等）以匹配全局选中的陪读小伙伴；展示框背景随伴宠切换
    try {
      const m = MASCOT_AVATARS_ALL.find((x) => x.id === mascotId);
      const patch = { homePetStageBg: homePetStageBackgroundCss(mascotId) };
      if (m && (!this.data.currentMascot || this.data.currentMascot.id !== mascotId)) {
        patch.currentMascot = mascotWithResolvedUrl(m);
      }
      this.setData(patch);
    } catch (e) {}

    const pet = getPetById(mascotId);
    if (!pet) return;
    const token = ++this._homeThreeToken;
    let transientStyleRetryScheduled = false;
    this._stopHomeModelProgressFake();
    this._startHomeModelProgressFake(token);
    this.setData({ homeThreeLoading: true, homeThreeFailed: false });
    try {
      const state = await requestCompanionState(mascotId);
      if (token !== this._homeThreeToken) return;
      // requestCompanionState 在 pet-growth.js 中返回的是后端 JSON body 本体（没有 data 包层）
      // 这里做兼容：如果未来后端返回 {data:{...}} 再处理
      const d = state && typeof state === "object"
        ? (state.data && typeof state.data === "object" ? state.data : state)
        : {};
      const rawFvt = d && (d.form_view_tuning_home || d.form_view_tuning);
      this._homeServerFormViewTuning =
        rawFvt && typeof rawFvt === "object" && !Array.isArray(rawFvt) ? { ...rawFvt } : {};
      // 首页展示：优先使用 pet-detail “设为陪读小伙伴”时保存的形态信息
      let eggActive = !!d.egg_model_active;
      let displayTier = Math.max(1, Math.min(3, Number(d.display_form_tier || 1) || 1));
      const guestUid = isGuestCompanionUserId(getUserId());
      if (!guestUid && eggActive) {
        preferredFormKey = "egg";
        try {
          wx.setStorageSync("selectedMascotFormKey", "egg");
          if (app && app.globalData) app.globalData.selectedMascotFormKey = "egg";
        } catch (e) {}
      }
      if (preferredFormKey === "egg") {
        if (guestUid || !!d.egg_model_active) eggActive = true;
      } else if (/^tier[123]$/.test(preferredFormKey)) {
        eggActive = false;
        displayTier = Math.max(1, Math.min(3, Number(preferredFormKey.replace("tier", "")) || 1));
      }
      const stats = d.stats && typeof d.stats === "object" ? d.stats : {};
      const unlocked = Array.isArray(d.unlocked_form_tiers) ? d.unlocked_form_tiers : [];
      const clamp01 = (n) => Math.max(0, Math.min(100, Number(n || 0) || 0));
      this.setData({
        hungerLevel: clamp01(stats.food || stats.hunger || stats.hunger_level),
        cleanLevel: clamp01(stats.clean || stats.cleanliness || stats.clean_level),
        moodLevel: clamp01(stats.mood || stats.happy || stats.mood_level),
        sleepyLevel: clamp01(stats.sleepy || stats.sleep || stats.sleepy_level),
        homeUnlockedFormTiers: unlocked && unlocked.length ? unlocked : [1],
      });
      const formKey = eggActive ? "egg" : `tier${displayTier}`;
      const hasServerTuning = (() => {
        try {
          const raw = this._homeServerFormViewTuning || {};
          const slot = raw && typeof raw === "object" ? (raw[formKey] || raw) : {};
          const tuning = slot && slot.tuning && typeof slot.tuning === "object" ? slot.tuning : slot;
          return !!(tuning && typeof tuning === "object" && Object.keys(tuning).length);
        } catch (e) {
          return false;
        }
      })();
      const shouldApplyStored = hasServerTuning || _shouldApplyStoredPositionFromLocalFlag(mascotId, formKey);
      // 避免“加载中 setData 先应用一次默认，再在 root ready 后又应用一次”造成瞬间跳动
      this._loadHomeTuningFromServer({ applyStoredPosition: shouldApplyStored, formKey, skipApply: true });
      let modelRel = getFormTierModelUrl(pet, displayTier);
      if (eggActive) {
        modelRel = getStaticEggModelUrl(pet) || getEggModelUrl(pet) || modelRel;
      }
      const modelUrl = resolveModelUrl(modelRel);
      if (!modelUrl) throw new Error("empty model url");
      this.setData({
        homeModelUrl: modelUrl,
        homeDisplayFormTier: displayTier,
        homeEggModelActive: eggActive,
        homeMascotFormTitle: getMascotFormDisplayName(
          mascotId,
          (this.data.currentMascot && this.data.currentMascot.name) || "",
          formKey
        ),
      });
      await this._buildHomeThreeScene(modelUrl, token);
      // root ready 后再一次性应用调参，保证位姿稳定
      this._applyHomeTuningToRoot();
      if (token === this._homeThreeToken) {
        this._stopHomeModelProgressFake();
        this.setData({ homeModelLoadProgress: 100, homeModelLoadStageText: "魔法完成！" });
      }
    } catch (e) {
      if (token !== this._homeThreeToken) return;
      const msg = String(
        (e && (e.message || e.errMsg || e.stack || e)) ? (e.message || e.errMsg || e.stack || e) : e || ""
      );
      const isTransientStyleError = /Cannot redefine property/i.test(msg) && /style/i.test(msg);
      if (isTransientStyleError) {
        this._homeTransientStyleRetry = Number(this._homeTransientStyleRetry || 0) + 1;
        const retryCount = this._homeTransientStyleRetry;
        const maxTransientRetry = 12;
        const curP = Number(this.data.homeModelLoadProgress || 0);
        const nextP = Math.max(70, curP);

        if (retryCount >= maxTransientRetry) {
          this._homeTransientStyleRetry = 0;
          if (this._homeStyleRetryTimer) {
            try { clearTimeout(this._homeStyleRetryTimer); } catch (e2) {}
            this._homeStyleRetryTimer = null;
          }
          this._stopHomeModelProgressFake();
          this.setData({ homeThreeFailed: true, homeThreeLoading: false });
        } else {
          transientStyleRetryScheduled = true;
          this.setData({
            homeThreeLoading: true,
            homeThreeFailed: false,
            homeModelLoadProgress: nextP,
            homeModelLoadStageText: `滴滴魔法修复中…（${retryCount}）`,
          });
          const delay = Math.min(1600, 320 * retryCount);
          if (this._homeStyleRetryTimer) {
            try { clearTimeout(this._homeStyleRetryTimer); } catch (e3) {}
          }
          this._homeStyleRetryTimer = setTimeout(() => {
            if (token !== this._homeThreeToken) return;
            this._loadAndBuildHomeThree();
          }, delay);
        }
      } else {
        this._homeTransientStyleRetry = 0;
        this._stopHomeModelProgressFake();
        this.setData({ homeThreeFailed: true });
      }
    } finally {
      if (token === this._homeThreeToken && !transientStyleRetryScheduled) this.setData({ homeThreeLoading: false });
      // 若加载期间发生了新的选择变更，加载结束后立即再刷新一次
      try {
        const pending = String(this._homeSelectionPendingSig || "");
        if (pending) {
          const cur = this._getHomeSelectionSig();
          if (cur && cur === pending) {
            this._homeSelectionPendingSig = "";
            this._loadAndBuildHomeThree();
          } else {
            this._homeSelectionPendingSig = "";
          }
        }
      } catch (e2) {}
    }
  },

  async _buildHomeThreeScene(modelUrl, token) {
    // 若正在构建中，记录最新一次请求，避免用户切形态时“卡住不切”
    if (this._homeThreeInFlight) {
      this._homeThreePendingBuild = { modelUrl, token };
      return;
    }
    this._homeThreeInFlight = true;
    try {
      if (!createScopedThreejs || !registerGLTFLoader) {
        throw new Error(`three import failed: ${THREE_IMPORT_ERROR || "unknown"}`);
      }

      const query = wx.createSelectorQuery().in(this);
      const canvasRes = await new Promise((resolve, reject) => {
        query.select("#homePetThreeCanvas").node().exec((res) => {
          const node = res && res[0] && res[0].node;
          if (!node) reject(new Error("home canvas not ready"));
          else resolve(node);
        });
      });
      if (token !== this._homeThreeToken) return;

      const metrics = getWindowMetrics();
      const pixelRatio = metrics.pixelRatio || 1;
      // 与 WXML/WXSS 的展示尺寸保持一致（home-pet-card 330x360rpx）
      const width = Math.max(260, Math.round((330 / 750) * metrics.windowWidth));
      const height = Math.max(280, Math.round((360 / 750) * metrics.windowWidth));
      canvasRes.width = width * pixelRatio;
      canvasRes.height = height * pixelRatio;

      // 关键修复点：threejs-miniprogram 在反复 createScopedThreejs 时可能触发
      // “Cannot redefine property: style”。因此只在第一次创建核心渲染器。
      if (!this._homeTHREE || !this._homeRenderer || !this._homeScene || !this._homeCamera) {
        const THREE = createScopedThreejs(canvasRes);
        registerGLTFLoader(THREE);
        this._homeTHREE = THREE;

        const renderer = new THREE.WebGLRenderer({ canvas: canvasRes, antialias: true, alpha: true });
        renderer.setPixelRatio(pixelRatio);
        renderer.setSize(width, height);
        renderer.setClearColor(0x000000, 0);

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(28, width / height, 0.01, 1000);
        camera.position.set(0, 0.15, 2.8);
        camera.lookAt(0, 0.1, 0);

        const lightA = new THREE.HemisphereLight(0xffffff, 0xd8d4ff, 1.15);
        const lightB = new THREE.DirectionalLight(0xffffff, 0.95);
        lightB.position.set(1.4, 2.2, 1.8);
        scene.add(lightA);
        scene.add(lightB);

        this._homeRenderer = renderer;
        this._homeScene = scene;
        this._homeCamera = camera;
        this._homeCanvas = canvasRes;

        const startTs = Date.now();
        const loop = () => {
          if (!this._homeRoot || !this._homeRenderer || !this._homeScene || !this._homeCamera) {
            this._homeRaf = canvasRes.requestAnimationFrame(loop);
            return;
          }
          const t = (Date.now() - startTs) / 1000;
          this._autoYaw = Math.sin(t * 0.55) * 30;
          if (!this._dragging && Date.now() - this._lastDragTs > 200) {
            this._dragYaw *= 0.93;
            if (Math.abs(this._dragYaw) < 0.15) this._dragYaw = 0;
          }
          const yawDeg = Math.max(-30, Math.min(30, this._autoYaw + this._dragYaw));
          this._homeRoot.rotation.y = this._homeBaseRotY + (yawDeg * Math.PI) / 180;
          this._homeRenderer.render(this._homeScene, this._homeCamera);
          this._homeRaf = canvasRes.requestAnimationFrame(loop);
        };
        this._homeRaf = canvasRes.requestAnimationFrame(loop);
      } else {
        // 更新尺寸（避免旋转/缩放时画面比例不一致）
        try {
          this._homeRenderer.setPixelRatio(pixelRatio);
          this._homeRenderer.setSize(width, height);
          this._homeCanvas = canvasRes;
          this._homeCamera.aspect = width / height;
          this._homeCamera.updateProjectionMatrix();
        } catch (e) {}
      }

      if (token !== this._homeThreeToken) return;
      const THREE = this._homeTHREE;
      const scene = this._homeScene;

      // 移除旧模型根节点并尽量释放几何/材质
      if (this._homeRoot && scene) {
        try {
          scene.remove(this._homeRoot);
          this._homeRoot.traverse((obj) => {
            if (obj && obj.isMesh) {
              try {
                if (obj.geometry && obj.geometry.dispose) obj.geometry.dispose();
              } catch (e) {}
              try {
                if (obj.material) {
                  if (Array.isArray(obj.material)) obj.material.forEach((m) => m && m.dispose && m.dispose());
                  else obj.material.dispose && obj.material.dispose();
                }
              } catch (e2) {}
            }
          });
        } catch (e3) {}
      }

      const loader = new THREE.GLTFLoader();
      const root = await new Promise((resolve, reject) => {
        loader.load(
          modelUrl,
          (gltf) => resolve(gltf.scene || (gltf.scenes && gltf.scenes[0]) || null),
          undefined,
          (err) => reject(err || new Error("load model failed"))
        );
      });
      if (!root || token !== this._homeThreeToken) return;

      // 轻微下移，让头部更居中
      root.position.set(0, -0.32, 0);
      root.rotation.set(0, 0, 0);
      const box = new THREE.Box3().setFromObject(root);
      const size = box.getSize(new THREE.Vector3());
      const maxAxis = Math.max(size.x, size.y, size.z) || 1;
      // 与 pet-detail 默认 tuning.targetSize=3.0 对齐
      const scale = (1.22 / maxAxis) * HOME_TUNING_BASE_TARGET_SIZE;
      root.scale.setScalar(scale);

      this._homeBasePos = { x: root.position.x, y: root.position.y, z: root.position.z };
      this._homeBaseScale = scale;
      const box2 = new THREE.Box3().setFromObject(root);
      const size2 = box2.getSize(new THREE.Vector3());
      this._homeBaseSizeY = size2.y || 1;
      this._homeBaseRotY = 0;

      scene.add(root);
      this._homeRoot = root;
      this._autoYaw = 0;
      this._dragYaw = 0;
      this._lastDragTs = 0;
      this._applyHomeTuningToRoot();
    } finally {
      this._homeThreeInFlight = false;
      // 如果中途又有更新请求，则接着跑最新那一次
      try {
        if (this._homeThreePendingBuild && this._homeThreePendingBuild.token === this._homeThreeToken) {
          const p = this._homeThreePendingBuild;
          this._homeThreePendingBuild = null;
          if (p && p.modelUrl) this._buildHomeThreeScene(p.modelUrl, p.token);
        } else {
          this._homeThreePendingBuild = null;
        }
      } catch (e) {
        this._homeThreePendingBuild = null;
      }
    }
  },

  _destroyHomeThree() {
    try {
      if (this._homeCanvas && this._homeRaf) this._homeCanvas.cancelAnimationFrame(this._homeRaf);
    } catch (e) {}
    this._homeRaf = null;
    this._homeRoot = null;
    try {
      if (this._homeRenderer && this._homeRenderer.dispose) this._homeRenderer.dispose();
    } catch (e) {}
    this._homeRenderer = null;
    this._homeScene = null;
    this._homeCamera = null;
    this._homeCanvas = null;
  },

  _currentHomeFormKey() {
    return this.data.homeEggModelActive
      ? "egg"
      : `tier${Math.max(1, Math.min(3, Number(this.data.homeDisplayFormTier || 1) || 1))}`;
  },

  _loadHomeTuningFromServer(options = {}) {
    const applyStoredPosition = !!(options && options.applyStoredPosition);
    const skipApply = !!(options && options.skipApply);
    const fk = (options && options.formKey ? options.formKey : this._currentHomeFormKey());
    const raw = this._homeServerFormViewTuning || {};
    // 兼容两种后端返回形状：
    // 1) map：{ tier1: {tuning:{...}, camera:{...}}, tier2: ... }
    // 2) slot：{ tuning:{...}, camera:{...} }（当前形态可能不再带 fk key）
    const slot = raw && typeof raw === "object" ? (raw[fk] || raw) : {};
    const tuning = slot && slot.tuning && typeof slot.tuning === "object" ? slot.tuning : slot;
    const n = (v, d) => (Number.isFinite(Number(v)) ? Number(v) : d);

    const targetSize = n(tuning.targetSize, HOME_TUNING_BASE_TARGET_SIZE);
    const rawLiftMul = n(tuning.liftMul, HOME_TUNING_BASE_LIFT_MUL);
    // 兼容历史：pet-detail 可能写入非常极端的 liftMul（如 -50），不适合首页展示卡片。
    // 超过首页可用范围时，回退到首页默认基线，避免“模型被顶到很靠上/靠下”。
    const liftMul =
      rawLiftMul < HOME_TUNING_LIFT_MUL_MIN || rawLiftMul > HOME_TUNING_LIFT_MUL_MAX
        ? HOME_TUNING_BASE_LIFT_MUL
        : rawLiftMul;
    const baseRotYDeg = n(tuning.baseRotYDeg, 0);

    const computedScalePct = clamp((targetSize / HOME_TUNING_BASE_TARGET_SIZE) * 100, 20, 300);
    // 初始加载：只要不进入调参，就保持之前“默认初始尺度/角度/位置”，避免被 pet-detail 历史极端值影响
    const nextScalePct = applyStoredPosition ? computedScalePct : 100;
    const nextPosY = applyStoredPosition
      ? clamp((liftMul - HOME_TUNING_BASE_LIFT_MUL) * 100, -10000, 200)
      : 0;
    const nextRotY = applyStoredPosition ? clamp(baseRotYDeg, -180, 180) : 0;

    this.setData(
      {
        // X/Z 当前 home 实现只是“画面平移”，后端 tuning schema 里未必提供这些字段
        homeTunePosX: applyStoredPosition ? n(tuning.position_x, 0) : 0,
        homeTunePosY: nextPosY,
        homeTunePosYText: String(nextPosY),
        homeTunePosZ: applyStoredPosition ? n(tuning.position_z, 0) : 0,
        homeTuneScalePct: nextScalePct,
        homeTuneRotY: nextRotY,
      },
      () => {
        if (!skipApply) this._applyHomeTuningToRoot();
      }
    );
  },

  _applyHomeTuningToRoot() {
    if (!this._homeRoot || !this._homeBasePos) return;
    const px = Number(this.data.homeTunePosX || 0) || 0;
    const py = Number(this.data.homeTunePosY || 0) || 0;
    const pz = Number(this.data.homeTunePosZ || 0) || 0;
    const sp = Number(this.data.homeTuneScalePct || 100) || 100;
    const ry = Number(this.data.homeTuneRotY || 0) || 0;
    const spClamped = Math.max(20, Math.min(300, sp));
    const s = (Number(this._homeBaseScale || 1) * spClamped) / 100;

    // home 的 UI 用 homeTunePosY 表示“相对 base liftMul 的偏移”：
    // 当 homeTunePosY=0 时，不额外改变初始位姿（保持之前的基准位置）
    const deltaLiftMul = py / 100; // liftMul - HOME_TUNING_BASE_LIFT_MUL
    const baseSizeY = Number(this._homeBaseSizeY || 1) || 1;
    const fitSizeY = baseSizeY * (spClamped / 100);
    const dy = fitSizeY * deltaLiftMul;

    this._homeRoot.position.set(
      Number(this._homeBasePos.x || 0) + px,
      Number(this._homeBasePos.y || 0) + dy,
      Number(this._homeBasePos.z || 0) + pz
    );
    this._homeRoot.scale.setScalar(s);
    this._homeBaseRotY = (ry * Math.PI) / 180;
  },

  onToggleHomeTuning() {
    const next = !this.data.showHomeTuning;
    this.setData({ showHomeTuning: next }, () => {
      if (next) this._loadHomeTuningFromServer({ applyStoredPosition: true });
    });
  },

  onHomeTuningSlider(e) {
    const key = e && e.currentTarget && e.currentTarget.dataset ? e.currentTarget.dataset.key : "";
    let v = Number(e && e.detail ? e.detail.value : 0);
    if (!key) return;
    if (key === "homeTunePosY") v = clamp(v, -10000, 200);
    const update = { [key]: v };
    if (key === "homeTunePosY") update.homeTunePosYText = String(v);
    this.setData(update, () => this._applyHomeTuningToRoot());
  },

  onHomeResetTuning() {
    this.setData(
      {
        homeTunePosX: 0,
        homeTunePosY: 0,
        homeTunePosYText: "0",
        homeTunePosZ: 0,
        homeTuneScalePct: 100,
        homeTuneRotY: 0,
      },
      () => this._applyHomeTuningToRoot()
    );
  },

  onHomeSaveTuning() {
    const mascotId = (this.data.currentMascot && this.data.currentMascot.id) || "cute-dog";
    const formKey = this._currentHomeFormKey();
    const sp = clamp(Number(this.data.homeTuneScalePct || 100) || 100, 20, 300);
    const targetSize = clamp((sp / 100) * HOME_TUNING_BASE_TARGET_SIZE, 0.1, 200.0);
    const deltaLiftMul = (Number(this.data.homeTunePosY || 0) || 0) / 100;
    const liftMul = clamp(
      HOME_TUNING_BASE_LIFT_MUL + deltaLiftMul,
      HOME_TUNING_LIFT_MUL_MIN,
      HOME_TUNING_LIFT_MUL_MAX
    );
    const baseRotYDeg = clamp(Number(this.data.homeTuneRotY || 0) || 0, -180, 180);
    const position_x = Number(this.data.homeTunePosX || 0) || 0;
    const position_z = Number(this.data.homeTunePosZ || 0) || 0;

    // 与 pet-detail/companion 的后端 tuning schema 对齐：避免保存后仍回读旧数据
    const tuning = {
      ...HOME_TUNING_DEFAULTS,
      liftMul,
      targetSize,
      baseRotYDeg,
      // 让首页的 X/Z 也能作为“一整套调参”被存储并在回读时恢复
      position_x,
      position_z,
    };

    // 让服务端清掉“手动相机覆盖”（与 pet-detail 保存行为一致），避免调参后仍被旧 camera 结果抵消
    postCompanionSetViewTuning(mascotId, formKey, tuning, undefined, true, "home")
      .then(() => {
        // 保存接口的回包往往不包含 form_view_tuning，所以这里改为：保存后立即拉取 companion/state 再回读
        // 标记：只要用户从 home 页面保存过，就允许下次回首页时应用这次调参
        _writeHomeTuningLastSaved(mascotId, formKey);

        requestCompanionState(mascotId)
          .then((state) => {
            const data = state && typeof state === "object"
              ? (state.data && typeof state.data === "object" ? state.data : state)
              : {};
            const rawFvt = data && (data.form_view_tuning_home || data.form_view_tuning);
            this._homeServerFormViewTuning =
              rawFvt && typeof rawFvt === "object" && !Array.isArray(rawFvt) ? { ...rawFvt } : {};
            this._loadHomeTuningFromServer({ applyStoredPosition: true, formKey });
          })
          .catch(() => {});
        wx.showToast({ title: "已保存设置", icon: "success" });
      })
      .catch(() => wx.showToast({ title: "保存失败", icon: "none" }));
  },

  _guestUserDataForHome() {
    return {
      avatar: "https://p2.ssl.qhimgs1.com/sdr/400__/t0457bfb0ce39464fcc.jpg",
      parentName: "宝宝家长",
      babyName: "点击登录",
      babyAge: "3",
      email: "",
      phone: "",
    };
  },

  _applyLevelToData(starsVal) {
    const n = Number(starsVal || 0) || 0;
    if (app && typeof app.calculateLevel === "function") {
      const lv = app.calculateLevel(n);
      return {
        stars: n,
        level: lv.level,
        levelTitle: lv.title,
        levelIcon: lv.icon,
      };
    }
    return { stars: n, level: 1, levelTitle: "初级读者", levelIcon: "📖" };
  },

  /**
   * 与 app 会话对齐并刷新首页昵称/星星；已登录时优先请求 /users/me 同步服务端 reader_stars。
   */
  loadData() {
    if (typeof app.loadUserData === "function") {
      app.loadUserData();
    }
    const token =
      app && typeof app.getAuthToken === "function" ? String(app.getAuthToken() || "").trim() : "";
    const flagged = !!(app.globalData && app.globalData.isLoggedIn);
    const reallyLoggedIn = flagged && !!token;

    if (!reallyLoggedIn) {
      const lv = this._applyLevelToData(app.globalData.stars || 0);
      this.setData({
        sessionLoggedIn: false,
        userData: this._guestUserDataForHome(),
        ...lv,
      });
      return;
    }

    const lv0 = this._applyLevelToData(app.globalData.stars || 0);
    this.setData({
      sessionLoggedIn: true,
      userData: app.globalData.userData || {},
      ...lv0,
    });

    const base = getApiBaseUrl();
    if (app._shouldBlockLoopbackRequest && app._shouldBlockLoopbackRequest(base)) {
      return;
    }
    if (typeof app.fetchMyProfile !== "function") {
      return;
    }
    app.fetchMyProfile((err) => {
      if (err) {
        return;
      }
      const lv1 = this._applyLevelToData(app.globalData.stars || 0);
      this.setData({
        sessionLoggedIn: true,
        userData: app.globalData.userData || {},
        ...lv1,
      });
    });
  },

  // 加载保存的吉祥物
  loadSavedMascot() {
    try {
      const savedMascotId = wx.getStorageSync('selectedMascot');
      if (savedMascotId) {
        const mascot = MASCOT_AVATARS_ALL.find(m => m.id === savedMascotId);
        if (mascot) {
          const newPhotoList = buildMascotPhotoList(mascot.id);
          this.setData({
            currentMascot: mascotWithResolvedUrl(mascot),
            homePetStageBg: homePetStageBackgroundCss(mascot.id),
            currentPhotoList: newPhotoList,
            currentIndex: 0,
            currentImage: newPhotoList[0] || "",
            homeFormPosterUrls: newPhotoList
          });
        }
      }
    } catch (e) {}
  },

  // 切换头像选择器显示/隐藏
  toggleAvatarPicker() {
    this.setData({
      showAvatarPicker: !this.data.showAvatarPicker
    });
  },

  _persistHomeSelection(mascotId, formKey) {
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

  onHomeOpenSwitch() {
    // 切换过程中停止轮询刷新，避免并发触发多次重建造成“卡住”
    this._stopHomeSelectionWatcher();
    this.setData({ showHomeSwitchModal: true, homeSwitchStep: "menu" });
  },

  onHomeCloseSwitch() {
    this.setData({ showHomeSwitchModal: false, homeSwitchStep: "menu" });
    // 恢复监听
    this._startHomeSelectionWatcher();
  },

  onHomeSwitchPickMascot() {
    this.setData({ homeSwitchStep: "mascot" });
  },

  onHomeSwitchPickForm() {
    // 进入“形态”页时，强制按当前选中伴宠刷新三档海报（避免仍展示上一次伴宠的形态图）
    let mid = (this.data.currentMascot && this.data.currentMascot.id) || "cute-dog";
    try {
      const saved = String(wx.getStorageSync("selectedMascot") || "").trim();
      if (saved) mid = saved;
    } catch (e) {}
    this.setData({ homeSwitchStep: "form", homeFormPosterUrls: buildMascotPhotoList(mid) });
  },

  onHomeSwitchBack() {
    this.setData({ homeSwitchStep: "menu" });
  },

  onHomeSelectMascotFromModal(e) {
    const mascot = e && e.currentTarget && e.currentTarget.dataset ? e.currentTarget.dataset.mascot : null;
    if (!mascot || mascot.locked) return;
    // 直接写全局并重建：立刻进入加载动画
    let fk = "tier1";
    try {
      const curFk = String(wx.getStorageSync("selectedMascotFormKey") || "").trim();
      if (curFk) fk = curFk;
    } catch (e) {}
    this._persistHomeSelection(mascot.id, fk);
    this.setData({ showHomeSwitchModal: false, homeSwitchStep: "menu" }, () => this._loadAndBuildHomeThree());
  },

  onHomeSelectFormTier(e) {
    const tier = Number(e && e.currentTarget && e.currentTarget.dataset ? e.currentTarget.dataset.tier : 0);
    if (!tier) return;
    const unlocked = new Set((this.data.homeUnlockedFormTiers || []).map((n) => Number(n)));
    if (!unlocked.has(tier)) return;
    const mid = (this.data.currentMascot && this.data.currentMascot.id) || "cute-dog";
    const fk = `tier${tier}`;
    // 先立刻切前端展示：写入本地并重建（不会等待后端，避免“卡住”）
    this._persistHomeSelection(mid, fk);
    this.setData({ showHomeSwitchModal: false, homeSwitchStep: "menu" }, () => this._loadAndBuildHomeThree());
    // 后端同步放后台，不阻塞 UI
    postCompanionSetDisplayForm(mid, tier).catch(() => {});
  },

  // 继续阅读
  continueReading() {
    try {
      const raw = wx.getStorageSync("readingRecent");
      const list = Array.isArray(raw) ? raw : [];
      const first = list.length ? list[0] : null;
      const bookId = String((first && first.bookId) || "").trim();
      if (bookId) {
        const source = String((first && first.source) || "").trim();
        const page = Math.max(0, Number((first && first.pageIndex) || 0) || 0);
        const query = source === "library"
          ? `id=${encodeURIComponent(bookId)}&source=library&startPage=${page}`
          : `id=${encodeURIComponent(bookId)}&startPage=${page}`;
        wx.navigateTo({ url: `/pages/read/read?${query}` });
        return;
      }
    } catch (e) {}
    // 没有最近阅读记录：跳到书架
    wx.switchTab({ url: "/pages/books/books" });
  },

  // 导航到菜单
  navigateToMenu(e) {
    const route = e.currentTarget.dataset.route;
    
    // TabBar页面用switchTab
    if (route === '/books' || route === '/play' || route === '/voice') {
      wx.switchTab({
        url: `/pages${route}${route}`
      });
    } else {
      wx.navigateTo({
        url: `/pages${route}${route}`
      });
    }
  },

  // 跳转到个人中心
  goToAuth() {
    wx.switchTab({
      url: '/pages/auth/auth'
    });
  },

  // 跳转到成长记录
  goToGrowth() {
    wx.navigateTo({
      url: '/pages/growth/growth'
    });
  },

  // 跳转到绘本馆
  goToBooks() {
    wx.switchTab({
      url: '/pages/books/books'
    });
  },

  // 跳转到签到
  goToCheckIn() {
    wx.navigateTo({
      url: '/pages/check-in/check-in'
    });
  },

  // 跳转到涂色
  goToColor() {
    wx.navigateTo({
      url: '/pages/color/color'
    });
  },

  // 跳转到 AR 面具演说家
  goToArFace() {
    wx.navigateTo({
      url: '/pages/ar-face/ar-face'
    });
  },

  initHomeGuide() {
    if (!isMainDone("authDone")) return;
    if (isMainDone("homeDone")) return;
    const steps = [
      {
        highlight: "pet",
        title: "欢迎来到陪伴首页",
        desc: "这里是可交互3D伴宠，滑动可与它互动，建立进入感。",
      },
      {
        highlight: "status",
        title: "成长状态会实时变化",
        desc: "阅读和互动会影响饥饿、清洁、心情、睡眠四项状态。",
      },
      {
        highlight: "voice",
        title: "先去克隆魔法音",
        desc: "完成音色训练后，阅读时就能切换到家人讲故事。",
      },
    ];
    this.setData({
      showGuide: true,
      guideSteps: steps,
      guideStepIndex: 0,
    });
    this.updateGuideStep();
  },

  updateGuideStep() {
    const list = Array.isArray(this.data.guideSteps) ? this.data.guideSteps : [];
    const idx = Number(this.data.guideStepIndex || 0);
    const cur = list[idx];
    if (!cur) {
      this.closeGuide(false);
      return;
    }
    this.setData({
      guideHighlight: String(cur.highlight || ""),
      guideTitle: String(cur.title || ""),
      guideDesc: String(cur.desc || ""),
    });
  },

  onGuideNext() {
    const idx = Number(this.data.guideStepIndex || 0);
    const next = idx + 1;
    if (next >= (this.data.guideSteps || []).length) {
      markMainDone("homeDone");
      this.closeGuide(false);
      return;
    }
    this.setData({ guideStepIndex: next }, () => this.updateGuideStep());
  },

  onGuideGoVoice() {
    markMainDone("homeDone");
    this.closeGuide(false);
    this.goToVoice();
  },

  closeGuide(onlyClose = true) {
    if (!onlyClose) {
      this.setData({
        showGuide: false,
        guideSteps: [],
        guideStepIndex: 0,
        guideHighlight: "",
        guideTitle: "",
        guideDesc: "",
      });
      return;
    }
    this.setData({ showGuide: false });
  },
});