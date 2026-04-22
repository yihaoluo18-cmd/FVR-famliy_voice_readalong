const { getAmusementParkProgress, buildAmusementParkHint } = require("../../utils/amusement-park-stars.js");
const { isMainDone, markMainDone } = require("../../utils/guide-flow.js");
const { getUserId, isGuestCompanionUserId, requestEggState } = require("../../utils/pet-growth.js");

/** 四档累计星：节点上数字为总量；堆叠星最多画 3 颗表示「有多颗」 */
const AP_MILESTONE_TOTALS = [1, 3, 5, 10];

const BASE_GAMES = [
  {
    id: "speaker",
    title: "小小演说家",
    desc: "看图说话得奖励",
    iconUrl: "../../assets/icons/home-mic.png",
    stickerUrl: "../../assets/icons/home-mic.png",
    emoji: "🎤",
    route: "/pages/speaker/speaker",
    delay: 0.05,
    unlocked: true,
  },
  {
    id: "color",
    title: "涂色小画家",
    desc: "给可爱动物涂上颜色",
    iconUrl: "../../assets/icons/home-color.png",
    stickerUrl: "../../assets/icons/home-color.png",
    emoji: "🖌️",
    route: "/pages/color/color",
    delay: 0.1,
    unlocked: true,
  },
  {
    id: "companion",
    title: "AI聊伴",
    desc: "语音聊天 + 可爱互动",
    iconUrl: "../../assets/icons/home-chat.png",
    stickerUrl: "../../assets/icons/home-chat.png",
    emoji: "✨",
    route: "/pages/companion/companion",
    delay: 0.15,
    unlocked: true,
  },
  {
    id: "petEggGarden",
    title: "宠物蛋乐园",
    desc: "签到和阅读都会让蛋蛋长大",
    iconUrl: "../../assets/icons/home-egg.png",
    stickerUrl: "../../assets/icons/home-egg.png",
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
    ferrisCabinFilled: Array.from({ length: FERRIS_CABINS.length }, () => false),
    apCount: 0,
    apTotal: 4,
    apNodes: [],
    apFillPercent: 0,
    apStarsToday: 0,
    apHint: '',
    flyStar: { show: false, phase: 'ready', x: 0, y: 0, dx: 0, dy: 0 },
    groundStars: [],
    apBonusStars: 0,
    ferrisNotes: [],
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
    this._apStarsPrev = null;
    this._groundSeed = 0;
    this._initFerrisNotes();
    this._initGroundStars();
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

  refreshAmusementParkUi(options = {}) {
    const suppressFly = !!(options && options.suppressFly);
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
    const baseStars = Math.max(0, Number(progress.milestoneStarsEarnedToday || 0) || 0);
    const bonus = Math.max(0, Number(this.data.apBonusStars || 0) || 0);
    const apStarsToday = baseStars + bonus;
    const apHint = buildAmusementParkHint(progress);
    const cabins = this.data.ferrisCabins || [];
    const maxFill = Math.min(cabins.length, apStarsToday);
    const nextCabinFilled = cabins.map((_, idx) => idx < maxFill);
    this.setData({
      apCount: c,
      apTotal: 4,
      apFillPercent,
      apNodes,
      apStarsToday,
      apHint,
      ferrisCabinFilled: nextCabinFilled,
    });

    // 从其它页面返回时，若“今日游乐园累计星数”增加，则补一个飞入舱位的动效
    // 首次进入仅同步状态，不播放飞星；后续“新增”再播放
    const prevRaw = this._apStarsPrev;
    const prev = prevRaw === null || prevRaw === undefined ? null : (Number(prevRaw) || 0);
    this._apStarsPrev = apStarsToday;
    if (!suppressFly && prev !== null && apStarsToday > prev) {
      // 仅为“新增且在舱位上可见的那部分”播放动画
      const from = Math.min(prev, cabins.length);
      const to = Math.min(apStarsToday, cabins.length);
      const delta = Math.max(0, to - from);
      if (delta > 0) this._queueFlyStars(from, delta);
    }
  },

  _initGroundStars() {
    // 生成几颗“掉落到地面”的可拾取星星（仅做互动展示，不影响任务结算）
    const seed = Number(this._groundSeed || 0) + 1;
    this._groundSeed = seed;
    const lefts = [16, 34, 56, 72, 86];
    const count = 4;
    const groundStars = Array.from({ length: count }, (_, i) => ({
      id: `g${seed}_${i}`,
      leftPct: lefts[i % lefts.length],
      delayMs: 120 + i * 140,
      picked: false,
    }));
    this.setData({ groundStars });
  },

  _initFerrisNotes() {
    // 音符粒子：跟随摩天轮缓慢“飘出”，若隐若现
    const notes = ["♪", "♫", "♩", "♬"];
    const ferrisNotes = Array.from({ length: 10 }, (_, i) => ({
      id: `n${i}`,
      glyph: notes[i % notes.length],
      // 让音符围绕摩天轮分布，但相位错开
      angle: (i * 36) % 360,
      radius: 214 + (i % 3) * 18,
      delayMs: 160 * i,
      size: 22 + (i % 3) * 2,
      drift: 8 + (i % 4) * 3,
    }));
    this.setData({ ferrisNotes });
  },

  _nextEmptyCabinIndex() {
    const filled = Array.isArray(this.data.ferrisCabinFilled) ? this.data.ferrisCabinFilled : [];
    const idx = filled.findIndex((x) => !x);
    if (idx >= 0) return idx;
    return Math.max(0, filled.length - 1);
  },

  onPickGroundStar(e) {
    const id = e && e.currentTarget && e.currentTarget.dataset ? String(e.currentTarget.dataset.id || "") : "";
    if (!id) return;
    const list = Array.isArray(this.data.groundStars) ? this.data.groundStars : [];
    const hit = list.find((s) => s && s.id === id);
    if (!hit || hit.picked) return;

    const targetCabinIdx = this._nextEmptyCabinIndex();
    // 先标记为已拾取，避免重复点击
    const nextList = list.map((s) => (s.id === id ? { ...s, picked: true } : s));
    this.setData({ groundStars: nextList });

    this._animateFlyStarFromSelector(`#groundStar-${id}`, targetCabinIdx).then(() => {
      // 飞到舱位后点亮，并增加“展示用”今日累计星
      const filled = Array.isArray(this.data.ferrisCabinFilled) ? [...this.data.ferrisCabinFilled] : [];
      if (filled.length) filled[targetCabinIdx] = true;
      const bonus = Math.max(0, Number(this.data.apBonusStars || 0) || 0) + 1;
      this.setData(
        { ferrisCabinFilled: filled, apBonusStars: bonus },
        () => this.refreshAmusementParkUi({ suppressFly: true })
      );
    });
  },

  _animateFlyStarFromSelector(startSelector, cabinIdx) {
    const idx = Math.max(0, Math.min((this.data.ferrisCabins || []).length - 1, Number(cabinIdx) || 0));
    const sel = String(startSelector || "").trim();
    if (!sel) return Promise.resolve();
    return new Promise((resolve) => {
      wx.createSelectorQuery()
        .in(this)
        .select(sel)
        .boundingClientRect()
        .select(`#ferrisCabinBox-${idx}`)
        .boundingClientRect()
        .exec((res) => {
          const start = res && res[0];
          const end = res && res[1];
          if (!start || !end) {
            resolve();
            return;
          }
          const sx = start.left + start.width / 2;
          const sy = start.top + start.height / 2;
          const ex = end.left + end.width / 2;
          const ey = end.top + end.height / 2;
          this.setData({ flyStar: { show: true, phase: "ready", x: sx, y: sy, dx: 0, dy: 0 } });
          setTimeout(() => {
            this.setData({ flyStar: { show: true, phase: "go", x: sx, y: sy, dx: ex - sx, dy: ey - sy } });
          }, 16);
          setTimeout(() => {
            this.setData({ flyStar: { ...this.data.flyStar, show: false, phase: "ready" } });
            resolve();
          }, 640);
        });
    });
  },

  _queueFlyStars(startIdx, delta) {
    if (!Number.isFinite(startIdx) || startIdx < 0) startIdx = 0;
    const d = Math.max(0, Number(delta || 0) || 0);
    if (!d) return;
    if (!this._flyStarQueue) this._flyStarQueue = [];
    for (let i = 0; i < d; i++) this._flyStarQueue.push(startIdx + i);
    if (this._flyStarRunning) return;
    this._flyStarRunning = true;
    this._runNextFlyStar();
  },

  _runNextFlyStar() {
    const q = Array.isArray(this._flyStarQueue) ? this._flyStarQueue : [];
    const nextIdx = q.shift();
    this._flyStarQueue = q;
    if (nextIdx === undefined || nextIdx === null) {
      this._flyStarRunning = false;
      return;
    }
    this._animateFlyStarIntoCabin(Number(nextIdx) || 0).finally(() => {
      // 小间隔，让连续奖励更顺滑
      setTimeout(() => this._runNextFlyStar(), 140);
    });
  },

  _animateFlyStarIntoCabin(cabinIdx) {
    const idx = Math.max(0, Math.min((this.data.ferrisCabins || []).length - 1, Number(cabinIdx) || 0));
    return new Promise((resolve) => {
      // 起点：进度卡头部的不可见锚点；终点：指定舱位
      wx.createSelectorQuery()
        .in(this)
        .select("#apFlyAnchor")
        .boundingClientRect()
        .select(`#ferrisCabinBox-${idx}`)
        .boundingClientRect()
        .exec((res) => {
          const start = res && res[0];
          const end = res && res[1];
          if (!start || !end) {
            resolve();
            return;
          }
          const sx = start.left + start.width / 2;
          const sy = start.top + start.height / 2;
          const ex = end.left + end.width / 2;
          const ey = end.top + end.height / 2;
          // 先放到起点，再触发位移（用 CSS transition）
          this.setData({
            flyStar: { show: true, phase: "ready", x: sx, y: sy, dx: 0, dy: 0 },
          });
          setTimeout(() => {
            this.setData({
              flyStar: { show: true, phase: "go", x: sx, y: sy, dx: ex - sx, dy: ey - sy },
            });
          }, 16);
          setTimeout(() => {
            this.setData({ flyStar: { ...this.data.flyStar, show: false, phase: "ready" } });
            resolve();
          }, 640);
        });
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
