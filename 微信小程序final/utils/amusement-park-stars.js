/**
 * 游乐园（Tab「玩」）四项任务：里程碑星星，按自然日重置。
 * 完成 1/2/3/4 个不同任务时，当日从本模块累计获得 1 / 3 / 5 / 10 颗星（增量发放）。
 */

const TASK_IDS = ['speaker', 'color', 'companion', 'petEggGarden'];

/** 完成 n 个任务时，当日本模块已累计获得的星星总数（下标即 n） */
const MILESTONE_TOTAL = [0, 1, 3, 5, 10];

function dateKey() {
  const d = new Date();
  const m = d.getMonth() + 1;
  const day = d.getDate();
  const mm = m < 10 ? `0${m}` : `${m}`;
  const dd = day < 10 ? `0${day}` : `${day}`;
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function storageKey() {
  return `amusementParkTasks.${dateKey()}`;
}

function readDoneList() {
  const key = storageKey();
  try {
    const raw = wx.getStorageSync(key);
    const arr = Array.isArray(raw) ? raw : [];
    const filtered = arr.map((x) => String(x || '').trim()).filter((id) => TASK_IDS.includes(id));
    return { key, list: [...new Set(filtered)] };
  } catch (e) {
    return { key, list: [] };
  }
}

function getAmusementParkProgress() {
  const { list } = readDoneList();
  const count = Math.min(4, list.length);
  return {
    doneIds: list,
    count,
    milestoneStarsEarnedToday: MILESTONE_TOTAL[count],
    nextMilestoneTotal: count < 4 ? MILESTONE_TOTAL[count + 1] : MILESTONE_TOTAL[4],
    allDone: count >= 4,
    ruleLine: '完成 1 项 1⭐ · 2 项共 3⭐ · 3 项共 5⭐ · 4 项共 10⭐',
  };
}

/**
 * 标记某游乐园任务当日已完成，并按里程碑差额发星。
 * @returns {{ delta: number, count: number, total: number, isNew: boolean }}
 */
function reportAmusementParkTaskDone(app, taskId, options) {
  const silent = options && options.silent;
  const id = String(taskId || '').trim();
  if (!TASK_IDS.includes(id) || !app || typeof app.addStars !== 'function') {
    const p = getAmusementParkProgress();
    return { delta: 0, count: p.count, total: MILESTONE_TOTAL[p.count], isNew: false };
  }
  const { key, list } = readDoneList();
  if (list.includes(id)) {
    const c = Math.min(4, list.length);
    return { delta: 0, count: c, total: MILESTONE_TOTAL[c], isNew: false };
  }
  const oldCount = list.length;
  const newList = list.concat([id]);
  const newCount = Math.min(4, newList.length);
  const delta = MILESTONE_TOTAL[newCount] - MILESTONE_TOTAL[oldCount];
  try {
    wx.setStorageSync(key, newList);
  } catch (e) {}
  if (delta > 0) {
    app.addStars(delta);
    if (!silent) {
      wx.showToast({
        title: `游乐园 +${delta}⭐（今日累计 ${MILESTONE_TOTAL[newCount]}⭐）`,
        icon: 'none',
        duration: 2200,
      });
    }
  }
  return { delta, count: newCount, total: MILESTONE_TOTAL[newCount], isNew: true };
}

function buildAmusementParkHint(progress) {
  const p = progress || getAmusementParkProgress();
  if (p.allDone) return '今日四项已全部完成，本页共累计 10⭐';
  const remain = 4 - p.count;
  const next = p.nextMilestoneTotal;
  return `还差 ${remain} 项，完成后今日本页累计可达 ${next}⭐`;
}

module.exports = {
  TASK_IDS,
  MILESTONE_TOTAL,
  getAmusementParkProgress,
  reportAmusementParkTaskDone,
  buildAmusementParkHint,
};
