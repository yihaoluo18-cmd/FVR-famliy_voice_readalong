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

function enrichSlotsWithPosters(slots) {
  const list = Array.isArray(slots) ? slots : [];
  const personaBgMap = {
    default: "rgba(250, 204, 21, 0.16)", // 柴犬淡黄色
    cute_fox: "rgba(236, 72, 153, 0.14)", // 狐狸淡粉色
    cute_dino: "rgba(34, 197, 94, 0.14)", // 恐龙淡绿色
    cute_cat: "rgba(59, 130, 246, 0.14)", // 猫淡蓝色
    cute_bunny: "rgba(147, 197, 253, 0.14)", // 兔子淡天蓝
    cute_squirrel: "rgba(245, 158, 11, 0.14)", // 松鼠淡橘金
    cute_chick: "rgba(251, 191, 36, 0.14)", // 小鸡淡金黄
    cute_panda: "rgba(232, 121, 169, 0.12)", // 熊猫淡粉
    cute_koala: "rgba(20, 184, 166, 0.12)", // 考拉淡青
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

    if (slot.ui_state !== "claimed") return { ...slot, bgColor };

    const pet = mid ? getPetById(mid) : null;
    if (!pet) return { ...slot, bgColor };

    const eggActive = !!slot.egg_model_active;
    const tier = Number(slot.display_form_tier) || 1;

    const posterRel = eggActive ? getStaticEggPosterUrl(pet) : getFormTierPosterUrl(pet, tier);
    const posterUrl2d = resolvePosterUrl(posterRel);
    return { ...slot, bgColor, posterUrl2d };
  });
}

Component({
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
  },

  pageLifetimes: {
    show() {
      this.loadState();
    },
  },

  lifetimes: {
    attached() {
      this.loadState();
    },
  },

  methods: {
    loadState() {
      this.setData({ loading: true });
      requestEggState()
        .then((data) => {
          const slots = enrichSlotsWithPosters(Array.isArray(data.slots) ? data.slots : []);
          const unl = data.unlocked_mascot_ids || [];
          this.setData({
            slots,
            unlocked_mascot_ids: unl,
            has_ready_to_claim: !!data.has_ready_to_claim,
            read_lifetime: data.read_lifetime || 0,
            checkin_month_total: data.checkin_month_total || 0,
            loading: false,
            hintLine: `本月已签到 ${data.checkin_month_total || 0} 天 · 阅读完成 ${data.read_lifetime || 0} 本`,
          });
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
          const slots = enrichSlotsWithPosters(Array.isArray(data.slots) ? data.slots : []);
          this.setData({
            slots,
            unlocked_mascot_ids: data.unlocked_mascot_ids || [],
            has_ready_to_claim: !!data.has_ready_to_claim,
            showUnlockOverlay: false,
          });
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
  },
});

