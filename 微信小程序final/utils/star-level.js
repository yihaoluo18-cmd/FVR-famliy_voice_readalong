/**
 * 星星与等级：共 10 级，累计星星达到阈值升级。
 * 星星来源：每日签到、游戏/互动完成、绘本读完、阅读时长（按日折算，有上限）。
 */

// 达到 Lv.1 … Lv.10 所需的累计星星（Lv.1 从 0 起）
const LEVEL_THRESHOLDS = [0, 45, 110, 200, 320, 480, 690, 950, 1280, 1700];

const LEVEL_META = [
  { title: '萌芽读者', icon: '📖' },
  { title: '故事新星', icon: '🌱' },
  { title: '探索小书虫', icon: '🔍' },
  { title: '阅读小达人', icon: '⭐' },
  { title: '想象大师', icon: '🎨' },
  { title: '绘本冒险家', icon: '🗺️' },
  { title: '博学者', icon: '📚' },
  { title: '故事大师', icon: '🏆' },
  { title: '传奇讲述者', icon: '👑' },
  { title: '星空阅读家', icon: '✨' },
];

/** 各来源单次/规则奖励（与产品说明对齐，可按需微调数字） */
const STAR_REWARDS = {
  CHECKIN_DAILY: 2,
  READ_BOOK_COMPLETE: 5,
  /** 每满多少分钟阅读时长折算 1 颗星 */
  READ_MINUTES_PER_STAR: 5,
  /** 每日通过「阅读时长」最多获得的星星数 */
  READ_DURATION_DAILY_CAP: 8,
};

const MAX_LEVEL = LEVEL_THRESHOLDS.length;

function calculateLevel(stars) {
  const n = Math.max(0, Number(stars) || 0);
  let level = 1;
  for (let L = MAX_LEVEL; L >= 1; L -= 1) {
    if (n >= LEVEL_THRESHOLDS[L - 1]) {
      level = L;
      break;
    }
  }
  const meta = LEVEL_META[level - 1] || LEVEL_META[0];
  if (level >= MAX_LEVEL) {
    return {
      level,
      title: meta.title,
      icon: meta.icon,
      starsToNextLevel: 0,
      hasNextLevel: false,
      progressPercent: 100,
    };
  }
  const curMin = LEVEL_THRESHOLDS[level - 1];
  const nextMin = LEVEL_THRESHOLDS[level];
  const span = Math.max(1, nextMin - curMin);
  const pct = Math.min(100, Math.max(0, ((n - curMin) / span) * 100));
  return {
    level,
    title: meta.title,
    icon: meta.icon,
    starsToNextLevel: Math.max(0, nextMin - n),
    hasNextLevel: true,
    progressPercent: Math.round(pct),
  };
}

/**
 * 根据当日累计阅读分钟数，按规则补发「时长」星星（与已发数量对齐，可多次调用）。
 * @param {string} dateKey 与 read 页 _dateKey() 一致的 YYYY-MM-DD
 */
function awardReadingDurationStars(app, dateKey) {
  if (!app || typeof app.addStars !== 'function' || !dateKey) return;
  const totalMin = Number(wx.getStorageSync(`readingMinutes.${dateKey}`) || 0) || 0;
  const eligible = Math.min(
    STAR_REWARDS.READ_DURATION_DAILY_CAP,
    Math.floor(totalMin / Math.max(1, STAR_REWARDS.READ_MINUTES_PER_STAR))
  );
  const awardedKey = `readDurationStarsAwarded.${dateKey}`;
  const prev = Number(wx.getStorageSync(awardedKey) || 0) || 0;
  const delta = eligible - prev;
  if (delta <= 0) return;
  try {
    app.addStars(delta);
    wx.setStorageSync(awardedKey, eligible);
  } catch (e) {}
}

module.exports = {
  LEVEL_THRESHOLDS,
  LEVEL_META,
  MAX_LEVEL,
  STAR_REWARDS,
  calculateLevel,
  awardReadingDurationStars,
};
