const { requestEggState, claimEggSlot } = require("../../utils/pet-growth.js");
const { getPetById, getFormTierPosterUrl, getStaticEggPosterUrl } = require("../../utils/pets-catalog.js");

const DEFAULT_BASE_URL = "http://127.0.0.1:9880";

function getApiBaseUrl() {
  const app = getApp();
  return app && app.getApiBaseUrl ? app.getApiBaseUrl() : DEFAULT_BASE_URL;
}

function resolvePosterUrl(rel) {
  const s = String(rel || "").trim();
  if (!s) return "";
  if (s.startsWith("http")) return s;
  if (s.startsWith("/assets/")) {
    const { toMiniprogramAssetUrl } = require("../../utils/asset-url.js");
    return toMiniprogramAssetUrl(s);
  }
  if (s.startsWith("/ar_companion/")) return `${getApiBaseUrl()}${s}`;
  if (s.startsWith("/ar_companion")) return `${getApiBaseUrl()}${s.startsWith("/") ? s : `/${s}`}`;
  if (s.startsWith("/")) return `${getApiBaseUrl()}${s}`;
  return `${getApiBaseUrl()}/${s}`;
}

/** 与后端一致：只要在 unlocked_mascot_ids 中，槽位应视为已拥有；并修正偶发的 ui_state 不同步 */
function normalizeSlotsForUnlockedList(slots, unlockedMascotIds) {
  const ids = Array.isArray(unlockedMascotIds) ? unlockedMascotIds : [];
  const set = new Set(ids.map((x) => String(x || "").trim()).filter(Boolean));
  return (Array.isArray(slots) ? slots : []).map((slot) => {
    if (!slot || typeof slot !== "object") return slot;
    const mid = String(slot.mascot_id || "").trim();
    if (!mid || !set.has(mid)) return slot;
    if (slot.ui_state === "claimed") return slot;
    return {
      ...slot,
      ui_state: "claimed",
      progress_percent: 100,
      progress_need: 0,
      hint:
        slot.rule === "starter"
          ? slot.hint
          : `${String(slot.label || "").trim() || "小伙伴"} 已解锁`,
    };
  });
}

function enrichSlotsWithPosters(slots) {
  const list = Array.isArray(slots) ? slots : [];
  const personaBgMap = {
    default: "rgba(250, 204, 21, 0.16)", // 柴犬淡黄色
    cute_fox: "rgba(236, 72, 153, 0.14)", // 狐狸淡粉色
    cute_dino: "rgba(34, 197, 94, 0.14)", // 绵羊淡绿色
    cute_cat: "rgba(59, 130, 246, 0.14)", // 猫淡蓝色
    cute_bunny: "rgba(147, 197, 253, 0.14)", // 兔子淡天蓝
    cute_squirrel: "rgba(245, 158, 11, 0.14)", // 松鼠淡橘金
    cute_chick: "rgba(251, 191, 36, 0.14)", // 小鸡淡金黄
    cute_panda: "rgba(232, 121, 169, 0.12)", // 熊猫淡粉
    cute_koala: "rgba(20, 184, 166, 0.12)", // 仓鼠淡青
    cute_penguin: "rgba(107, 114, 128, 0.12)", // 企鹅淡灰
  };

  function bgColorForMascotId(mascotId) {
    const mid = String(mascotId || "").trim();
    const pet = mid ? getPetById(mid) : null;
    const pid = pet && pet.personaId ? pet.personaId : "default";
    return personaBgMap[pid] || personaBgMap.default;
  }

  return list.map((slot) => {
    if (!slot) return slot;
    const mid = String(slot.mascot_id || slot.mascotId || "").trim();
    const bgColor = bgColorForMascotId(mid);
    const emoji = String(slot.emoji || "").trim() || getMascotEmoji(mid);

    if (slot.ui_state !== "claimed") return { ...slot, bgColor, emoji };

    const pet = mid ? getPetById(mid) : null;
    if (!pet) return { ...slot, bgColor, emoji };
    const eggActive = !!slot.egg_model_active;
    const tier = Number(slot.display_form_tier) || 1;

    const posterRel = eggActive ? getStaticEggPosterUrl(pet) : getFormTierPosterUrl(pet, tier);
    const posterUrl2d = resolvePosterUrl(posterRel);

    return { ...slot, bgColor, posterUrl2d, emoji };
  });
}

function getMascotEmoji(mascotId) {
  const map = {
    "cute-dog": "🐶",
    "cute-fox": "🦊",
    "cute-dino": "🐑",
    "cute-cat": "🐱",
    "cute-bunny": "🐰",
    "cute-squirrel": "🐿️",
    "cute-chick": "🐥",
    "cute-panda": "🐼",
    "cute-koala": "🐹",
    "cute-penguin": "🐧",
  };
  const id = String(mascotId || "").trim();
  return map[id] || "🥚";
}

Page({
  data: {
    loading: true,
    slots: [],
    unlocked_mascot_ids: [],
    has_ready_to_claim: false,
    read_lifetime: 0,
    checkin_month_total: 0,
    hintLine: "",
    showUnlockOverlay: false,
    unlockOverlayLabel: "",
    productSlots: [],
    highlightSlots: [],
    showcaseSlots: [],
    showcaseScrollLeft: 0,
    showcaseScrollWithAnimation: false,
    aquariumEggs: [],
  },

  onShow() {
    this.loadState();
    this.startShowcaseAutoScroll();
  },

  onHide() {
    this.stopShowcaseAutoScroll();
    this.stopAquariumPhysics();
  },

  onUnload() {
    this.stopShowcaseAutoScroll();
    this.stopAquariumPhysics();
  },

  loadState() {
    this.setData({ loading: true });
    requestEggState()
      .then((data) => {
        const unl = data.unlocked_mascot_ids || [];
        const rawSlots = Array.isArray(data.slots) ? data.slots : [];
        const slots = enrichSlotsWithPosters(normalizeSlotsForUnlockedList(rawSlots, unl));
        const productSlots = this.buildProductSlots(slots);
        const highlightSlots = this.buildHighlightSlots(productSlots);
        const showcaseSlots = this.buildShowcaseSlots(productSlots);
        const aquariumSlots = this.buildAquariumSlots(productSlots);
        this.setData({
          slots,
          productSlots,
          highlightSlots,
          showcaseSlots,
          unlocked_mascot_ids: unl,
          has_ready_to_claim: !!data.has_ready_to_claim,
          read_lifetime: data.read_lifetime || 0,
          checkin_month_total: data.checkin_month_total || 0,
          loading: false,
          hintLine: `本月已签到 ${data.checkin_month_total || 0} 天 · 阅读完成 ${data.read_lifetime || 0} 本`,
        });
        this.initAquariumEggs(aquariumSlots);
        try {
          const app = getApp();
          const { reportAmusementParkTaskDone } = require("../../utils/amusement-park-stars.js");
          reportAmusementParkTaskDone(app, "petEggGarden");
        } catch (e) {}
      })
      .catch(() => {
        this.setData({ loading: false });
        wx.showToast({ title: "加载失败", icon: "none" });
      });
  },

  onClaimTap(e) {
    const idx = Number(e.currentTarget.dataset.index);
    if (!Number.isFinite(idx)) return;
    const slot = this.data.slots[idx];
    if (!slot || slot.ui_state !== "ready") return;

    this.setData({ showUnlockOverlay: true, unlockOverlayLabel: slot.label || "新伙伴" });
    claimEggSlot(idx)
      .then((data) => {
        const unl = data.unlocked_mascot_ids || [];
        const rawSlots = Array.isArray(data.slots) ? data.slots : [];
        const slots = enrichSlotsWithPosters(normalizeSlotsForUnlockedList(rawSlots, unl));
        const productSlots = this.buildProductSlots(slots);
        const highlightSlots = this.buildHighlightSlots(productSlots);
        const showcaseSlots = this.buildShowcaseSlots(productSlots);
        const aquariumSlots = this.buildAquariumSlots(productSlots);
        this.setData({
          slots,
          productSlots,
          highlightSlots,
          showcaseSlots,
          unlocked_mascot_ids: unl,
          has_ready_to_claim: !!data.has_ready_to_claim,
          showUnlockOverlay: false,
        });
        this.initAquariumEggs(aquariumSlots);
        wx.showToast({ title: `已获得 ${slot.label} 的宠物蛋`, icon: "success" });
        const mid = String(slot.mascot_id || "").trim();
        if (mid) wx.navigateTo({ url: `/pages/pet-detail/pet-detail?id=${encodeURIComponent(mid)}` });
      })
      .catch(() => {
        this.setData({ showUnlockOverlay: false });
        wx.showToast({ title: "领取失败，请重试", icon: "none" });
      });
  },

  goToCompanion(e) {
    const mid = String(
      (e &&
        e.currentTarget &&
        e.currentTarget.dataset &&
        (e.currentTarget.dataset.mascotId || e.currentTarget.dataset.mascot_id)) ||
        ""
    ).trim();
    if (!mid) return;
    wx.navigateTo({ url: `/pages/pet-detail/pet-detail?id=${encodeURIComponent(mid)}` });
  },

  goHome() {
    wx.navigateBack({ fail: () => wx.switchTab({ url: "/pages/home/home" }) });
  },

  buildProductSlots(slots) {
    // 已解锁/已拥有优先展示（提前放置），其余：可领取 > 孵化中 > 未解锁
    const stateOrder = { claimed: 0, ready: 1, incubating: 2, locked: 3 };
    const FIRST_MASCOT_ID = "cute-dog"; // 柴柴小星固定首位展示
    return (Array.isArray(slots) ? slots : [])
      .slice()
      .sort((a, b) => {
        const aFirst = String(a && a.mascot_id || "") === FIRST_MASCOT_ID;
        const bFirst = String(b && b.mascot_id || "") === FIRST_MASCOT_ID;
        if (aFirst !== bFirst) return aFirst ? -1 : 1;
        const oa = Object.prototype.hasOwnProperty.call(stateOrder, a.ui_state) ? stateOrder[a.ui_state] : 99;
        const ob = Object.prototype.hasOwnProperty.call(stateOrder, b.ui_state) ? stateOrder[b.ui_state] : 99;
        if (oa !== ob) return oa - ob;
        return Number(a.slot_index || 0) - Number(b.slot_index || 0);
      });
  },

  buildHighlightSlots(productSlots) {
    const list = Array.isArray(productSlots) ? productSlots : [];
    return list.slice(0, Math.min(5, list.length));
  },

  buildAquariumSlots(productSlots) {
    const list = Array.isArray(productSlots) ? productSlots : [];
    return list.filter((item) => String(item && item.ui_state || "") === "claimed");
  },

  buildShowcaseSlots(productSlots) {
    const list = Array.isArray(productSlots) ? productSlots : [];
    if (!list.length) return [];
    const loop = list.concat(list);
    return loop.map((item, idx) => ({
      ...item,
      __k: `${item.slot_index}-${idx}`,
    }));
  },

  startShowcaseAutoScroll() {
    this.stopShowcaseAutoScroll();
    this._showcaseUserTouching = false;
    this._showcaseMaxScrollLeft = 1200;
    this._showcaseTick = setInterval(() => {
      if (this._showcaseUserTouching) return;
      let next = Number(this.data.showcaseScrollLeft || 0) + 2;
      if (next >= this._showcaseMaxScrollLeft) next = 0;
      this.setData({ showcaseScrollWithAnimation: false, showcaseScrollLeft: next });
    }, 36);
  },

  stopShowcaseAutoScroll() {
    if (this._showcaseTick) {
      clearInterval(this._showcaseTick);
      this._showcaseTick = null;
    }
  },

  onShowcaseTouchStart() {
    this._showcaseUserTouching = true;
  },

  onShowcaseTouchEnd() {
    this._showcaseUserTouching = false;
  },

  ensureAquariumRect(cb) {
    const query = wx.createSelectorQuery().in(this);
    query.select("#aquariumContainer").boundingClientRect((rect) => {
      if (rect && rect.width && rect.height) {
        this._aquariumRect = rect;
        cb && cb(rect);
        return;
      }
      try {
        const info = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
        const fallback = { left: 16, top: 0, width: Math.max(260, Number(info.windowWidth || 360) - 40), height: 210 };
        this._aquariumRect = fallback;
        cb && cb(fallback);
      } catch (e) {
        const fallback = { left: 16, top: 0, width: 320, height: 210 };
        this._aquariumRect = fallback;
        cb && cb(fallback);
      }
    }).exec();
  },

  initAquariumEggs(sourceSlots) {
    this.stopAquariumPhysics();
    const src = Array.isArray(sourceSlots) ? sourceSlots : [];
    if (!src.length) {
      this._aquariumEggs = [];
      this.setData({ aquariumEggs: [] });
      return;
    }
    wx.nextTick(() => {
      this.ensureAquariumRect((rect) => {
        const size = 44;
        const radius = size / 2;
        const eggs = src.map((item, idx) => {
          let x = radius + 12 + (idx % 3) * (radius * 2 + 14);
          let y = radius + 18 + Math.floor(idx / 3) * (radius * 2 + 8);
          x = Math.min(rect.width - radius - 10, x);
          y = Math.min(rect.height - radius - 10, y);
          return {
            id: String(item.slot_index),
            slot_index: item.slot_index,
            mascot_id: item.mascot_id,
            emoji: String(item && item.emoji || "").trim() || getMascotEmoji(item && item.mascot_id),
            posterUrl2d: item.posterUrl2d,
            ui_state: item.ui_state,
            x,
            y,
            vx: (Math.random() - 0.5) * 1.2,
            vy: (Math.random() - 0.5) * 1.2,
            r: radius,
            size,
            z: idx + 1,
          };
        });
        this._aquariumEggs = eggs;
        this.syncAquariumEggsToView();
        this.startAquariumPhysics();
      });
    });
  },

  syncAquariumEggsToView() {
    const list = Array.isArray(this._aquariumEggs) ? this._aquariumEggs : [];
    this.setData({
      aquariumEggs: list.map((egg) => ({
        id: egg.id,
        slot_index: egg.slot_index,
        emoji: egg.emoji,
        posterUrl2d: egg.posterUrl2d,
        ui_state: egg.ui_state,
        mascot_id: egg.mascot_id,
        style: `left:${(egg.x - egg.r).toFixed(1)}px;top:${(egg.y - egg.r).toFixed(1)}px;width:${egg.size}px;height:${egg.size * 1.2}px;z-index:${egg.z};`,
      })),
    });
  },

  startAquariumPhysics() {
    if (this._aquariumTick) return;
    this._aquariumTick = setInterval(() => {
      this.stepAquariumPhysics();
    }, 16);
  },

  stopAquariumPhysics() {
    if (this._aquariumTick) {
      clearInterval(this._aquariumTick);
      this._aquariumTick = null;
    }
    this._draggingEgg = null;
  },

  stepAquariumPhysics() {
    const eggs = this._aquariumEggs;
    const rect = this._aquariumRect;
    if (!eggs || !eggs.length || !rect) return;
    const damping = 0.992;
    const gravity = 0.08;
    const restitution = 0.8;
    const dragId = this._draggingEgg && this._draggingEgg.id;

    eggs.forEach((egg) => {
      if (egg.id === dragId) return;
      egg.vy += gravity;
      egg.vx *= damping;
      egg.vy *= damping;
      egg.x += egg.vx;
      egg.y += egg.vy;

      if (egg.x - egg.r < 0) {
        egg.x = egg.r;
        egg.vx = Math.abs(egg.vx) * restitution;
      } else if (egg.x + egg.r > rect.width) {
        egg.x = rect.width - egg.r;
        egg.vx = -Math.abs(egg.vx) * restitution;
      }
      if (egg.y - egg.r < 0) {
        egg.y = egg.r;
        egg.vy = Math.abs(egg.vy) * restitution;
      } else if (egg.y + egg.r > rect.height) {
        egg.y = rect.height - egg.r;
        egg.vy = -Math.abs(egg.vy) * restitution;
      }
    });

    for (let i = 0; i < eggs.length; i++) {
      for (let j = i + 1; j < eggs.length; j++) {
        const a = eggs[i];
        const b = eggs[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.0001;
        const minDist = a.r + b.r - 3;
        if (dist >= minDist) continue;
        const nx = dx / dist;
        const ny = dy / dist;
        const overlap = minDist - dist;
        const aDragging = a.id === dragId;
        const bDragging = b.id === dragId;

        if (aDragging && !bDragging) {
          b.x += nx * overlap;
          b.y += ny * overlap;
        } else if (!aDragging && bDragging) {
          a.x -= nx * overlap;
          a.y -= ny * overlap;
        } else {
          a.x -= nx * overlap * 0.5;
          a.y -= ny * overlap * 0.5;
          b.x += nx * overlap * 0.5;
          b.y += ny * overlap * 0.5;
        }

        const rvx = b.vx - a.vx;
        const rvy = b.vy - a.vy;
        const velAlongNormal = rvx * nx + rvy * ny;
        if (velAlongNormal > 0) continue;
        const impulse = -(1 + 0.75) * velAlongNormal / 2;
        if (!aDragging) {
          a.vx -= impulse * nx;
          a.vy -= impulse * ny;
        }
        if (!bDragging) {
          b.vx += impulse * nx;
          b.vy += impulse * ny;
        }
      }
    }
    this.syncAquariumEggsToView();
  },

  onAquariumEggTouchStart(e) {
    const id = String(e && e.currentTarget && e.currentTarget.dataset ? e.currentTarget.dataset.id : "");
    if (!id) return;
    const t = e && e.touches && e.touches[0] ? e.touches[0] : null;
    if (!t) return;
    const idx = this._aquariumEggs.findIndex((egg) => egg.id === id);
    if (idx < 0) return;
    const topZ = this._aquariumEggs.reduce((m, egg) => Math.max(m, Number(egg.z || 0)), 0) + 1;
    this._aquariumEggs[idx].z = topZ;
    this._draggingEgg = {
      id,
      lastX: Number(t.pageX || t.clientX || 0),
      lastY: Number(t.pageY || t.clientY || 0),
      lastTs: Date.now(),
      vx: 0,
      vy: 0,
    };
    this.syncAquariumEggsToView();
  },

  onAquariumTouchMove(e) {
    if (!this._draggingEgg) return;
    const t = e && e.touches && e.touches[0] ? e.touches[0] : null;
    if (!t || !this._aquariumRect) return;
    const px = Number(t.pageX || t.clientX || 0);
    const py = Number(t.pageY || t.clientY || 0);
    const drag = this._draggingEgg;
    const idx = this._aquariumEggs.findIndex((egg) => egg.id === drag.id);
    if (idx < 0) return;
    const egg = this._aquariumEggs[idx];
    const now = Date.now();
    const dt = Math.max(8, now - drag.lastTs);
    const localX = px - this._aquariumRect.left;
    const localY = py - this._aquariumRect.top;
    egg.x = Math.max(egg.r, Math.min(this._aquariumRect.width - egg.r, localX));
    egg.y = Math.max(egg.r, Math.min(this._aquariumRect.height - egg.r, localY));
    drag.vx = ((px - drag.lastX) / dt) * 6;
    drag.vy = ((py - drag.lastY) / dt) * 6;
    drag.lastX = px;
    drag.lastY = py;
    drag.lastTs = now;
    this.syncAquariumEggsToView();
  },

  onAquariumTouchEnd() {
    if (!this._draggingEgg) return;
    const drag = this._draggingEgg;
    const idx = this._aquariumEggs.findIndex((egg) => egg.id === drag.id);
    if (idx >= 0) {
      this._aquariumEggs[idx].vx = drag.vx;
      this._aquariumEggs[idx].vy = drag.vy;
    }
    this._draggingEgg = null;
  },
});

