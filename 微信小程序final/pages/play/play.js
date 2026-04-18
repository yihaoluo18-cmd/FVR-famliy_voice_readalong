const { getAmusementParkProgress } = require("../../utils/amusement-park-stars.js");
const { isMainDone, markMainDone } = require("../../utils/guide-flow.js");
const { getUserId, isGuestCompanionUserId, requestEggState } = require("../../utils/pet-growth.js");

/** 四档累计星：节点上数字为总量；堆叠星最多画 3 颗表示「有多颗」 */
const AP_MILESTONE_TOTALS = [1, 3, 5, 10];

const BASE_GAMES = [
  {
    id: "speaker",
    title: "小小演说家",
    desc: "看图说话得奖励",
    iconEmoji: "🎤",
    emoji: "🎤",
    route: "/pages/speaker/speaker",
    delay: 0.05,
    unlocked: true,
  },
  {
    id: "color",
    title: "涂色小画家",
    desc: "给可爱动物涂上颜色",
    iconEmoji: "🖌️",
    emoji: "🖌️",
    route: "/pages/color/color",
    delay: 0.1,
    unlocked: true,
  },
  {
    id: "companion",
    title: "AI伴宠",
    desc: "语音聊天 + 可爱互动",
    iconEmoji: "🐶",
    emoji: "✨",
    route: "/pages/companion/companion",
    delay: 0.15,
    unlocked: true,
  },
  {
    id: "petEggGarden",
    title: "宠物蛋乐园",
    desc: "签到和阅读都会让蛋蛋长大",
    iconEmoji: "🥚",
    emoji: "✨",
    route: "/pages/pet-system/pet-system",
    delay: 0.2,
    unlocked: true,
  },
];

const FERRIS_CABINS = [0, 45, 90, 135, 180, 225, 270, 315].map((angle) => ({ angle }));

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

Page({
  data: {
    games: [],
    ferrisDeg: 0,
    ferrisCabins: FERRIS_CABINS,
    apCount: 0,
    apTotal: 4,
    apNodes: [],
    apFillPercent: 0,
    showGuide: false,
    guideSteps: [],
    guideStepIndex: 0,
    guideHighlight: '',
    guideTitle: '',
    guideDesc: '',
  },

  onLoad() {
    this._ferrisDeg = 0;
    this._ferrisDragging = false;
    this._ferrisRect = null;
    this._ferrisTimer = null;
    this._lastTouchAngle = 0;
    this.refreshAmusementParkUi();
  },

  onShow() {
    this.refreshAmusementParkUi();
    this.measureFerrisTouch();
    // 从其它 Tab 返回时 onReady 不会再次执行，需重新启动 idle 旋转
    this._ensureFerrisSpinTimer();
    this.initPlayGuide();
  },

  onReady() {
    this.measureFerrisTouch();
    this._ensureFerrisSpinTimer();
  },

  onHide() {
    if (this._ferrisTimer) {
      clearInterval(this._ferrisTimer);
      this._ferrisTimer = null;
    }
  },

  onUnload() {
    if (this._ferrisTimer) {
      clearInterval(this._ferrisTimer);
      this._ferrisTimer = null;
    }
  },

  _ensureFerrisSpinTimer() {
    if (this._ferrisTimer) {
      clearInterval(this._ferrisTimer);
      this._ferrisTimer = null;
    }
    const fromData = Number(this.data.ferrisDeg);
    if (Number.isFinite(fromData)) {
      this._ferrisDeg = fromData;
    } else if (typeof this._ferrisDeg !== "number" || Number.isNaN(this._ferrisDeg)) {
      this._ferrisDeg = 0;
    }
    this._ferrisTimer = setInterval(() => {
      if (this._ferrisDragging) return;
      this._ferrisDeg += 0.16;
      this.setData({ ferrisDeg: this._ferrisDeg });
    }, 45);
  },

  measureFerrisTouch() {
    wx.createSelectorQuery()
      .in(this)
      .select(".ride-touch-target")
      .boundingClientRect()
      .exec((res) => {
        const rect = res && res[0];
        if (rect && rect.width) this._ferrisRect = rect;
      });
  },

  computeTouchAngle(clientX, clientY) {
    const r = this._ferrisRect;
    if (!r || !r.width) return 0;
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    return (Math.atan2(clientY - cy, clientX - cx) * 180) / Math.PI;
  },

  onRideTouchStart(e) {
    this._ferrisDragging = true;
    const t = e.touches[0];
    const x = t.clientX;
    const y = t.clientY;
    wx.createSelectorQuery()
      .in(this)
      .select(".ride-touch-target")
      .boundingClientRect()
      .exec((res) => {
        const rect = res && res[0];
        if (rect && rect.width) this._ferrisRect = rect;
        this._lastTouchAngle = this.computeTouchAngle(x, y);
      });
  },

  onRideTouchMove(e) {
    if (!this._ferrisDragging) return;
    if (!this._ferrisRect || !this._ferrisRect.width) {
      this.measureFerrisTouch();
      return;
    }
    const t = e.touches[0];
    const angle = this.computeTouchAngle(t.clientX, t.clientY);
    let delta = angle - this._lastTouchAngle;
    if (delta > 180) delta -= 360;
    if (delta < -180) delta += 360;
    this._lastTouchAngle = angle;
    this._ferrisDeg += delta;
    this.setData({ ferrisDeg: this._ferrisDeg });
  },

  onRideTouchEnd() {
    this._ferrisDragging = false;
    this.measureFerrisTouch();
  },

  refreshAmusementParkUi() {
    const progress = getAmusementParkProgress();
    const doneSet = new Set(progress.doneIds || []);
    const guest = isGuestCompanionUserId(getUserId());
    const applyGames = (unlockedOthers) => {
      const games = BASE_GAMES.map((g) => ({
        ...g,
        done: doneSet.has(g.id),
        unlocked: guest ? g.unlocked : (unlockedOthers ? true : g.id === "petEggGarden"),
      }));
      this.setData({ games });
    };

    if (guest) {
      applyGames(true);
    } else {
      requestEggState()
        .then((data) => applyGames(shouldUnlockAmusementGamesByEggState(data)))
        .catch(() => applyGames(false));
    }
    const c = Math.min(4, Number(progress.count) || 0);
    const apFillPercent = Math.round((c / 4) * 100);
    const apNodes = AP_MILESTONE_TOTALS.map((stars, idx) => ({
      stars,
      leftPct: Number((((idx + 0.5) / 4) * 100).toFixed(2)),
      stackLayers: Array.from({ length: Math.min(stars, 3) }, (_, i) => i),
    }));
    this.setData({
      apCount: c,
      apTotal: 4,
      apFillPercent,
      apNodes,
    });
  },

  playGame(e) {
    const game = e.currentTarget.dataset.game;
    if (!game || !game.unlocked) {
      wx.showToast({ title: "该游戏尚未解锁", icon: "none" });
      return;
    }
    if (!game.route) {
      wx.showToast({ title: "功能开发中", icon: "none" });
      return;
    }
    markMainDone("playDone");
    this.closeGuide();
    wx.navigateTo({ url: game.route });
  },

  initPlayGuide() {
    if (!isMainDone("readDone")) return;
    if (isMainDone("playDone")) return;
    const steps = [
      {
        highlight: 'games',
        title: '欢迎来到游乐园',
        desc: '从小小演说家开始，让表达训练和阅读成长连接起来。',
      },
      {
        highlight: 'egg',
        title: '宠物蛋乐园是成长汇总',
        desc: '阅读与签到都会转化为孵化与成长进度，形成正反馈。',
      },
    ];
    this.setData({ showGuide: true, guideSteps: steps, guideStepIndex: 0 });
    this.updateGuideStep();
  },

  updateGuideStep() {
    const list = Array.isArray(this.data.guideSteps) ? this.data.guideSteps : [];
    const idx = Number(this.data.guideStepIndex || 0);
    const cur = list[idx];
    if (!cur) return this.closeGuide();
    this.setData({
      guideHighlight: String(cur.highlight || ''),
      guideTitle: String(cur.title || ''),
      guideDesc: String(cur.desc || ''),
    });
  },

  onGuideNext() {
    const next = Number(this.data.guideStepIndex || 0) + 1;
    if (next >= (this.data.guideSteps || []).length) return this.closeGuide();
    this.setData({ guideStepIndex: next }, () => this.updateGuideStep());
  },

  closeGuide() {
    this.setData({
      showGuide: false,
      guideSteps: [],
      guideStepIndex: 0,
      guideHighlight: '',
      guideTitle: '',
      guideDesc: '',
    });
  },

  noop() {},
});
