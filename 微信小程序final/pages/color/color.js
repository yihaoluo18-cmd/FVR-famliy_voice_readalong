const app = getApp();

Page({
  data: {
    // API 配置
    apiBaseUrl: '',
    
    // 页面模式: 'list'（列表），'coloring'（涂色中）
    mode: 'list',
    // 列表页子模式：填色训练 / 小小画室
    listMode: 'train', // train | studio
    
    // 涂色任务列表
    sketchList: [],
    currentSketch: null,
    
    // 图片加载（仅线稿）
    lineArtUrl: '',
    lineArtDisplayUrl: '',
    forceImageFallback: false,
    
    // 颜色选择
    colors: [
      "#FF6B6B", "#4ECDC4", "#FFE66D", "#A8E6CF", 
      "#FF8B94", "#C06C84", "#355C7D", "#F8B195",
      "#FFB3D9", "#FBBF24", "#34D399", "#60A5FA"
    ],
    selectedColor: "#FF6B6B",
    recommendedColors: [],
    
    // 交互状态
    hasColored: false,
    sparkles: [],
    showConfetti: false,
    selectedRegion: null,
    
    // Canvas 相关
    canvasReady: false,
    canvasWidth: 0,
    canvasHeight: 0,
    canvasLeft: 0,
    canvasTop: 0,
    
    // 填涂历史（用于撤销）
    fillHistory: [],
    
    // AI 评价
    showScore: false,
    aiScore: 0,
    fullStars: 0,
    evalResult: null,
    evaluating: false,
    // 评分提示词：由前端内置，不暴露给用户编辑
    // 注意：后端 readalong_api 已对 eval_mode=coloring_evaluation 做了图片评分分支，
    // 这里仍传 expected_text 作为提示词，便于后端记录/回归对齐。
    _internalColoringEvalPrompt: `请评价这张儿童涂色作品并给出总分(0-100整数)+建议。要求：1句鼓励 + 2-4条可执行建议，孩子能懂，语气温暖。`,
    
    // 保存选项
    showSaveDialog: false,
    saveToCloud: true,
    saveResult: {
      cloudWorkId: '',
      cloudStatus: '',
      localAlbumStatus: '',
      localRecordPath: ''
    },

    // 完成预览弹窗（导出后展示，不立刻重置画板）
    showFinishModal: false,
    finishPreviewPath: '',
    finishPreviewLoading: false,
    lastExportPngPath: '',

    // 参考答案展示
    showReferenceModal: false,
    referenceAnswerUrl: '',

    // （已删除调试展示内容：tap 坐标/后端摘要/闭合区域测试）

    // 全局填色偏移（单位：像素），用于微调“应该上色的区域”相对底图的位置
    regionShiftX: 0,
    regionShiftY: 0,

    // 线稿展示：默认用 baseCanvas 作为可见层（保证与像素读取完全同源）
    showBaseCanvasLineArt: false,

    // 题库选题（按种类/按难度）
    bankView: 'category', // 'category' | 'difficulty'
    bankCategoryGroups: [],
    bankDifficultyGroups: [],
    // 题目进度（按当前 bankView 的顺序拉平成一列）
    bankFlatItems: [],
    bankCurrentIndex: 0,
    bankCurrentItem: null,
    bankProgressPercent: 0,
    bankTotalQuestions: 0,
    // 小缩略图条：只展示当前附近少量题，避免拖动复杂
    bankThumbItems: [],

    // 填色进度（按像素）
    coloringProgressPercent: 0,
    progressThumbLeftPercent: 0,
    coloringProgressFilledPixels: 0,
    // 进度条滑块上的小图标（按题目：水果/动物等）
    progressMascot: '🎨'
    ,

    // 小小画室：已完成作品展示
    studioWorks: [],
    studioFeatured: [],
    studioRackRenderItems: [],
    studioLeftWorks: [],
    studioRightWorks: [],
    rackScrollLeft: 0,
    rackScrollWithAnimation: true,
    rackFloatingPaused: false,
    showStudioPreview: false,
    studioPreviewWork: null,
  },

  // 题库分类与难度（按 paint_basement 文件名编号）
  // 用于前端展示：种类区分 + 难易程度区分
  _BANK_META_BY_NUM: {
    1: { category: '陆地动物/家禽', difficulty: '中等' },
    2: { category: '水果', difficulty: '中等' },
    3: { category: '海洋动物', difficulty: '简单' },
    4: { category: '陆地动物/家禽', difficulty: '中等' },
    5: { category: '海洋动物', difficulty: '困难' },
    6: { category: '海洋动物', difficulty: '困难' },
    7: { category: '陆地动物/家禽', difficulty: '中等' },
    8: { category: '陆地动物/家禽', difficulty: '简单' },
    9: { category: '陆地动物/家禽', difficulty: '中等' },
    10: { category: '陆地动物/家禽', difficulty: '中等' },
    11: { category: '陆地动物/家禽', difficulty: '简单' },
    12: { category: '甜点/主食', difficulty: '简单' },
    13: { category: '水果', difficulty: '简单' },
    14: { category: '水果', difficulty: '困难' },
    15: { category: '水果', difficulty: '困难' },
    16: { category: '水果', difficulty: '困难' },
    17: { category: '蔬菜/食材', difficulty: '困难' },
    18: { category: '蔬菜/食材', difficulty: '困难' },
    19: { category: '蔬菜/食材', difficulty: '困难' },
    20: { category: '昆虫', difficulty: '简单' },
    21: { category: '蔬菜/食材', difficulty: '简单' },
    22: { category: '甜点/主食', difficulty: '简单' },
    23: { category: '甜点/主食', difficulty: '困难' },
    24: { category: '自然/玩具', difficulty: '中等' },
    25: { category: '甜点/主食', difficulty: '简单' },
    26: { category: '水果', difficulty: '困难' },
    27: { category: '水果', difficulty: '中等' },
    28: { category: '物品', difficulty: '简单' },
    29: { category: '自然/玩具', difficulty: '中等' },
    30: { category: '物品', difficulty: '中等' }
  },

  // 每道题目“形象”推荐色（最多 5 个，供儿童快速涂色）
  // 数字对应 paint_basement/xxx.jpg 的编号：1..30
  _RECOMMENDED_COLORS_BY_NUM: {
    1: ['#EC9813', '#902C00', '#5A1C01', '#956820', '#CA8B28'], // 小狗（来自参考答案）
    2: ['#EF0C0C', '#37F500', '#3B51FD', '#30220F', '#A01C1C'], // 苹果（来自参考答案）
    3: ['#53A1E9', '#DCFEFD', '#FCB1FE', '#36495A', '#AEBFC1'], // 水母（来自参考答案）
    4: ['#F3C91C', '#F4F1E8', '#43380A', '#A48C26'], // 企鹅（来自参考答案，颜色较少）
    5: ['#F0A63A', '#EE400A', '#EE6F3C', '#3B1D0E', '#93512C'], // 螃蟹（来自参考答案）
    6: ['#3B82F6', '#06B6D4', '#A5B4FC', '#F8FAFC', '#0EA5E9'], // 鲸鱼
    7: ['#C4A484', '#F5F5DC', '#16A34A', '#A16207', '#111827'], // 蜗牛
    8: ['#A16207', '#F5F3E8', '#F59E0B', '#111827', '#F472B6'], // 刺猬
    9: ['#16A34A', '#14532D', '#FBBF24', '#B45309', '#111827'], // 鳄鱼
    10: ['#F8FAFC', '#9CA3AF', '#111827', '#F472B6', '#60A5FA'], // 绵羊
    11: ['#FBBF24', '#F97316', '#F8FAFC', '#22C55E', '#B45309'], // 鸭子
    12: ['#EC4899', '#60A5FA', '#FBBF24', '#F8FAFC', '#A16207'], // 冰激凌
    13: ['#F59E0B', '#FBBF24', '#F97316', '#22C55E', '#F8FAFC'], // 芒果
    14: ['#22C55E', '#84CC16', '#F8FAFC', '#B45309', '#111827'], // 猕猴桃
    15: ['#EF4444', '#F472B6', '#22C55E', '#B45309', '#F8FAFC'], // 樱桃
    16: ['#22C55E', '#16A34A', '#EF4444', '#F8FAFC', '#111827'], // 西瓜
    17: ['#F97316', '#F59E0B', '#16A34A', '#B45309', '#FDE68A'], // 南瓜
    18: ['#8B5CF6', '#6D28D9', '#22C55E', '#C4B5FD', '#F8FAFC'], // 茄子
    19: ['#EF4444', '#22C55E', '#F59E0B', '#F8FAFC', '#B45309'], // 番茄
    20: ['#3B82F6', '#F43F5E', '#A78BFA', '#FBBF24', '#10B981'], // 蝴蝶
    21: ['#EF4444', '#22C55E', '#F59E0B', '#F8FAFC', '#14532D'], // 辣椒
    22: ['#FBBF24', '#F59E0B', '#F8FAFC', '#22C55E', '#B45309'], // 荷包蛋
    23: ['#EC4899', '#A78BFA', '#FBBF24', '#F8FAFC', '#6B3B27'], // 甜甜圈
    24: ['#EF4444', '#F97316', '#FBBF24', '#22C55E', '#3B82F6'], // 彩虹
    25: ['#B45309', '#FBBF24', '#F8FAFC', '#F97316', '#111827'], // 面包
    26: ['#3B82F6', '#1D4ED8', '#A78BFA', '#F8FAFC', '#22C55E'], // 蓝莓
    27: ['#F97316', '#FBBF24', '#F472B6', '#F8FAFC', '#22C55E'], // 桃子
    28: ['#60A5FA', '#F59E0B', '#22C55E', '#F8FAFC', '#111827'], // 帽子
    29: ['#60A5FA', '#34D399', '#F59E0B', '#F97316', '#B45309'], // 风车
    30: ['#FBBF24', '#B45309', '#9CA3AF', '#16A34A', '#111827'], // 铅笔
  },

  _BANK_CATEGORY_ORDER: [
    '陆地动物/家禽',
    '海洋动物',
    '水果',
    '蔬菜/食材',
    '甜点/主食',
    '昆虫',
    '自然/玩具',
    '物品',
    '其他'
  ],

  _BANK_DIFF_ORDER: ['简单', '中等', '困难'],

  _BANK_CATEGORY_ICON: {
    '陆地动物/家禽': '🐾',
    '海洋动物': '🐳',
    '水果': '🍎',
    '蔬菜/食材': '🥕',
    '甜点/主食': '🍩',
    '昆虫': '🦋',
    '自然/玩具': '🌈',
    '物品': '🎒',
    '其他': '✨'
  },

  _BANK_DIFF_ICON: {
    '简单': '😊',
    '中等': '😃',
    '困难': '😣'
  },

  // 涂色进度条「滑块」上的形象（与 paint_basement 编号一致，1..30）
  _PROGRESS_THUMB_BY_NUM: {
    1: '🐕', 2: '🍎', 3: '🪼', 4: '🐧', 5: '🦀',
    6: '🐋', 7: '🐌', 8: '🦔', 9: '🐊', 10: '🐑',
    11: '🦆', 12: '🍦', 13: '🥭', 14: '🥝', 15: '🍒',
    16: '🍉', 17: '🎃', 18: '🍆', 19: '🍅', 20: '🦋',
    21: '🌶️', 22: '🍳', 23: '🍩', 24: '🌈', 25: '🍞',
    26: '🫐', 27: '🍑', 28: '🧢', 29: '🪁', 30: '✏️'
  },

  onLoad() {
    try {
      const sys = wx.getSystemInfoSync();
      const w = Number(sys && sys.windowWidth) || 375;
      this._rpx2px = w / 750;
    } catch (e) {
      this._rpx2px = 0.5;
    }
    const base = (app && app.globalData && app.globalData.apiBaseUrl) || 'http://127.0.0.1:9880';
    this.setData({ apiBaseUrl: base });
    
    // 加载涂色任务列表
    this._loadSketchList();
    // 加载画室作品（本地记录）
    this._loadStudioWorks();

    // 运行时缓存（不放 setData，减少渲染）
    this._paintPixels = null;
    this._lastTapTs = 0;
    this._baseDrawRetry = 0;

  },

  onShow() {
    if (this.data.mode === 'list') {
      // 列表模式，刷新列表
      this._loadSketchList();
      this._loadStudioWorks();
      this._startRackAutoScroll();
    }
  },

  onHide() {
    this._stopRackAutoScroll();
  },

  switchListMode(e) {
    const mode = (e && e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.mode) || 'train';
    if (mode !== 'train' && mode !== 'studio') return;
    if (mode === this.data.listMode) return;
    this.setData({ listMode: mode }, () => {
      if (mode === 'studio') this._loadStudioWorks();
    });
  },

  _getUserId() {
    try {
      const app = getApp && getApp();
      const g = app && app.globalData ? app.globalData : {};
      const fromGlobal = (g.user_id || g.userId || g.openid || g.openId || '').toString().trim();
      if (fromGlobal) return fromGlobal;
    } catch (e) {}
    try {
      const fromStorage = (wx.getStorageSync('user_id') || wx.getStorageSync('openid') || wx.getStorageSync('openId') || '').toString().trim();
      if (fromStorage) return fromStorage;
    } catch (e) {}
    return 'guest';
  },

  _requireProgress100(actionHint = '操作') {
    const p = Number(this.data.coloringProgressPercent || 0) || 0;
    if (p >= 100) return true;
    wx.showToast({ title: `还差一点点，涂色到100%才能${actionHint}哦`, icon: 'none' });
    return false;
  },

  _loadStudioWorks() {
    const userId = this._getUserId();
    const url = `${this.data.apiBaseUrl}/coloring/get_user_works/${encodeURIComponent(userId)}?limit=50`;

    wx.request({
      url,
      method: 'GET',
      timeout: 15000,
      success: (res) => {
        if (res && res.statusCode === 200 && res.data && res.data.ok) {
          const works = Array.isArray(res.data.works) ? res.data.works : [];
          const normalized = works
            .map((w) => {
              const workId = String((w && (w.work_id || w.id)) || '');
              const createdAt = String((w && w.created_at) || '');
              const ts = createdAt ? Date.parse(createdAt) : NaN;
              return {
                id: workId,
                title: String((w && w.title) || '作品'),
                timestamp: Number.isFinite(ts) ? ts : Date.now(),
                image_path: this._toAbsoluteUrl(String((w && (w.image_url || w.image_path)) || '')),
                evaluation: (w && w.evaluation) || null,
                sketch_id: String((w && w.sketch_id) || ''),
              };
            })
            .filter((w) => w.id && w.image_path);

          normalized.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
          this._applyStudioLayout(normalized);
          return;
        }
        this._loadStudioWorksFromLocal();
      },
      fail: () => this._loadStudioWorksFromLocal(),
    });
  },

  _loadStudioWorksFromLocal() {
    let works = [];
    try {
      works = wx.getStorageSync('coloringWorks') || [];
    } catch (e) {
      works = [];
    }
    if (!Array.isArray(works)) works = [];

    const normalized = works
      .map((w) => ({
        id: String((w && w.id) || ''),
        title: String((w && w.title) || (w && w.sketch_title) || '作品'),
        timestamp: Number((w && w.timestamp) || 0) || 0,
        image_path: String((w && (w.image_path || w.imagePath || w.path)) || ''),
        evaluation: (w && w.evaluation) || null,
        sketch_id: String((w && w.sketch_id) || ''),
      }))
      .filter((w) => w.image_path);

    normalized.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
    this._applyStudioLayout(normalized);
  },

  _estimateFrameHeight(type = 'square') {
    if (type === 'portrait') return 252;
    if (type === 'wide') return 174;
    return 210;
  },

  _applyStudioLayout(normalizedWorks) {
    const works = normalizedWorks || [];
    const left = [];
    const right = [];

    // 按“行”交替：每行一横一纵，且下一行左右对调
    for (let i = 0, row = 0; i < works.length; i += 2, row += 1) {
      const a = works[i];
      const b = works[i + 1];
      const evenRow = row % 2 === 0;
      const leftType = evenRow ? 'wide' : 'portrait';
      const rightType = evenRow ? 'portrait' : 'wide';

      if (a) left.push({ ...a, frameType: leftType, frameClass: `mini ${leftType}` });
      if (b) right.push({ ...b, frameType: rightType, frameClass: `mini ${rightType}` });
    }

    // 合并后的 studioWorks 继续保留，供预览/删除按 id 查找
    const merged = [...left, ...right];
    const featured = merged.slice(0, 6);
    const rackRenderItems = this._buildRackRenderItems(featured);

    this.setData({
      studioWorks: merged,
      studioFeatured: featured,
      studioRackRenderItems: rackRenderItems,
      studioLeftWorks: left,
      studioRightWorks: right,
    }, () => {
      this._resetRackLoopPosition();
      this._startRackAutoScroll();
    });
  },

  _buildRackRenderItems(items) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) return [];
    const triple = [...list, ...list, ...list];
    return triple.map((it, i) => ({ ...it, __k: `${String(it.id || 'w')}_${i}` }));
  },

  _rackBaseCount() {
    return Math.max(0, Array.isArray(this.data.studioFeatured) ? this.data.studioFeatured.length : 0);
  },

  _rackItemStepPx() {
    const rpx2px = Number(this._rpx2px || 0) || 0.5;
    // 对应 wxss: .rack-item width 220rpx + margin-right 14rpx
    return Math.max(1, Math.round((220 + 14) * rpx2px));
  },

  _rackScrollOffsetPx() {
    // rack-scroll 无额外左内边距
    return 0;
  },

  _rackSegmentWidthPx() {
    return Math.max(0, this._rackBaseCount() * this._rackItemStepPx());
  },

  _resetRackLoopPosition() {
    const seg = this._rackSegmentWidthPx();
    if (seg <= 0) return;
    const off = this._rackScrollOffsetPx();
    const start = off + seg;
    this._rackScrollLeft = start;
    this.setData({ rackScrollLeft: start });
  },

  _ensureRackLoopInMiddle() {
    const seg = this._rackSegmentWidthPx();
    if (seg <= 0) return null;
    const off = this._rackScrollOffsetPx();
    let cur = Number(this._rackScrollLeft || this.data.rackScrollLeft || 0) || 0;
    const min = off + seg;
    const max = off + seg * 2;
    if (cur >= max) cur -= seg;
    if (cur < min) cur += seg;
    this._rackScrollLeft = cur;
    return cur;
  },

  _startRackAutoScroll() {
    this._stopRackAutoScroll();
    const n = this._rackBaseCount();
    if (n <= 2) return;
    if (!Array.isArray(this.data.studioRackRenderItems) || this.data.studioRackRenderItems.length < n * 3) return;
    this._rackAutoTimer = setInterval(() => {
      if (this._rackUserTouching) return;
      const seg = this._rackSegmentWidthPx();
      if (seg <= 0) return;
      const cur0 = Number(this._rackScrollLeft || this.data.rackScrollLeft || 0) || 0;
      const cur = this._ensureRackLoopInMiddle() ?? cur0;
      const next = cur + this._rackItemStepPx();
      const off = this._rackScrollOffsetPx();
      const max = off + seg * 2;
      if (next >= max) {
        const jumped = next - seg;
        this._rackScrollLeft = jumped;
        this.setData({ rackScrollWithAnimation: false, rackScrollLeft: jumped }, () => {
          this.setData({ rackScrollWithAnimation: true });
        });
        return;
      }
      this._rackScrollLeft = next;
      this.setData({ rackScrollLeft: next });
    }, 1800);
  },

  _stopRackAutoScroll() {
    if (this._rackAutoTimer) {
      clearInterval(this._rackAutoTimer);
      this._rackAutoTimer = null;
    }
  },

  onRackScroll(e) {
    const x = Number((e && e.detail && e.detail.scrollLeft) || 0) || 0;
    this._rackScrollLeft = Math.max(0, x);
  },

  onRackTouchStart() {
    this._rackUserTouching = true;
    this.setData({ rackFloatingPaused: true });
    this._stopRackAutoScroll();
  },

  onRackTouchEnd() {
    this._rackUserTouching = false;
    const n = this._rackBaseCount();
    const step = this._rackItemStepPx();
    const seg = this._rackSegmentWidthPx();
    const off = this._rackScrollOffsetPx();
    const cur = Number(this._rackScrollLeft || this.data.rackScrollLeft || 0) || 0;
    if (!n || seg <= 0 || step <= 0) {
      this.setData({ rackFloatingPaused: false }, () => this._startRackAutoScroll());
      return;
    }
    const rawIdx = Math.round((cur - off) / step);
    const k = ((rawIdx % n) + n) % n;
    const target = off + seg + k * step;
    this._rackScrollLeft = target;
    const normalized = this._ensureRackLoopInMiddle() ?? target;
    this.setData({ rackScrollLeft: normalized, rackFloatingPaused: false }, () => this._startRackAutoScroll());
  },

  deleteStudioWork(e) {
    const workId = String(e && e.currentTarget && e.currentTarget.dataset ? (e.currentTarget.dataset.workid || '') : '').trim();
    if (!workId) return;

    wx.showModal({
      title: '删除这幅画吗？',
      content: '删除后无法恢复哦～',
      confirmText: '删除',
      confirmColor: '#ef4444',
      cancelText: '取消',
      success: (r) => {
        if (!r || !r.confirm) return;

        // 优先删除后端（work_* 结构），失败则尝试本地删除
        const url = `${this.data.apiBaseUrl}/coloring/delete_work/${encodeURIComponent(workId)}`;
        wx.request({
          url,
          method: 'DELETE',
          timeout: 15000,
          success: (res) => {
            if (res && res.statusCode === 200 && res.data && res.data.ok) {
              wx.showToast({ title: '已删除', icon: 'success' });
              this._loadStudioWorks();
              return;
            }
            this._deleteStudioWorkLocalFallback(workId);
          },
          fail: () => this._deleteStudioWorkLocalFallback(workId),
        });
      },
    });
  },

  _deleteStudioWorkLocalFallback(workId) {
    let works = [];
    try {
      works = wx.getStorageSync('coloringWorks') || [];
    } catch (e) {
      works = [];
    }
    if (!Array.isArray(works)) works = [];
    const next = works.filter((w) => String((w && w.id) || '') !== workId);
    try {
      wx.setStorageSync('coloringWorks', next);
    } catch (e) {}
    wx.showToast({ title: '已删除(本地)', icon: 'success' });
    this._loadStudioWorksFromLocal();
  },

  openStudioPreview(e) {
    const list = this.data.studioWorks || [];
    const ds = (e && e.currentTarget && e.currentTarget.dataset) || {};
    const workId = String(ds.workid || '').trim();
    let target = null;
    if (workId) {
      target = list.find((w) => String(w.id) === workId) || null;
    } else {
      const idx = Number(ds.index);
      if (Number.isFinite(idx) && idx >= 0 && idx < list.length) target = list[idx];
    }
    if (!target) return;
    this.setData({
      showStudioPreview: true,
      studioPreviewWork: target,
    });
  },

  closeStudioPreview() {
    this.setData({
      showStudioPreview: false,
      studioPreviewWork: null,
    });
  },

  _toAbsoluteUrl(url) {
    if (!url) return '';
    if (/^https?:\/\//i.test(url)) return url;

    const base = (this.data.apiBaseUrl || '').replace(/\/$/, '');
    if (!base) return url;

    return url.startsWith('/') ? `${base}${url}` : `${base}/${url}`;
  },

  _toBundledLineArtPath(rawUrl) {
    // 当前仓库未包含 /assets/coloring/lineart 资源，禁用该“内置路径”兜底，统一走 downloadFile 的 temp 路径。
    // 否则会在开发者工具内触发：Failed to load local image resource /assets/coloring/lineart/*.png
    return '';
  },

  // ═══════════════════════════════════
  //  列表模式：选择涂色项目
  // ═══════════════════════════════════
  
  _loadSketchList() {
    const url = `${this.data.apiBaseUrl}/coloring/get_sketches`;
    
    wx.request({
      url,
      method: 'GET',
      timeout: 15000,
      success: (res) => {
        if (res.statusCode === 200 && res.data.ok) {
          const normalizedItems = (res.data.items || []).map((item) => ({
            ...item,
            lineart_url: this._toAbsoluteUrl(item.lineart_url),
            regionmap_url: this._toAbsoluteUrl(item.regionmap_url),
            bundled_lineart: this._toBundledLineArtPath(item.lineart_url),
            local_thumb: this._toBundledLineArtPath(item.lineart_url) || ''
          }));

          // 先渲染题库结构（避免缩略图下载阻塞导致页面空白）
          const groups = this._buildBankGroups(normalizedItems);
          this.setData({
            sketchList: normalizedItems,
            bankCategoryGroups: groups.categoryGroups,
            bankDifficultyGroups: groups.difficultyGroups
          });
          this._initBankProgress(groups);

          // 再异步补齐缩略图
          this._prefetchListThumbs(normalizedItems);
        } else {
          wx.showToast({ title: '加载任务失败', icon: 'none' });
        }
      },
      fail: (err) => {
        wx.showToast({ title: '网络错误', icon: 'none' });
      }
    });
  },

  _prefetchListThumbs(items) {
    if (!items || !items.length) return;

    const withTimeout = (p, ms = 8000) => new Promise((resolve) => {
      let done = false;
      const timer = setTimeout(() => {
        if (done) return;
        done = true;
        resolve('');
      }, ms);
      Promise.resolve(p)
        .then((v) => {
          if (done) return;
          done = true;
          clearTimeout(timer);
          resolve(v || '');
        })
        .catch(() => {
          if (done) return;
          done = true;
          clearTimeout(timer);
          resolve('');
        });
    });

    const jobs = items.map((item) => {
      if (item.local_thumb) {
        return Promise.resolve(item);
      }
      return withTimeout(this._downloadImage(item.lineart_url), 8000)
        .then((tempPath) => ({ ...item, local_thumb: tempPath || '' }));
    });

    Promise.all(jobs).then((results) => {
      // 题库分组：按种类/按难度展示
      const groups = this._buildBankGroups(results);
      this.setData({
        sketchList: results,
        bankCategoryGroups: groups.categoryGroups,
        bankDifficultyGroups: groups.difficultyGroups
      });
      // 初始化题目进度与当前题目
      this._initBankProgress(groups);
    });
  },

  _extractNumFromSketch(sketch) {
    const pickStrings = [];
    if (sketch && sketch.title) pickStrings.push(String(sketch.title));
    if (sketch && sketch.id) pickStrings.push(String(sketch.id));
    if (sketch && sketch.lineart_url) pickStrings.push(String(sketch.lineart_url));
    if (sketch && sketch.local_thumb) pickStrings.push(String(sketch.local_thumb));

    // 1) 先尝试：从 title/id 开头取数字（例如：'1 dog' / '02 apple'）
    for (const s0 of pickStrings) {
      const s = String(s0 || '');
      const m = s.match(/^\s*(\d{1,2})/);
      if (m && m[1]) return Number(m[1]);
    }

    // 2) 再尝试：从文件名取数字（例如：.../paint_basement/17 南瓜.jpg -> 17）
    for (const s0 of pickStrings) {
      const s = String(s0 || '');
      const noQuery = s.split('?')[0];
      const base = noQuery.split('/').pop() || '';
      const stem = base.replace(/\.[a-z0-9]+$/i, '');
      const m = stem.match(/^\s*(\d{1,2})/);
      if (m && m[1]) return Number(m[1]);
    }

    // 3) 最后尝试：在字符串中找 1-2 位数字 token
    for (const s0 of pickStrings) {
      const s = String(s0 || '');
      const m2 = s.match(/\b(\d{1,2})\b/);
      if (m2 && m2[1]) return Number(m2[1]);
    }

    // 4) 兜底：提取所有数字片段，优先取 1-30
    for (const s0 of pickStrings) {
      const s = String(s0 || '');
      const ms = s.match(/\d{1,3}/g);
      if (ms && ms.length) {
        for (const part of ms) {
          const n = Number(part);
          if (Number.isFinite(n) && n >= 1 && n <= 30) return n;
        }
      }
    }

    return null;
  },

  _attachBankMeta(sketch) {
    const num = this._extractNumFromSketch(sketch);
    const meta = (num != null && this._BANK_META_BY_NUM[num]) ? this._BANK_META_BY_NUM[num] : null;
    const category = meta ? meta.category : '其他';
    const difficulty = meta ? meta.difficulty : '中等';
    const difficultyClass = (difficulty === '简单') ? 'simple'
      : (difficulty === '中等') ? 'medium'
        : (difficulty === '困难') ? 'hard'
          : 'medium';
    const categoryIcon = this._BANK_CATEGORY_ICON[category] || '✨';
    const difficultyIcon = this._BANK_DIFF_ICON[difficulty] || '😊';

    const qid = this._formatQidFromSketch({
      ...sketch,
      metaNum: num
    });

    // 兼容后端字段：把“标签/简介”尽量整理成前端可展示的字段
    let tags = [];
    const tagsRaw = sketch && (sketch.tags || sketch.tag || sketch.labels || sketch.label);
    if (Array.isArray(tagsRaw)) {
      tags = tagsRaw.map((t) => String(t)).filter(Boolean);
    } else if (typeof tagsRaw === 'string') {
      const s = tagsRaw.trim();
      if (s) {
        tags = s.split(/[，,]/).map((t) => t.trim()).filter(Boolean);
      }
    }
    const introRaw = sketch && (sketch.intro || sketch.introduction || sketch.brief || sketch.description);
    const intro = (typeof introRaw === 'string') ? introRaw : (tags.length ? '' : '');
    return {
      ...sketch,
      metaNum: num,
      metaCategory: category,
      metaCategoryIcon: categoryIcon,
      metaDifficulty: difficulty,
      metaDifficultyIcon: difficultyIcon,
      metaDifficultyClass: difficultyClass,
      qid,
      // 用于题库展示
      tags,
      intro
    };
  },

  /** 进度条滑块图标：优先标题关键词，再按题号，再按种类兜底 */
  _getProgressThumb(sketch) {
    const title = String((sketch && sketch.title) || '');
    const keywordPairs = [
      ['猕猴桃', '🥝'], ['苹果', '🍎'], ['水母', '🪼'], ['企鹅', '🐧'], ['螃蟹', '🦀'],
      ['鲸鱼', '🐋'], ['蜗牛', '🐌'], ['刺猬', '🦔'], ['鳄鱼', '🐊'], ['绵羊', '🐑'], ['羊', '🐑'],
      ['鸭子', '🦆'], ['鸭', '🦆'], ['冰激凌', '🍦'], ['冰淇淋', '🍦'], ['芒果', '🥭'],
      ['樱桃', '🍒'], ['西瓜', '🍉'], ['南瓜', '🎃'], ['茄子', '🍆'], ['番茄', '🍅'],
      ['西红柿', '🍅'], ['蝴蝶', '🦋'], ['辣椒', '🌶️'], ['荷包蛋', '🍳'], ['甜甜圈', '🍩'],
      ['彩虹', '🌈'], ['面包', '🍞'], ['蓝莓', '🫐'], ['桃子', '🍑'], ['帽子', '🧢'],
      ['风车', '🪁'], ['铅笔', '✏️'], ['小狗', '🐕'], ['狗', '🐕']
    ];
    for (let i = 0; i < keywordPairs.length; i++) {
      const k = keywordPairs[i][0];
      const em = keywordPairs[i][1];
      if (k && title.includes(k)) return em;
    }
    const num = (sketch && sketch.metaNum != null) ? sketch.metaNum : this._extractNumFromSketch(sketch);
    if (num != null && this._PROGRESS_THUMB_BY_NUM[num]) {
      return this._PROGRESS_THUMB_BY_NUM[num];
    }
    const cat = sketch && sketch.metaCategory;
    if (cat === '水果') return '🍎';
    if (cat === '陆地动物/家禽') return '🐾';
    if (cat === '海洋动物') return '🐠';
    if (cat === '蔬菜/食材') return '🥕';
    if (cat === '甜点/主食') return '🍰';
    if (cat === '昆虫') return '🐛';
    if (cat === '自然/玩具') return '🌟';
    if (cat === '物品') return '🎁';
    return '🎨';
  },

  _buildBankGroups(sketchList) {
    const items = (sketchList || []).map((s) => this._attachBankMeta(s));

    // categoryGroups
    const catMap = {};
    items.forEach((it) => {
      const c = it.metaCategory || '其他';
      (catMap[c] || (catMap[c] = [])).push(it);
    });
    const categoryGroups = [];
    this._BANK_CATEGORY_ORDER.forEach((c) => {
      const arr = catMap[c];
      if (!arr || !arr.length) return;
      arr.sort((a, b) => (a.metaNum || 999) - (b.metaNum || 999));
      categoryGroups.push({
        category: c,
        icon: this._BANK_CATEGORY_ICON[c] || '✨',
        items: arr
      });
    });

    // difficultyGroups
    const diffMap = { 简单: [], 中等: [], 困难: [] };
    items.forEach((it) => {
      const d = it.metaDifficulty || '中等';
      if (!diffMap[d]) diffMap[d] = [];
      diffMap[d].push(it);
    });
    const difficultyGroups = [];
    this._BANK_DIFF_ORDER.forEach((d) => {
      const arr = diffMap[d];
      if (!arr || !arr.length) return;
      arr.sort((a, b) => (a.metaNum || 999) - (b.metaNum || 999));
      difficultyGroups.push({
        difficulty: d,
        icon: this._BANK_DIFF_ICON[d] || '😊',
        items: arr
      });
    });

    return { categoryGroups, difficultyGroups };
  },

  switchBankView(e) {
    const view = e.currentTarget.dataset.view;
    if (view !== 'category' && view !== 'difficulty') return;
    const nextBankView = view;
    const bankFlatItems = this._flattenBankItems(nextBankView, this.data.bankCategoryGroups, this.data.bankDifficultyGroups);
    const nextIndex = 0;
    const nextItem = (bankFlatItems && bankFlatItems.length) ? bankFlatItems[0] : null;
    const total = bankFlatItems ? bankFlatItems.length : 0;
    const bankThumbItems = this._buildBankThumbItems(bankFlatItems, nextIndex);
    this.setData({
      bankView: nextBankView,
      bankFlatItems,
      bankCurrentIndex: nextIndex,
      bankCurrentItem: nextItem,
      bankTotalQuestions: total,
      bankProgressPercent: total ? Math.round(((nextIndex + 1) / total) * 100) : 0,
      bankThumbItems
    });
  },

  _flattenBankItems(view, categoryGroups, difficultyGroups) {
    const catGroups = categoryGroups || [];
    const diffGroups = difficultyGroups || [];
    const out = [];
    if (view === 'category') {
      catGroups.forEach((g) => {
        if (g && Array.isArray(g.items)) out.push(...g.items);
      });
    } else {
      diffGroups.forEach((g) => {
        if (g && Array.isArray(g.items)) out.push(...g.items);
      });
    }
    // 题目条统一按题号顺序展示：1 -> 30
    out.sort((a, b) => {
      const an = Number.isFinite(a && a.metaNum) ? a.metaNum : 9999;
      const bn = Number.isFinite(b && b.metaNum) ? b.metaNum : 9999;
      return an - bn;
    });
    return out;
  },

  _formatQidFromSketch(sketch) {
    // 题库缩略图文案：按序题号 + 名称（如：8 小刺猬）
    const n = (sketch && (sketch.metaNum != null)) ? sketch.metaNum : this._extractNumFromSketch(sketch);
    const pickName = () => {
      const candidates = [];
      if (sketch && sketch.title) candidates.push(String(sketch.title));
      if (sketch && sketch.lineart_url) candidates.push(String(sketch.lineart_url));
      if (sketch && sketch.id) candidates.push(String(sketch.id));
      for (const raw0 of candidates) {
        let raw = String(raw0 || '').trim();
        if (!raw) continue;
        raw = raw.split('?')[0];
        raw = raw.split('/').pop() || raw;
        raw = raw.replace(/\.[a-z0-9]+$/i, '').trim();
        // 去掉开头题号前缀：'8 刺猬' / '08-刺猬' / 'q008 刺猬'
        raw = raw
          .replace(/^\s*q?\d{1,3}\s*[-_.、\s]*/i, '')
          .trim();
        if (raw) return raw;
      }
      return '';
    };
    const name = pickName();
    if (Number.isFinite(n)) {
      return name ? `${n} ${name}` : String(n);
    }
    // 兜底：直接用名称或 id/title
    if (name) return name;
    const fallback = (sketch && (sketch.id || sketch.title)) ? String(sketch.id || sketch.title) : '';
    return fallback ? fallback : '题目';
  },

  _buildBankThumbItems(bankFlatItems, bankCurrentIndex) {
    const list = bankFlatItems || [];
    const total = list.length;
    const idx = Number(bankCurrentIndex);
    if (!total) return [];

    const windowSize = 5;
    const safeIdx = Number.isFinite(idx) ? Math.max(0, Math.min(idx, total - 1)) : 0;
    let start = Math.max(0, safeIdx - 2);
    let end = Math.min(total, start + windowSize);
    start = Math.max(0, end - windowSize);

    const slice = list.slice(start, end);
    return slice.map((it, i) => ({
      thumbIndex: start + i,
      item: it,
      qid: this._formatQidFromSketch(it)
    }));
  },

  _initBankProgress(groups) {
    const bankFlatItems = this._flattenBankItems(this.data.bankView, groups.categoryGroups, groups.difficultyGroups);
    const total = bankFlatItems.length;
    const idx = 0;
    const item = total ? bankFlatItems[0] : null;
    const bankThumbItems = this._buildBankThumbItems(bankFlatItems, idx);
    this.setData({
      bankFlatItems,
      bankCurrentIndex: idx,
      bankCurrentItem: item,
      bankTotalQuestions: total,
      bankProgressPercent: total ? Math.round(((idx + 1) / total) * 100) : 0,
      bankThumbItems
    });
  },

  setBankIndex(e) {
    const index = Number(e.currentTarget.dataset.index);
    if (!Number.isFinite(index)) return;
    const list = this.data.bankFlatItems || [];
    if (!list.length) return;
    const idx = Math.max(0, Math.min(index, list.length - 1));
    const item = list[idx] || null;
    const total = list.length;
    const bankThumbItems = this._buildBankThumbItems(list, idx);
    this.setData({
      bankCurrentIndex: idx,
      bankCurrentItem: item,
      bankProgressPercent: total ? Math.round(((idx + 1) / total) * 100) : 0,
      bankThumbItems
    });
  },

  startColoringFromBank() {
    const sketch = this.data.bankCurrentItem;
    if (!sketch) {
      wx.showToast({ title: '还没有题目', icon: 'none' });
      return;
    }
    // 复用 selectSketch 里的逻辑：需要一个 e.currentTarget.dataset.sketch
    this.selectSketch({ currentTarget: { dataset: { sketch } } });
  },

  selectSketch(e) {
    const sketch = e.currentTarget.dataset.sketch;
    const metaSk = this._attachBankMeta(sketch);
    const progressMascot = this._getProgressThumb(metaSk);
    const lineArtUrl = this._toAbsoluteUrl(sketch.lineart_url);
    const bundledLineArt = sketch.bundled_lineart || this._toBundledLineArtPath(sketch.lineart_url);

    // 答案色：优先使用后端对“答案图”提取后的 palette
    const answerPalette = (sketch && Array.isArray(sketch.palette) && sketch.palette.length) ? sketch.palette : [];
    const palette = answerPalette.length ? answerPalette : this.data.colors;
    const recommendedColors = this._buildRecommendedColors(answerPalette, palette);
    const initialSelectedColor = (recommendedColors && recommendedColors.length)
      ? recommendedColors[0]
      : ((palette && palette.length) ? palette[0] : this.data.selectedColor);

    this.setData({
      currentSketch: sketch,
      mode: 'coloring',
      progressMascot,
      // 小狗/非小狗：统一使用后端/上传的线稿（lineart_url）
      lineArtUrl,
      lineArtDisplayUrl: bundledLineArt || sketch.local_thumb || '',
      forceImageFallback: false,
      // 若后端提供训练色板（≤4色），则覆盖默认色板
      colors: palette,
      recommendedColors,
      // 不点小圆球时，直接填色也应该使用推荐色风格
      selectedColor: initialSelectedColor,
      selectedRegion: { name: '', hint: '请选择一个闭合区域，点击填色' },
      fillHistory: [],
      hasColored: false,
      sparkles: [],
      showReferenceModal: false,
      referenceAnswerUrl: ''
    });

    // 进入涂色页时，不再从后端恢复历史记录，所有填色仅保存在前端会话中。
    this.setData({ 
      fillHistory: [], 
      hasColored: false,
      coloringProgressPercent: 0,
      progressThumbLeftPercent: 0,
      coloringProgressFilledPixels: 0,
      selectedRegion: { name: '', hint: '请选择一个闭合区域，点击填色' },
    });

    // 兜底：无内置图时下载后端线稿并转本地 temp 路径
    if (!bundledLineArt && !sketch.local_thumb) {
      this._downloadImage(lineArtUrl)
        .then((tempPath) => {
          this._lineArtTempPath = tempPath;
          this.setData({ lineArtDisplayUrl: tempPath });
        })
        .catch(() => {});
    }

    wx.vibrateShort();

    // 使用 nextTick 避免固定延迟导致的容器查找失败
    wx.nextTick(() => this._initCanvases());
  },

  _partIcon(name) {
    const n = String(name || '');
    if (n.includes('身体')) return '🧸';
    if (n.includes('头')) return '🙂';
    if (n.includes('耳')) return '👂';
    if (n.includes('尾')) return '🐾';
    if (n.includes('四肢') || n.includes('脚') || n.includes('腿')) return '🦶';
    if (n.includes('果身') || n.includes('果')) return '🍎';
    if (n.includes('叶根') || n.includes('梗') || n.includes('根')) return '🌿';
    if (n.includes('叶')) return '🍃';
    return '🎨';
  },

  onSketchImageError(e) {
    const index = Number(e.currentTarget.dataset.index);
    const sketchId = e.currentTarget.dataset.sketchId;

    // 优先：如果 index 能用，直接定位
    if (Number.isFinite(index)) {
      this.setData({
        [`sketchList[${index}].local_thumb`]: ''
      });
      return;
    }

    // 兜底：用 id 找到 sketchList 中对应项
    if (!sketchId) return;
    const list = this.data.sketchList || [];
    const idx = list.findIndex((it) => String(it && it.id) === String(sketchId));
    if (idx < 0) return;

    this.setData({
      [`sketchList[${idx}].local_thumb`]: ''
    });
  },

  onLineArtImageError() {
    // 常见原因：/assets/coloring/lineart/* 在项目内不存在，导致本地路径加载失败
    // 兜底策略：下载后端线稿到 temp path 再显示
    if (this._lineArtTempPath && this.data.lineArtDisplayUrl !== this._lineArtTempPath) {
      this.setData({ lineArtDisplayUrl: this._lineArtTempPath });
      return;
    }

    const url = this.data.lineArtUrl;
    if (!url) {
      wx.showToast({ title: '线稿地址为空', icon: 'none' });
      return;
    }

    if (this._downloadingLineArt) return;
    this._downloadingLineArt = true;
    this._downloadImage(url)
      .then((tempPath) => {
        this._lineArtTempPath = tempPath;
        this.setData({ lineArtDisplayUrl: tempPath });
      })
      .catch((err) => {
        wx.showToast({ title: '线稿显示失败', icon: 'none' });
      })
      .finally(() => {
        this._downloadingLineArt = false;
      });
  },

  // ═══════════════════════════════════
  //  涂色模式：Canvas 和绘图
  // ═══════════════════════════════════

  _initCanvases() {
    const query = wx.createSelectorQuery().in(this);
    query.select('#canvasContainer').boundingClientRect((rect) => {
      if (!rect) {
        console.error('获取 Canvas 尺寸失败');
        return;
      }

      const canvasWidth = Math.max(1, Math.floor(rect.width));
      // 兜底：某些情况下 rect.height 可能为 0（布局尚未稳定 / aspect-ratio 不生效）
      const measuredH = Math.floor(rect.height);
      const canvasHeight = Math.max(1, measuredH > 1 ? measuredH : canvasWidth);

      this.setData({ 
        canvasWidth, 
        canvasHeight,
        canvasLeft: rect.left,
        canvasTop: rect.top,
        canvasReady: false
      }, () => {
        // 确保 canvas 宽高属性已应用后再绘制，避免被重置清空
        this._paintPixels = new Uint8ClampedArray(Math.floor(canvasWidth * canvasHeight * 4));
        this._regionColorIndexMap = {};

        // 先生成一张“本地占位线稿图片”并赋值给 lineArtDisplayUrl，避免什么都不展示
        // 注意：不能画在 paintCanvas 上，因为后续会用 putImageData 覆盖整层像素
        this._ensureLocalPlaceholderLineArt(canvasWidth, canvasHeight);

        // 上传线稿和区域图
        this._loadLineArtAndRegionMap(canvasWidth, canvasHeight);
      });
    }).exec();
  },

  _ensureLocalPlaceholderLineArt(canvasWidth, canvasHeight) {
    if (this.data.lineArtDisplayUrl) return;
    if (this._placeholderLineArtRendering) return;
    this._placeholderLineArtRendering = true;

    const w = Math.max(1, Math.floor(canvasWidth || this.data.canvasWidth));
    const h = Math.max(1, Math.floor(canvasHeight || this.data.canvasHeight));
    const ctx = wx.createCanvasContext('mergeCanvas', this);

    ctx.clearRect(0, 0, w, h);
    ctx.setFillStyle('#ffffff');
    ctx.fillRect(0, 0, w, h);

    // 画一个“线稿占位”：边框 + 简单几何线条（保证肉眼可见）
    ctx.setStrokeStyle('#111827');
    ctx.setLineWidth(Math.max(6, Math.floor(Math.min(w, h) * 0.02)));
    ctx.strokeRect(24, 24, w - 48, h - 48);
    ctx.beginPath();
    ctx.moveTo(48, Math.floor(h * 0.25));
    ctx.lineTo(w - 48, Math.floor(h * 0.25));
    ctx.moveTo(48, Math.floor(h * 0.5));
    ctx.lineTo(w - 48, Math.floor(h * 0.5));
    ctx.moveTo(48, Math.floor(h * 0.75));
    ctx.lineTo(w - 48, Math.floor(h * 0.75));
    ctx.stroke();

    ctx.setFillStyle('#111827');
    ctx.setFontSize(Math.max(18, Math.floor(Math.min(w, h) * 0.06)));
    ctx.fillText('线稿加载中…', 36, Math.max(80, Math.floor(h * 0.12)));

    ctx.setFillStyle('#6b7280');
    ctx.setFontSize(Math.max(14, Math.floor(Math.min(w, h) * 0.04)));
    ctx.fillText('（用于验证前端渲染链路）', 36, Math.max(120, Math.floor(h * 0.18)));

    ctx.draw(false, () => {
      wx.canvasToTempFilePath({
        canvasId: 'mergeCanvas',
        success: (res) => {
          if (res && res.tempFilePath && !this.data.lineArtDisplayUrl) {
            this._lineArtTempPath = res.tempFilePath;
            this.setData({ lineArtDisplayUrl: res.tempFilePath });
          }
        },
        fail: (err) => {
          wx.showToast({ title: '占位图导出失败', icon: 'none' });
        },
        complete: () => {
          this._placeholderLineArtRendering = false;
        }
      }, this);
    });
  },

  _loadLineArtAndRegionMap(canvasWidth, canvasHeight) {
    // 闭合区域填涂依赖：baseCanvas 像素（线稿闭合墙）
    // 纯前端模式：不再下载/解析 regionMap。
    const linePromise = this.data.lineArtUrl
      ? this._downloadImage(this.data.lineArtUrl)
      : Promise.resolve(this.data.lineArtDisplayUrl);

    this.setData({ canvasReady: false });

    Promise.allSettled([linePromise]).then(([lineRes]) => {
      const lineArtData = lineRes.status === 'fulfilled' ? lineRes.value : null;

      if (lineArtData) {
        this._lineArtTempPath = lineArtData;
        this.setData({ lineArtDisplayUrl: lineArtData });
        this._drawBaseLineArt(lineArtData, canvasWidth, canvasHeight);
        this._paintPixels = new Uint8ClampedArray(Math.floor(canvasWidth * canvasHeight * 4));
      }

      if (!lineArtData) {
        wx.showToast({ title: '线稿加载失败', icon: 'none' });
      }
    }).catch(err => {
      console.error('加载图像出错', err);
      wx.showToast({ title: '图像加载出错', icon: 'none' });
    });
  },

  _downloadImage(url) {
    // 目标：无论后端是 http 还是 https，最终都产出一个“本地可用路径”（tempFilePath / USER_DATA_PATH）
    // 原因：<wx-image> 已不支持直接加载 http URL；而 downloadFile 在部分环境下也可能失败。
    return new Promise((resolve, reject) => {
      if (!url) {
        reject(new Error('Empty url'));
        return;
      }

      const tryRequestWriteFile = () => {
        const fs = wx.getFileSystemManager && wx.getFileSystemManager();
        if (!fs || !wx.request || !wx.env || !wx.env.USER_DATA_PATH) {
          reject(new Error('No fs/request env'));
          return;
        }

        const safeName = String(url)
          .split('?')[0]
          .split('/')
          .filter(Boolean)
          .slice(-1)[0] || `img_${Date.now()}.png`;
        const fileName = /\.png$/i.test(safeName) ? safeName : `${safeName}.png`;
        const savePath = `${wx.env.USER_DATA_PATH}/${Date.now()}_${Math.random().toString(16).slice(2)}_${fileName}`;

        wx.request({
          url,
          method: 'GET',
          responseType: 'arraybuffer',
          timeout: 20000,
          success: (res) => {
            const ok = res && (res.statusCode === 200) && res.data;
            if (!ok) {
              reject(new Error(`request failed: ${res && res.statusCode}`));
              return;
            }
            fs.writeFile({
              filePath: savePath,
              data: res.data,
              encoding: 'binary',
              success: () => resolve(savePath),
              fail: reject,
            });
          },
          fail: reject,
        });
      };

      wx.downloadFile({
        url,
        success: (res) => {
          if (res.statusCode === 200 && res.tempFilePath) {
            resolve(res.tempFilePath);
          } else {
            tryRequestWriteFile();
          }
        },
        fail: () => {
          tryRequestWriteFile();
        }
      });
    });
  },

  _resolveCanvasImagePath(src) {
    return new Promise((resolve) => {
      if (!src) {
        resolve('');
        return;
      }
      wx.getImageInfo({
        src,
        success: (res) => resolve(res.path || src),
        fail: () => resolve(src)
      });
    });
  },

  _calcAspectFitRect(imgW, imgH, canvasW, canvasH) {
    const cw = Math.max(1, Math.floor(canvasW));
    const ch = Math.max(1, Math.floor(canvasH));
    const iw = Math.max(1, Math.floor(imgW));
    const ih = Math.max(1, Math.floor(imgH));
    const scale = Math.min(cw / iw, ch / ih);
    const dw = Math.max(1, Math.floor(iw * scale));
    const dh = Math.max(1, Math.floor(ih * scale));
    const dx = Math.floor((cw - dw) / 2);
    const dy = Math.floor((ch - dh) / 2);
    return { dx, dy, dw, dh, cw, ch };
  },

  _parseRegionMapData(regionMapPath, canvasWidth, canvasHeight) {
    return new Promise((resolve, reject) => {
    // 兼容旧版 CanvasContext：直接用路径 drawImage，不使用 createImage()
    const ctx = wx.createCanvasContext('regionCanvas', this);
    const w = Math.max(1, Math.floor(canvasWidth || this.data.canvasWidth));
    const h = Math.max(1, Math.floor(canvasHeight || this.data.canvasHeight));
    ctx.clearRect(0, 0, w, h);
    // 用白底填充，让 padding 区域自然不可填
    ctx.setFillStyle('#ffffff');
    ctx.fillRect(0, 0, w, h);

    // 关键：regionMap 也按 aspectFit 绘制，和前端线稿 <image mode="aspectFit"> 对齐
    wx.getImageInfo({
      src: regionMapPath,
      success: (info) => {
        const { dx, dy, dw, dh } = this._calcAspectFitRect(info.width, info.height, w, h);
        ctx.drawImage(regionMapPath, dx, dy, dw, dh);
        ctx.draw(false, () => {
          wx.canvasGetImageData({
            canvasId: 'regionCanvas',
            x: 0,
            y: 0,
            width: w,
            height: h,
            success: (res) => {
              this.setData({ regionMapImageData: res.data });
              this._buildRegionColorMap(res.data);
              // 自检：如果像素全透明（常见于隐藏 canvas 未渲染），提前给出可见提示
              try {
                const d = res.data || [];
                const samplePoints = [
                  [Math.floor(w / 2), Math.floor(h / 2)],
                  [Math.floor(w * 0.25), Math.floor(h * 0.25)],
                  [Math.floor(w * 0.75), Math.floor(h * 0.25)],
                  [Math.floor(w * 0.25), Math.floor(h * 0.75)],
                  [Math.floor(w * 0.75), Math.floor(h * 0.75)]
                ];
                let anyNonZero = false;
                for (const [sx, sy] of samplePoints) {
                  const si = (sy * w + sx) * 4 + 3;
                  const a = d[si] || 0;
                  if (a > 0) { anyNonZero = true; break; }
                }
                if (!anyNonZero) {
                  wx.showToast({ title: '区域图像素全透明，疑似隐藏canvas未渲染', icon: 'none' });
                }
              } catch (e2) {}
              // 若后端没有提供 offsets_url，则退回前端扫描构建
              if (!this._regionPixelOffsets) {
                this._buildRegionPixelOffsets(res.data);
              }
              console.log('✅ 区域图数据缓存完成');
              resolve();
            },
            fail: (err) => {
              console.error('❌ 读取区域图像素失败', err);
              wx.showToast({ title: '区域图加载失败', icon: 'none' });
              reject(err);
            }
          }, this);
        });
      },
      fail: () => {
        // 兜底：无法取尺寸时仍按拉伸绘制（保持旧逻辑）
        ctx.drawImage(regionMapPath, 0, 0, w, h);
        ctx.draw(false, () => {
          wx.canvasGetImageData({
            canvasId: 'regionCanvas',
            x: 0,
            y: 0,
            width: w,
            height: h,
            success: (res) => {
              this.setData({ regionMapImageData: res.data });
              this._buildRegionColorMap(res.data);
              try {
                const d = res.data || [];
                const samplePoints = [
                  [Math.floor(w / 2), Math.floor(h / 2)],
                  [Math.floor(w * 0.25), Math.floor(h * 0.25)],
                  [Math.floor(w * 0.75), Math.floor(h * 0.25)],
                  [Math.floor(w * 0.25), Math.floor(h * 0.75)],
                  [Math.floor(w * 0.75), Math.floor(h * 0.75)]
                ];
                let anyNonZero = false;
                for (const [sx, sy] of samplePoints) {
                  const si = (sy * w + sx) * 4 + 3;
                  const a = d[si] || 0;
                  if (a > 0) { anyNonZero = true; break; }
                }
                if (!anyNonZero) {
                  wx.showToast({ title: '区域图像素全透明，疑似隐藏canvas未渲染', icon: 'none' });
                }
              } catch (e2) {}
              if (!this._regionPixelOffsets) {
                this._buildRegionPixelOffsets(res.data);
              }
              console.log('✅ 区域图数据缓存完成');
              resolve();
            },
            fail: (err) => {
              console.error('❌ 读取区域图像素失败', err);
              wx.showToast({ title: '区域图加载失败', icon: 'none' });
              reject(err);
            }
          }, this);
        });
      }
    });
    });
  },

  _loadRegionOffsetsFromServer(url) {
    // 下载二进制 offsets 文件并解析成 { colorKey: Uint32Array(offsets) }
    wx.request({
      url,
      method: 'GET',
      responseType: 'arraybuffer',
      timeout: 20000,
      success: (res) => {
        if (res.statusCode !== 200 || !res.data) return;
        try {
          const map = this._parseOffsetsArrayBuffer(res.data);
          if (map && Object.keys(map).length) {
            this._regionPixelOffsets = map;
            this.setData({ offsetsReady: true });
          }
        } catch (e) {
          // ignore, fallback to client build
        }
      },
      fail: () => {}
    });
  },

  _parseOffsetsArrayBuffer(buf) {
    // 对应后端 OFST1 格式
    const u8 = new Uint8Array(buf);
    const magic = String.fromCharCode(u8[0], u8[1], u8[2], u8[3], u8[4]);
    if (magic !== 'OFST1') return null;
    const dv = new DataView(buf);
    let off = 5;
    const nKeys = dv.getUint32(off, true); off += 4;
    const out = {};
    const dec = new TextDecoder('utf-8');
    for (let k = 0; k < nKeys; k++) {
      const keyLen = dv.getUint16(off, true); off += 2;
      const key = dec.decode(u8.slice(off, off + keyLen)); off += keyLen;
      const count = dv.getUint32(off, true); off += 4;
      const bytes = count * 4;
      const arr = new Uint32Array(buf.slice(off, off + bytes));
      off += bytes;
      out[key] = arr;
    }
    return out;
  },

  _buildRegionPixelOffsets(imageData) {
    // 预计算每个 colorKey 对应的像素偏移列表，用于“拖动预览”快速渲染
    const data = imageData || [];
    const buckets = {};
    for (let i = 0; i < data.length; i += 4) {
      const a = data[i + 3];
      if (a < 10) continue;
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      if (r > 245 && g > 245 && b > 245) continue;
      const key = `rgb(${r},${g},${b})`;
      (buckets[key] || (buckets[key] = [])).push(i);
    }
    const out = {};
    Object.keys(buckets).forEach((k) => {
      out[k] = new Uint32Array(buckets[k]);
    });
    this._regionPixelOffsets = out;
  },

  _cacheLineArtPixels(lineArtPath, canvasWidth, canvasHeight) {
    return new Promise((resolve, reject) => {
      const ctx = wx.createCanvasContext('mergeCanvas', this);
      const w = Math.max(1, Math.floor(canvasWidth || this.data.canvasWidth));
      const h = Math.max(1, Math.floor(canvasHeight || this.data.canvasHeight));

      this._resolveCanvasImagePath(lineArtPath).then((drawPath) => {
        ctx.clearRect(0, 0, w, h);
        ctx.setFillStyle('#ffffff');
        ctx.fillRect(0, 0, w, h);
        if (drawPath) {
          ctx.drawImage(drawPath, 0, 0, w, h);
        }
        ctx.draw(false, () => {
          wx.canvasGetImageData({
            canvasId: 'mergeCanvas',
            x: 0,
            y: 0,
            width: w,
            height: h,
            success: (res) => {
                const data = res.data || [];
                const cx = Math.floor(w / 2);
                const cy = Math.floor(h / 2);
                const ci = (cy * w + cx) * 4 + 3;
                const alpha = data[ci] || 0;

                this._baseLinePixels = new Uint8ClampedArray(data);

                if (alpha > 0) {
                  this._paintPixels = new Uint8ClampedArray(data);
                  this._renderPaintPixels();
                } else {
                  // drawImage 失败时不要把空白/透明数据刷到可见层，避免遮挡底图
                  this._paintPixels = new Uint8ClampedArray(Math.floor(w * h * 4));
                }
              resolve();
            },
            fail: (err) => reject(err)
          }, this);
        });
      });
    });
  },

  _drawLineArtToPaintCanvas(lineArtPath, canvasWidth, canvasHeight) {
    const w = Math.max(1, Math.floor(canvasWidth || this.data.canvasWidth));
    const h = Math.max(1, Math.floor(canvasHeight || this.data.canvasHeight));
    const ctx = wx.createCanvasContext('paintCanvas', this);

    const drawOnce = (path) => {
      this._resolveCanvasImagePath(path).then((drawPath) => {
        ctx.clearRect(0, 0, w, h);
        if (drawPath) {
          ctx.drawImage(drawPath, 0, 0, w, h);
        }
        ctx.draw(false, () => {
          wx.canvasGetImageData({
            canvasId: 'paintCanvas',
            x: Math.floor(w / 2),
            y: Math.floor(h / 2),
            width: 1,
            height: 1,
            success: (res) => {
              const alpha = res && res.data ? res.data[3] : 0;
              if (alpha > 0) {
                console.log('✅ 线稿已强制绘制到画板');
                return;
              }
              console.warn('⚠️ 线稿绘制后像素透明，保留强制底图层兜底');
            },
            fail: () => {}
          }, this);
        });
      });
    };

    try {
      drawOnce(lineArtPath);
    } catch (e) {
      const fallback = this.data.lineArtUrl || lineArtPath;
      drawOnce(fallback);
    }
  },

  // 点击涂色区域
  handleTap(e) {
    if (!this.data.canvasReady || this.data.evaluating) return;

    const now = Date.now();
    if (now - this._lastTapTs < 120) return;
    this._lastTapTs = now;

    const touch = (e.touches && e.touches[0]) || (e.changedTouches && e.changedTouches[0]) || e.detail;
    if (!touch) return;

    // 坐标：优先 changedTouches 的 clientXY 减 #canvasContainer 的 boundingClientRect；
    // 勿优先 e.detail.x/y（点到 canvas/image 子节点时常相对错误原点，导致纵向大偏移）。
    const query = wx.createSelectorQuery().in(this);
    query.select('#canvasContainer').boundingClientRect((rect) => {
      const { canvasWidth, canvasHeight } = this.data;
      if (!rect || !canvasWidth || !canvasHeight) return;

      const containerW = Math.max(1, Math.floor(rect.width));
      const containerH = Math.max(1, Math.floor(rect.height));
      const scaleX = canvasWidth / containerW;
      const scaleY = canvasHeight / containerH;

      // 优先 clientXY：点到子节点(canvas/image)时 e.detail.x/y 可能相对错误原点，导致整幅填色纵向/横向偏移
      let rawX;
      let rawY;
      if (typeof touch.clientX === 'number' && typeof touch.clientY === 'number') {
        rawX = touch.clientX - rect.left;
        rawY = touch.clientY - rect.top;
      } else if (typeof e.detail === 'object' && typeof e.detail.x === 'number' && typeof e.detail.y === 'number') {
        rawX = e.detail.x;
        rawY = e.detail.y;
      } else if (typeof touch.pageX === 'number' && typeof touch.pageY === 'number') {
        rawX = touch.pageX - rect.left;
        rawY = touch.pageY - rect.top;
      } else {
        return;
      }

      // 与 <image mode="aspectFit"> / baseCanvas 一致：先映射到「线稿在容器内的显示框」，再换算到画布像素
      let x;
      let y;
      const nat = this._lineArtNaturalSize;
      const cfit = this._lineArtCanvasFit;
      // 当线稿展示改为直接显示 baseCanvas（同一像素网格）时，不需要再做 aspectFit 映射
      if (this.data.showBaseCanvasLineArt) {
        x = rawX * scaleX;
        y = rawY * scaleY;
      } else if (nat && nat.w && nat.h && cfit && cfit.dw > 0 && cfit.dh > 0) {
        const {
          dx: fdx,
          dy: fdy,
          dw: fdw,
          dh: fdh
        } = this._calcAspectFitRect(nat.w, nat.h, containerW, containerH);
        const u = (rawX - fdx) / fdw;
        const v = (rawY - fdy) / fdh;
        if (u < -0.02 || u > 1.02 || v < -0.02 || v > 1.02) {
          return;
        }
        const uc = Math.min(1, Math.max(0, u));
        const vc = Math.min(1, Math.max(0, v));
        x = cfit.dx + uc * cfit.dw;
        y = cfit.dy + vc * cfit.dh;
      } else {
        x = rawX * scaleX;
        y = rawY * scaleY;
      }
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;

      if (x < 0 || y < 0 || x >= canvasWidth || y >= canvasHeight) {
        return;
      }

      // 1. 识别区域（带调试信息）
      const hit = this._identifyRegionWithDebug(x, y);
      const region = hit.region;
      if (!region) {
        wx.showToast({ title: hit.toast || '点击在线条上，请选择区域', icon: 'none' });
        return;
      }

      // 2. 高亮区域
      this._highlightRegion(region, x, y);

      this.setData({
        selectedRegion: region,
        // 关键：不要在每次填色点击时覆盖推荐色
        // 否则用户用“参考答案推荐色”填色后，推荐色会被重置为原调色板。
        recommendedColors: (this.data.recommendedColors && this.data.recommendedColors.length)
          ? this.data.recommendedColors
          : (this.data.colors ? this.data.colors.slice(0, 4) : [])
      });

      // 4. 填充区域
      this._fillRegion(region);

      // 5. 特效
      const sparkle = {
        id: Date.now(),
        x: x + Math.random() * 40 - 20,
        y: y + Math.random() * 40 - 20
      };
      const sparkles = [...this.data.sparkles, sparkle];
      this.setData({
        sparkles: sparkles,
        hasColored: true
      });

      setTimeout(() => {
        this.setData({
          sparkles: this.data.sparkles.filter(s => s.id !== sparkle.id)
        });
      }, 800);

      wx.vibrateShort();
    }).exec();
  },

  _identifyRegionWithDebug(x, y) {
    // 基于线稿像素识别“可填充区域”的起点（闭合区域 flood fill）
    const { canvasWidth, canvasHeight } = this.data;
    const fx = Math.floor(x);
    const fy = Math.floor(y);
    const sx = fx;
    const sy = fy;
    const base = `xy=(${fx},${fy}) canvas=(${canvasWidth}x${canvasHeight})`;

    if (!this._baseLinePixels) {
      return { region: null, toast: '线稿加载中…', debug: `${base} lineArtPixels=未就绪` };
    }
    if (!this.data.currentSketch) {
      return { region: null, toast: '任务未就绪', debug: `${base} sketch=null` };
    }

    const data = this._baseLinePixels;
    const wall = this._lineWallMask;
    const idx = (sy * canvasWidth + sx) * 4;
    const r0 = data[idx], g0 = data[idx + 1], b0 = data[idx + 2], a0 = data[idx + 3];
    const raw = `rgba=(${r0},${g0},${b0},${a0})`;

    const isEmpty = (a) => (typeof a !== 'number') || (a < 10);
    // 与 _rebuildPaintPixels 里的“线条墙”判定保持一致
    const isLine = (r, g, b, a) => {
      // 若墙掩码已构建，直接用掩码判定（这里不再依赖灰度阈值）
      if (wall) return false;
      if (!a || typeof a !== 'number') return false;
      if (a < 128) return false;
      const gray = (r + g + b) / 3;
      return gray < 180;
    };

    // 在线条或透明附近时：在邻域内寻找更“像区域内部”的种子点
    // 通过“非线条像素 + 周围邻域也大多为非线条”来避免选到隔壁小区域/边缘外侧。
    let pick = { r: r0, g: g0, b: b0, a: a0, x: sx, y: sy, dist2: 0, neighborScore: -1 };
    const isCandidateSeed = (xx, yy) => {
      const ii = (yy * canvasWidth + xx) * 4;
      const r = data[ii], g = data[ii + 1], b = data[ii + 2], a = data[ii + 3];
      const p = yy * canvasWidth + xx;
      if (isEmpty(a)) return { ok: false, score: 0 };
      if (wall && wall[p]) return { ok: false, score: 0 };
      if (!wall && isLine(r, g, b, a)) return { ok: false, score: 0 };

      // 8 邻域非线条计数（越高越说明在区域内部）
      const dirs = [
        [-1, -1], [0, -1], [1, -1],
        [-1, 0],           [1, 0],
        [-1, 1], [0, 1], [1, 1],
      ];
      let score = 0;
      for (const [ddx, ddy] of dirs) {
        const nx = xx + ddx;
        const ny = yy + ddy;
        if (nx < 0 || nx >= canvasWidth || ny < 0 || ny >= canvasHeight) continue;
        const ni = (ny * canvasWidth + nx) * 4;
        const nr = data[ni], ng = data[ni + 1], nb = data[ni + 2], na = data[ni + 3];
        const np = ny * canvasWidth + nx;
        if (isEmpty(na)) continue;
        if (wall) {
          if (!wall[np]) score += 1;
        } else {
          if (!isLine(nr, ng, nb, na)) score += 1;
        }
      }
      return { ok: score >= 5, score };
    };

    // 判断种子所在连通域是否触达边界：
    // 触边通常意味着“外背景”，不应作为闭合填色目标。
    const regionTouchesBorder = (sx0, sy0) => {
      if (!wall) return false;
      if (sx0 < 0 || sy0 < 0 || sx0 >= canvasWidth || sy0 >= canvasHeight) return true;
      const p0 = sy0 * canvasWidth + sx0;
      if (wall[p0]) return true;
      const visited = new Uint8Array(canvasWidth * canvasHeight);
      const stack = [[sx0, sy0]];
      while (stack.length) {
        const [cx, cy] = stack.pop();
        if (cx < 0 || cy < 0 || cx >= canvasWidth || cy >= canvasHeight) continue;
        const p = cy * canvasWidth + cx;
        if (visited[p]) continue;
        visited[p] = 1;
        if (wall[p]) continue;
        if (cx === 0 || cy === 0 || cx === canvasWidth - 1 || cy === canvasHeight - 1) {
          return true;
        }
        stack.push([cx + 1, cy]);
        stack.push([cx - 1, cy]);
        stack.push([cx, cy + 1]);
        stack.push([cx, cy - 1]);
      }
      return false;
    };

    const p0 = sy * canvasWidth + sx;
    const isWall0 = wall ? !!wall[p0] : isLine(r0, g0, b0, a0);
    if (isEmpty(a0) || isWall0 || regionTouchesBorder(sx, sy)) {
      const rad = 8;
      for (let dy = -rad; dy <= rad; dy++) {
        const yy = sy + dy;
        if (yy < 0 || yy >= canvasHeight) continue;
        for (let dx = -rad; dx <= rad; dx++) {
          const xx = sx + dx;
          if (xx < 0 || xx >= canvasWidth) continue;
          const d2 = dx * dx + dy * dy;
          if (pick.dist2 !== 0 && d2 > pick.dist2) continue; // 已有更近候选则跳过

          const c = isCandidateSeed(xx, yy);
          if (!c.ok) continue;
          if (regionTouchesBorder(xx, yy)) continue;
          if (pick.dist2 === 0 || d2 < pick.dist2 || (d2 === pick.dist2 && c.score > pick.neighborScore)) {
            const ii = (yy * canvasWidth + xx) * 4;
            const r = data[ii], g = data[ii + 1], b = data[ii + 2], a = data[ii + 3];
            pick = { r, g, b, a, x: xx, y: yy, dist2: d2, neighborScore: c.score };
          }
        }
      }
    }

    if (isEmpty(pick.a) || regionTouchesBorder(pick.x, pick.y)) {
      return { region: null, toast: '点到空白区域', debug: `${base} ${raw} pick=none` };
    }

    // 闭合区域 flood fill 模式：只需要返回一个起点像素坐标
    // 若点击点不是墙，仍可计算一次邻域得分用于 debug（避免 neighborScore=-1 的误解）
    if (pick.neighborScore < 0) {
      const dirs = [
        [-1, -1], [0, -1], [1, -1],
        [-1, 0],           [1, 0],
        [-1, 1], [0, 1], [1, 1],
      ];
      let score = 0;
      for (const [ddx, ddy] of dirs) {
        const nx = pick.x + ddx;
        const ny = pick.y + ddy;
        if (nx < 0 || nx >= canvasWidth || ny < 0 || ny >= canvasHeight) continue;
        const ni = (ny * canvasWidth + nx) * 4;
        const na = data[ni + 3];
        if (isEmpty(na)) continue;
        const np = ny * canvasWidth + nx;
        if (wall) {
          if (!wall[np]) score += 1;
        } else {
          const nr = data[ni], ng = data[ni + 1], nb = data[ni + 2];
          if (!isLine(nr, ng, nb, na)) score += 1;
        }
      }
      pick.neighborScore = score;
    }

    return {
      region: {
        x: pick.x,
        y: pick.y,
        name: '',
        hint: '已识别到可填充区域'
      },
      toast: '',
      debug: `${base} ${raw} pick=(${pick.x},${pick.y}) neighborScore=${pick.neighborScore} lineFloodFill=ready`
    };
  },

  // （已移除）拖动色球上色交互：为提升流畅性，改回“点击闭合区域填色”

  autoCompleteColoring() {
    if (this.data.evaluating) return;
    if (!this.data.hasColored) {
      wx.showToast({ title: '先涂一涂哦', icon: 'none' });
      return;
    }
    const url = this._getReferenceAnswerUrl(this.data.currentSketch);
    if (!url) {
      wx.showToast({ title: '暂无参考答案', icon: 'none' });
      return;
    }
    this.setData({
      showReferenceModal: true,
      referenceAnswerUrl: url
    });
  },

  closeReferenceModal() {
    this.setData({
      showReferenceModal: false,
      referenceAnswerUrl: ''
    });
  },

  _getReferenceAnswerUrl(sketch) {
    if (!sketch) return '';

    // 最新题库/答案库采用“同名文件”一一对应（资源已统一迁移到 /assets 下）：
    // /assets/paint_basement/<filename>  -> /assets/paint_basement_masks/<filename>
    // 例如：16 西瓜.jpg -> 16 西瓜.jpg
    const pickStrings = [];
    if (sketch.lineart_url) pickStrings.push(String(sketch.lineart_url));
    if (sketch.local_thumb) pickStrings.push(String(sketch.local_thumb));
    if (sketch.title) pickStrings.push(String(sketch.title));
    if (sketch.id) pickStrings.push(String(sketch.id));

    let fileName = '';

    // 1) 优先从线稿 URL 提取文件名（最可靠）
    for (const s0 of pickStrings) {
      const s = String(s0 || '');
      if (!s) continue;
      const noQuery = s.split('?')[0];
      const base = noQuery.split('/').pop() || '';
      if (/\.(png|jpg|jpeg|webp)$/i.test(base)) {
        fileName = base;
        break;
      }
    }

    // 2) 兜底：从题号构造（如果后端只给了纯标题/ID）
    if (!fileName) {
      const num = (sketch.metaNum != null) ? sketch.metaNum : this._extractNumFromSketch(sketch);
      if (Number.isFinite(num)) {
        const stem = String(sketch.title || sketch.id || '').trim();
        fileName = stem ? `${num} ${stem}.jpg` : `${num}.jpg`;
      }
    }

    if (!fileName) return '';

    // 用绝对 URL，确保小程序图片能正确加载（不能只用相对路径）
    const p = `/assets/paint_basement_masks/${encodeURIComponent(fileName)}`;
    return this._toAbsoluteUrl(p);
  },

  // （已移除）预览层渲染

  _highlightRegion(region, x, y) {
    // 单画布模式下用星光特效代替高亮圈，避免多层 canvas 兼容问题
    return;
  },

  _fillRegion(region) {
    if (!this._baseLinePixels || !region) return;

    // 使用当前点击点作为 flood fill 起点（region 里已有 pickX/pickY）
    const sx = typeof region.x === 'number' ? region.x : null;
    const sy = typeof region.y === 'number' ? region.y : null;
    if (sx == null || sy == null) return;

    // 保存到历史：起点坐标 + 颜色
    const fillHistory = this.data.fillHistory.concat({
      x: sx,
      y: sy,
      color: this.data.selectedColor,
      timestamp: Date.now()
    });
    this.setData({ fillHistory });
    this._rebuildPaintPixels(fillHistory);
  },

  // 选择颜色
  selectColor(e) {
    const color = e.currentTarget.dataset.color;
    this.setData({ selectedColor: color });
    wx.vibrateShort();
  },

  // 撤销
  undoColor() {
    if (this.data.fillHistory.length === 0) {
      wx.showToast({ title: '还没涂色呢', icon: 'none' });
      return;
    }

    const fillHistory = this.data.fillHistory.slice(0, -1);
    const hasColored = fillHistory.length > 0;
    this.setData({
      fillHistory,
      hasColored,
      sparkles: hasColored ? this.data.sparkles : [],
      selectedRegion: hasColored ? this.data.selectedRegion : { name: '', hint: '请选择一个闭合区域，点点涂色吧' }
    });
    this._rebuildPaintPixels(fillHistory);

    wx.vibrateShort();
  },

  // 完成涂色 → 进入评价流程
  async finishColoring() {
    if (this.data.evaluating || this.data.showScore || this.data.showFinishModal || this.data.finishPreviewLoading) return;
    if (!this.data.hasColored) {
      wx.showToast({ title: '请先涂色哦', icon: 'none' });
      return;
    }
    if (!this._requireProgress100('完成')) return;

    // 新流程：先导出 → 弹出预览弹窗（保存 / AI打分 / 继续修改）
    this.setData({ finishPreviewLoading: true });
    this._exportToPNG((pngPath) => {
      if (!pngPath) {
        this.setData({ finishPreviewLoading: false });
        wx.showToast({ title: '导出失败', icon: 'none' });
        return;
      }

      // 彩带可保留，增强“完成”反馈，但不影响画板
      this.setData({
        showConfetti: true,
        finishPreviewLoading: false,
        showFinishModal: true,
        finishPreviewPath: pngPath,
        lastExportPngPath: pngPath,
      });
      setTimeout(() => {
        this.setData({ showConfetti: false });
      }, 3000);
    });
  },

  closeFinishModal() {
    this.setData({
      showFinishModal: false,
      finishPreviewPath: '',
      finishPreviewLoading: false
    });
  },

  finishModalSave() {
    if (!this._requireProgress100('保存')) return;
    // 进入保存弹窗（不离开涂色页，不清空画板）
    this.setData({
      showFinishModal: false,
      showSaveDialog: true,
      saveResult: {
        cloudWorkId: '',
        cloudStatus: '',
        localAlbumStatus: '',
        localRecordPath: ''
      }
    });
  },

  finishModalAiScore() {
    if (this.data.evaluating) return;
    if (!this._requireProgress100('打分')) return;
    const existing = this.data.lastExportPngPath;
    // 优先复用刚导出的预览图，避免再次导出引发画面闪动
    if (existing) {
      this.setData({ showFinishModal: false });
      this._evaluate(existing, this.data._internalColoringEvalPrompt);
      return;
    }
    this.setData({ showFinishModal: false, finishPreviewLoading: true });
    this._exportToPNG((pngPath) => {
      this.setData({ finishPreviewLoading: false });
      if (!pngPath) {
        wx.showToast({ title: '导出失败', icon: 'none' });
        return;
      }
      this.setData({ lastExportPngPath: pngPath });
      this._evaluate(pngPath, this.data._internalColoringEvalPrompt);
    });
  },

  _exportToPNG(callback) {
    // 底图 image + 涂色画布二次合成导出
    const w = Math.max(1, Math.floor(this.data.canvasWidth));
    const h = Math.max(1, Math.floor(this.data.canvasHeight));
    wx.canvasToTempFilePath({
      canvasId: 'paintCanvas',
      width: w,
      height: h,
      destWidth: w,
      destHeight: h,
      success: (paintRes) => {
        const ctx = wx.createCanvasContext('mergeCanvas', this);
        const linePath = this.data.lineArtDisplayUrl || this.data.lineArtUrl;

        this._resolveCanvasImagePath(linePath).then((drawPath) => {
          ctx.clearRect(0, 0, w, h);
          // 背景白底（和 regionMap 的 padding 逻辑一致）
          ctx.setFillStyle('#ffffff');
          ctx.fillRect(0, 0, w, h);

          const drawMerged = () => {
            // paintCanvas 是整张画布像素（包含 padding），直接覆盖即可
            ctx.drawImage(paintRes.tempFilePath, 0, 0, w, h);
            ctx.draw(false, () => {
              wx.canvasToTempFilePath({
                canvasId: 'mergeCanvas',
                width: w,
                height: h,
                destWidth: w,
                destHeight: h,
                success: (res) => callback(res.tempFilePath),
                fail: () => callback(null)
              }, this);
            });
          };

          if (!drawPath) {
            drawMerged();
            return;
          }

          // 关键修复：如果 lineArtDisplayUrl 已是从 baseCanvas 导出的同尺寸图片，
          // 再做 aspectFit 会“二次适配”导致整体偏移。此时应直接铺满 (0,0,w,h)。
          const shouldDrawFull = (() => {
            if (this.data.showBaseCanvasLineArt) return true;
            const nat = this._lineArtNaturalSize;
            if (nat && Number(nat.w) === w && Number(nat.h) === h) return true;
            const fit = this._lineArtCanvasFit;
            if (fit && Number(fit.dx) === 0 && Number(fit.dy) === 0 && Number(fit.dw) === w && Number(fit.dh) === h) return true;
            return false;
          })();

          if (shouldDrawFull) {
            ctx.drawImage(drawPath, 0, 0, w, h);
            drawMerged();
            return;
          }

          // 线稿按 aspectFit 绘制（用于“原始线稿图片尺寸 != 画布尺寸”的情况）
          wx.getImageInfo({
            src: drawPath,
            success: (info) => {
              const { dx, dy, dw, dh } = this._calcAspectFitRect(info.width, info.height, w, h);
              ctx.drawImage(drawPath, dx, dy, dw, dh);
              drawMerged();
            },
            fail: () => {
              ctx.drawImage(drawPath, 0, 0, w, h);
              drawMerged();
            }
          });
        });
      },
      fail: () => callback(null)
    }, this);
  },

  // ═══════════════════════════════════
  //  AI 评价
  // ═══════════════════════════════════

  _evaluate(imagePath, promptText) {
    this.setData({ evaluating: true });
    const basePrompt = (typeof promptText === 'string' && promptText.trim())
      ? promptText.trim()
      : String(this.data._internalColoringEvalPrompt || '').trim();
    // 把“当前题目名称”隐式传给后端，用于生成“常见颜色建议”（用户不可编辑）
    const title = String((this.data.currentSketch && this.data.currentSketch.title) || '').trim();
    const prompt = title ? `${basePrompt}\n对象：${title}` : basePrompt;

    wx.uploadFile({
      url: `${this.data.apiBaseUrl}/readalong/evaluate`,
      filePath: imagePath,
      name: 'file',
      formData: {
        expected_text: prompt || `请评价这张涂色作品，给出0-100分和建议。`,
        book_id: (this.data.currentSketch && this.data.currentSketch.id) || 'coloring_task',
        sentence_index: '0',
        audio_format: 'png',
        eval_mode: 'coloring_evaluation'
      },
      timeout: 180000,
      success: (res) => {
        try {
          const data = JSON.parse(res.data);
          if (data.ok) {
            const accuracyRaw = Number(data.accuracy);
            const hasAccuracy = Number.isFinite(accuracyRaw);
            const starFromAccuracy = hasAccuracy
              ? Math.max(1, Math.min(5, Math.round(accuracyRaw / 20)))
              : null;
            const starCount = Math.max(1, Math.min(5, Number(data.stars || starFromAccuracy || 4)));
            const score = hasAccuracy
              ? Math.max(0, Math.min(100, Math.round(accuracyRaw)))
              : Math.round((starCount / 5) * 100);
            const evalSource = String(data.source || '');
            const sourceHint = evalSource === 'fallback' ? '（当前为兜底评分）' : '';

            this.setData({
              evalResult: {
                stars: starCount,
                feedback: `${data.feedback || '很棒的涂色作品！'}${sourceHint}`,
                transcript: data.transcript || '',
                source: evalSource
              },
              showScore: true,
              aiScore: score,
              fullStars: starCount
            });

            // 奖励星星
            this._rewardStars(starCount);
          }
        } catch (e) {
          console.log('评价解析失败', e);
          wx.showToast({ title: '评价失败', icon: 'none' });
        }
      },
      fail: () => {
        wx.showToast({ title: '评价请求失败', icon: 'none' });
      },
      complete: () => {
        this.setData({ evaluating: false });
      }
    });
  },

  // （已移除）用户自定义提示词输入

  _drawBaseLineArt(lineArtPath, canvasWidth, canvasHeight) {
    const w = Math.max(1, Math.floor(canvasWidth || this.data.canvasWidth));
    const h = Math.max(1, Math.floor(canvasHeight || this.data.canvasHeight));
    const ctx = wx.createCanvasContext('baseCanvas', this);
    this._baseDrawRetry = 0;

    const drawWithPath = (imgPath) => {
      ctx.clearRect(0, 0, w, h);
      ctx.setFillStyle('#ffffff');
      ctx.fillRect(0, 0, w, h);

      // 必须与 <image mode="aspectFit"> 的缩放策略一致，否则点击坐标与像素栅格会偏离
      wx.getImageInfo({
        src: imgPath,
        success: (info) => {
          const { dx, dy, dw, dh } = this._calcAspectFitRect(info.width, info.height, w, h);
          // 供 handleTap：点击相对整容器映射，必须与 aspectFit 线稿矩形一致，否则会整体错位
          this._lineArtNaturalSize = { w: info.width, h: info.height };
          this._lineArtCanvasFit = { dx, dy, dw, dh };
          try {
            ctx.drawImage(imgPath, dx, dy, dw, dh);
          } catch (e) {
            // 兜底：至少画出可见占位，便于排查
            ctx.setFillStyle('#ffffff');
            ctx.fillRect(0, 0, w, h);
            ctx.setStrokeStyle('#111111');
            ctx.setLineWidth(6);
            ctx.strokeRect(24, 24, w - 48, h - 48);
            ctx.moveTo(24, 24);
            ctx.lineTo(w - 24, h - 24);
            ctx.stroke();
            console.error('❌ drawImage 失败，已绘制兜底占位', e);
          }

          ctx.draw(false, () => {
            this._verifyBaseCanvasVisible(w, h, imgPath, drawWithPath);
          });
        },
        fail: () => {
          this._lineArtNaturalSize = null;
          this._lineArtCanvasFit = { dx: 0, dy: 0, dw: w, dh: h };
          // 尺寸获取失败时，退回到拉伸绘制（不理想但可用）
          try {
            ctx.drawImage(imgPath, 0, 0, w, h);
          } catch (e) {}
          ctx.draw(false, () => {
            this._verifyBaseCanvasVisible(w, h, imgPath, drawWithPath);
          });
        }
      });
    };

    // 优先使用 downloadFile 返回的 temp 路径（通常最稳定）
    // 如果 temp 路径不可渲染，再回退到原始 URL。
    try {
      drawWithPath(lineArtPath);
    } catch (e) {
      console.warn('temp 路径绘制失败，回退原始 URL', e);
      drawWithPath(this.data.lineArtUrl || lineArtPath);
    }
  },

  _verifyBaseCanvasVisible(w, h, imgPath, redrawFn) {
    wx.canvasGetImageData({
      canvasId: 'baseCanvas',
      x: Math.floor(w / 2),
      y: Math.floor(h / 2),
      width: 1,
      height: 1,
      success: (res) => {
        const alpha = res && res.data ? res.data[3] : 0;
        if (alpha > 0) {
          console.log('✅ 线稿底图绘制完成', { w, h, imgPath, alpha, retry: this._baseDrawRetry });
          // 关键：把 baseCanvas 渲染结果导出为图片作为“可见线稿层”
          // 这样“用户看到的线稿”与“flood fill 读取的像素”完全同源，避免任何平台取整/解码差异导致整体偏移。
          try {
            wx.canvasToTempFilePath({
              canvasId: 'baseCanvas',
              width: Math.floor(w),
              height: Math.floor(h),
              destWidth: Math.floor(w),
              destHeight: Math.floor(h),
              success: (r) => {
                if (r && r.tempFilePath) {
                  this._lineArtTempPath = r.tempFilePath;
                  // 显示层改为 baseCanvas 导出的同源图片
                  this.setData({ lineArtDisplayUrl: r.tempFilePath });
                  // 点击映射也改为“画布同尺寸图片”：容器内 aspectFit 将铺满，无留白错位风险
                  this._lineArtNaturalSize = { w: Math.floor(w), h: Math.floor(h) };
                  this._lineArtCanvasFit = { dx: 0, dy: 0, dw: Math.floor(w), dh: Math.floor(h) };
                }
              },
              fail: () => {}
            }, this);
          } catch (e) {}
          // 额外读取整张 baseCanvas 像素，作为“闭合区域填涂”的线稿参考
          wx.canvasGetImageData({
            canvasId: 'baseCanvas',
            x: 0,
            y: 0,
            width: Math.floor(w),
            height: Math.floor(h),
            success: (full) => {
              try {
                const data = full && full.data ? full.data : null;
                if (data && data.length) {
                  this._baseLinePixels = new Uint8ClampedArray(data);
                  // 构建“线条墙”掩码，供识别起点和 flood fill 统一边界判定
                  this._buildLineWallMask(w, h);
                  // 线稿像素就绪后再允许点击填色，避免出现“线稿加载中…/未就绪”
                  if (!this.data.canvasReady) {
                    this.setData({ canvasReady: true, showBaseCanvasLineArt: true });
                  }
                }
              } catch (e2) {}
            },
            fail: () => {},
          }, this);
          return;
        }

        if (this._baseDrawRetry < 2) {
          this._baseDrawRetry += 1;
          const delay = this._baseDrawRetry * 120;
          console.warn(`⚠️ baseCanvas 透明，${delay}ms 后第 ${this._baseDrawRetry} 次重绘`);
          setTimeout(() => redrawFn(imgPath), delay);
          return;
        }

        // 最终兜底：画一个明显的可视占位，确保用户至少看见画板内容
        const ctx = wx.createCanvasContext('baseCanvas', this);
        ctx.setFillStyle('#ffffff');
        ctx.fillRect(0, 0, w, h);
        ctx.setStrokeStyle('#ef4444');
        ctx.setLineWidth(6);
        ctx.strokeRect(20, 20, w - 40, h - 40);
        ctx.setFillStyle('#ef4444');
        ctx.setFontSize(24);
        ctx.fillText('线稿加载中...', 36, 56);
        ctx.draw();
        this.setData({ forceImageFallback: true });
        // 同步读取占位像素，至少解除 canvasReady 锁死
        try {
          wx.canvasGetImageData({
            canvasId: 'baseCanvas',
            x: 0,
            y: 0,
            width: Math.floor(w),
            height: Math.floor(h),
            success: (full2) => {
              try {
                const data = full2 && full2.data ? full2.data : null;
                if (data && data.length) {
                  this._baseLinePixels = new Uint8ClampedArray(data);
                }
              } catch (e3) {}
              this.setData({ canvasReady: true, showBaseCanvasLineArt: true });
            },
            fail: () => {
              this.setData({ canvasReady: true, showBaseCanvasLineArt: true });
            }
          }, this);
        } catch (e4) {
          this.setData({ canvasReady: true, showBaseCanvasLineArt: true });
        }
        console.warn('⚠️ baseCanvas 透明，已绘制兜底占位');
      },
      fail: () => {
        console.log('✅ 线稿底图绘制完成', { w, h, imgPath, retry: this._baseDrawRetry });
      }
    }, this);
  },

  _rewardStars(starCount) {
    const { reportAmusementParkTaskDone } = require("../../utils/amusement-park-stars.js");
    reportAmusementParkTaskDone(app, "color");
    app.globalData.coloringWorks = (app.globalData.coloringWorks || 0) + 1;

    try {
      wx.setStorageSync('coloringWorks', app.globalData.coloringWorks);
    } catch (e) {
      console.log('保存失败', e);
    }
  },

  // ═══════════════════════════════════
  //  保存作品
  // ═══════════════════════════════════

  closeScore() {
    this.setData({ 
      showScore: false,
      showSaveDialog: true,
      saveResult: {
        cloudWorkId: '',
        cloudStatus: '',
        localAlbumStatus: '',
        localRecordPath: ''
      }
    });
  },

  saveTCloud() {
    if (!this._requireProgress100('保存')) return;
    // 兼容旧按钮：改为“保存到画室”
    this._saveToStudio();
  },

  saveToLocal() {
    if (!this._requireProgress100('保存')) return;
    this._saveToLocal();
  },

  finishSaveDialog() {
    // 保存完成后，直接回到“小小画室”查看作品
    this.setData({ listMode: 'studio' });
    this._backToList();
  },

  _saveToStudio() {
    const reuse = this.data.lastExportPngPath;
    const exportOnce = (cb) => {
      if (reuse) cb(reuse);
      else this._exportToPNG(cb);
    };
    exportOnce((pngPath) => {
      if (!pngPath) {
        wx.showToast({ title: '导出失败', icon: 'none' });
        return;
      }

      const userId = this._getUserId();
      const sketchId = this.data.currentSketch && this.data.currentSketch.id;
      const title = this.data.currentSketch && this.data.currentSketch.title;
      const evaluation = this.data.evalResult ? JSON.stringify(this.data.evalResult) : '';

      wx.showLoading({ title: '保存到画室…' });
      wx.uploadFile({
        url: `${this.data.apiBaseUrl}/coloring/upload_work`,
        filePath: pngPath,
        name: 'file',
        formData: {
          user_id: userId,
          sketch_id: sketchId || '',
          title: title || '',
          evaluation,
        },
        timeout: 45000,
        success: (res) => {
          wx.hideLoading();
          let data = null;
          try {
            data = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
          } catch (e) {
            data = null;
          }
          if (res.statusCode === 200 && data && data.ok) {
            const wid = (data.work && data.work.work_id) || data.work_id || '';
            this.setData({
              saveResult: {
                ...this.data.saveResult,
                cloudStatus: '成功',
                cloudWorkId: wid,
              },
            });
            wx.showToast({ title: '已保存到画室', icon: 'success' });
            this._loadStudioWorks();
            return;
          }
          wx.showToast({ title: '保存失败', icon: 'none' });
        },
        fail: () => {
          wx.hideLoading();
          wx.showToast({ title: '保存失败', icon: 'none' });
        },
      });
    });
  },

  _saveToLocal() {
    // 先导出图片并尝试保存到系统相册，同时写入本地记录
    const reuse = this.data.lastExportPngPath;
    const exportOnce = (cb) => {
      if (reuse) cb(reuse);
      else this._exportToPNG(cb);
    };
    exportOnce((pngPath) => {
      if (!pngPath) {
        wx.showToast({ title: '导出失败', icon: 'none' });
        return;
      }

      const persistRecord = () => {
        const works = wx.getStorageSync('coloringWorks') || [];
        const recordId = `work_${Date.now()}`;
        const localRecordPath = `storage://coloringWorks/${recordId}`;
        works.push({
          id: recordId,
          sketch_id: this.data.currentSketch && this.data.currentSketch.id,
          title: this.data.currentSketch && this.data.currentSketch.title,
          timestamp: Date.now(),
          image_path: pngPath,
          local_record_path: localRecordPath,
          evaluation: this.data.evalResult
        });
        try {
          wx.setStorageSync('coloringWorks', works);
        } catch (e) {}
        return localRecordPath;
      };

      const onSaved = () => {
        const localRecordPath = persistRecord();
        this.setData({
          saveResult: {
            ...this.data.saveResult,
            localAlbumStatus: '成功',
            localRecordPath
          }
        });
        wx.showToast({ title: '已保存到本地', icon: 'success' });
      };

      wx.saveImageToPhotosAlbum({
        filePath: pngPath,
        success: onSaved,
        fail: () => {
          // 无相册权限时也保留本地记录，避免用户作品丢失
          const localRecordPath = persistRecord();
          this.setData({
            saveResult: {
              ...this.data.saveResult,
              localAlbumStatus: '失败（无权限）',
              localRecordPath
            }
          });
          wx.showToast({ title: '已保存记录（相册权限未开启）', icon: 'none' });
        }
      });
    });
  },

  _backToList() {
    this.setData({
      mode: 'list',
      showSaveDialog: false,
      showScore: false,
      currentSketch: null,
      hasColored: false,
      fillHistory: [],
      coloringProgressPercent: 0,
      progressThumbLeftPercent: 0,
      coloringProgressFilledPixels: 0,
      showReferenceModal: false,
      referenceAnswerUrl: '',
      saveResult: {
        cloudWorkId: '',
        cloudStatus: '',
        localAlbumStatus: '',
        localRecordPath: ''
      }
    });
  },

  // 返回列表
  backToList() {
    // 直接回到“画图题库”列表页（涂色小画家列表模式）
    this._backToList();
  },

  onUnload() {
    // 清理
    this._stopRackAutoScroll();
    this._clearCanvases();
  },

  _clearCanvases() {
    // 清理 Canvas 资源
    wx.createCanvasContext('paintCanvas', this).clearRect(0, 0, this.data.canvasWidth, this.data.canvasHeight);
  },

  _buildRegionColorMap(imageData) {
    const regions = (this.data.currentSketch && this.data.currentSketch.regions) || [];
    // 优先使用后端下发的 color_key -> region 索引，保证像素颜色能准确命中区域
    // 否则旧逻辑“采样颜色顺序取模”会导致 map=miss 或命中错区
    this._regionColorIndexMap = {};
    if (regions && regions.length) {
      let ok = 0;
      for (let i = 0; i < regions.length; i++) {
        const ck = regions[i] && regions[i].color_key;
        if (!ck) continue;
        this._regionColorIndexMap[String(ck)] = i;
        ok += 1;
      }
      if (ok > 0) return;
    }

    const colors = [];
    const seen = {};
    const data = imageData || [];

    for (let i = 0; i < data.length; i += 4) {
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      const a = data[i + 3];
      if (a < 10) continue;
      if (r > 245 && g > 245 && b > 245) continue;
      const key = `rgb(${r},${g},${b})`;
      if (!seen[key]) {
        seen[key] = true;
        colors.push(key);
      }
      if (colors.length >= Math.max(regions.length, 8)) break;
    }

    colors.forEach((key, idx) => {
      const mappedIdx = regions.length ? (idx % regions.length) : 0;
      this._regionColorIndexMap[key] = mappedIdx;
    });
  },

  _hexToRgb(hex) {
    if (!hex || typeof hex !== 'string') return null;
    let v = hex.replace('#', '');
    if (v.length === 3) {
      v = v.split('').map((c) => c + c).join('');
    }
    if (v.length !== 6) return null;
    const n = parseInt(v, 16);
    if (Number.isNaN(n)) return null;
    return {
      r: (n >> 16) & 255,
      g: (n >> 8) & 255,
      b: n & 255
    };
  },

  _normalizeHexColor(hex) {
    if (!hex || typeof hex !== 'string') return '';
    let v = hex.trim().replace(/^#/, '');
    if (v.length === 3) {
      v = v.split('').map((c) => c + c).join('');
    }
    if (!/^[0-9a-fA-F]{6}$/.test(v)) return '';
    return `#${v.toUpperCase()}`;
  },

  _colorDistance(hexA, hexB) {
    const a = this._hexToRgb(hexA);
    const b = this._hexToRgb(hexB);
    if (!a || !b) return Number.MAX_SAFE_INTEGER;
    const dr = a.r - b.r;
    const dg = a.g - b.g;
    const db = a.b - b.b;
    return Math.sqrt(dr * dr + dg * dg + db * db);
  },

  _getProgressThumbLeftPercent(percent) {
    const p = Number.isFinite(Number(percent)) ? Number(percent) : 0;
    // 进度滑块做边界夹紧，避免 100% 时气泡越过右边框
    return Math.max(4, Math.min(96, p));
  },

  _buildRecommendedColors(answerColors, fallbackPalette) {
    // 推荐色仅展示：答案色 + 最多 1 个干扰色
    const answer = Array.isArray(answerColors) ? answerColors : [];
    const fallback = Array.isArray(fallbackPalette) ? fallbackPalette : [];

    const used = {};
    const normalizedAnswer = [];
    answer.forEach((c) => {
      const h = this._normalizeHexColor(c);
      if (!h || used[h]) return;
      used[h] = true;
      normalizedAnswer.push(h);
    });

    // 无答案色时的兜底
    if (!normalizedAnswer.length) {
      const out = [];
      fallback.forEach((c) => {
        const h = this._normalizeHexColor(c);
        if (!h || used[h]) return;
        used[h] = true;
        out.push(h);
      });
      return out.slice(0, 3);
    }

    const base = normalizedAnswer.slice(0, 5);
    const pool = []
      .concat(this.data.colors || [])
      .concat(fallback || []);

    // 在候选池挑一个与答案色“整体最远”的颜色作为干扰色
    let distractor = '';
    let bestScore = -1;
    pool.forEach((c) => {
      const h = this._normalizeHexColor(c);
      if (!h || used[h]) return;
      let minDist = Number.MAX_SAFE_INTEGER;
      base.forEach((ac) => {
        const d = this._colorDistance(h, ac);
        if (d < minDist) minDist = d;
      });
      if (minDist > bestScore) {
        bestScore = minDist;
        distractor = h;
      }
    });

    const out = base.slice();
    if (distractor) out.push(distractor);
    return out;
  },

  // 线稿“墙”掩码：把黑线及其抗锯齿边缘加粗成墙
  // 这样 flood fill 的边界会更贴合你原来 regionmap 的效果（避免漏填/边界偏移）。
  _buildLineWallMask(w, h) {
    const source = this._baseLinePixels;
    if (!source) return;

    const cw = Math.floor(w);
    const ch = Math.floor(h);
    if (!cw || !ch) return;

    const wall = new Uint8Array(cw * ch);

    // 线条墙阈值：仅做像素判定，不做任何形态学膨胀/腐蚀。
    // 目的是严格在前端基于原线稿黑线做闭合填色。
    const WALL_GRAY_THRESHOLD = 180;

    const isDarkPixel = (r, g, b, a) => {
      if (!a || typeof a !== 'number') return false;
      // 与测试页保持一致：只把足够不透明的暗像素当作“墙”
      if (a < 128) return false;
      const gray = (r + g + b) / 3;
      return gray < WALL_GRAY_THRESHOLD;
    };

    // 第一步：初始“暗像素”标记
    for (let y = 0; y < ch; y++) {
      for (let x = 0; x < cw; x++) {
        const p = y * cw + x;
        const i = p * 4;
        const r = source[i];
        const g = source[i + 1];
        const b = source[i + 2];
        const a = source[i + 3];
        if (isDarkPixel(r, g, b, a)) wall[p] = 1;
      }
    }

    // 不做任何膨胀/腐蚀：严格使用原始“暗像素”作为墙
    // 这样边界不会因为形态学处理而与用户看到的线条错位。
    this._lineWallMask = wall;

    // 计算“可填充像素总量”：只统计不触边界的闭合连通域
    // 这样进度条不会因为存在很小/难点的小区域而变得不可理解（会自动停在真实完成度附近）。
    this._totalFillablePixels = this._computeTotalFillablePixels(cw, ch);
  },

  _computeTotalFillablePixels(w, h) {
    const wall = this._lineWallMask;
    if (!wall) return 0;

    const cw = Math.floor(w);
    const ch = Math.floor(h);
    const size = cw * ch;
    if (!cw || !ch || !size) return 0;

    // 访问标记：1 表示已访问（墙或非墙都会被标记，避免重复 BFS）
    const visited = new Uint8Array(size);
    let total = 0;

    // 用于 BFS 的栈（复用同一个数组，降低 GC 压力）
    const stack = [];

    for (let p = 0; p < size; p++) {
      if (visited[p]) continue;

      // 墙不算“可填充”
      if (wall[p]) {
        visited[p] = 1;
        continue;
      }

      // 从一个非墙像素开始做连通域 BFS
      visited[p] = 1;
      stack.length = 0;
      stack.push(p);

      let count = 0;
      let touchesBorder = false;

      while (stack.length) {
        const cp = stack.pop();
        const x = cp % cw;
        const y = (cp / cw) | 0;
        count += 1;

        if (x === 0 || y === 0 || x === cw - 1 || y === ch - 1) {
          touchesBorder = true;
        }

        // 4 邻域
        const nx0 = x - 1;
        const nx1 = x + 1;
        const ny0 = y - 1;
        const ny1 = y + 1;

        if (nx0 >= 0) {
          const np = y * cw + nx0;
          if (!visited[np] && !wall[np]) {
            visited[np] = 1;
            stack.push(np);
          }
        }
        if (nx1 < cw) {
          const np = y * cw + nx1;
          if (!visited[np] && !wall[np]) {
            visited[np] = 1;
            stack.push(np);
          }
        }
        if (ny0 >= 0) {
          const np = ny0 * cw + x;
          if (!visited[np] && !wall[np]) {
            visited[np] = 1;
            stack.push(np);
          }
        }
        if (ny1 < ch) {
          const np = ny1 * cw + x;
          if (!visited[np] && !wall[np]) {
            visited[np] = 1;
            stack.push(np);
          }
        }
      }

      // 不触边界的连通域才是“闭合区域”
      if (!touchesBorder) total += count;
    }

    return total;
  },

  _renderPaintPixels() {
    if (!this._paintPixels) return;
    wx.canvasPutImageData({
      canvasId: 'paintCanvas',
      data: this._paintPixels,
      x: 0,
      y: 0,
      width: Math.floor(this.data.canvasWidth),
      height: Math.floor(this.data.canvasHeight),
      success: () => {},
      fail: () => {}
    }, this);
  },

  _rebuildPaintPixels(fillHistory) {
    const source = this._baseLinePixels;
    if (!source) return;
    this._paintPixels = new Uint8ClampedArray(source.length);

    const w = Math.floor(this.data.canvasWidth);
    const h = Math.floor(this.data.canvasHeight);
    if (!w || !h) return;

    const wall = this._lineWallMask;

    // 使用基于线稿的闭合区域 flood fill：每条 fillHistory 记录一个起点和颜色
    const buf = this._paintPixels;

    const inBounds = (x, y) => x >= 0 && y >= 0 && x < w && y < h;

    const floodFill = (sx, sy, color) => {
      const rgb = this._hexToRgb(color);
      if (!rgb) return 0;
      const startIdx = (sy * w + sx) * 4;
      const a0 = source[startIdx + 3];
      if (!a0) return 0;

      const stack = [[sx, sy]];
      const visited = new Uint8Array(w * h);
      let filledCount = 0;

      while (stack.length) {
        const [x, y] = stack.pop();
        if (!inBounds(x, y)) continue;
        const p = y * w + x;
        if (visited[p]) continue;
        visited[p] = 1;

        if (wall && wall[p]) continue;
        const si = p * 4;
        if (!wall) {
          const a = source[si + 3];
          if (!a || a < 128) continue;
          const r = source[si], g = source[si + 1], b = source[si + 2];
          const gray = (r + g + b) / 3;
          if (gray < 140) continue;
        }

        buf[si] = rgb.r;
        buf[si + 1] = rgb.g;
        buf[si + 2] = rgb.b;
        buf[si + 3] = 200;
        filledCount += 1;

        stack.push([x + 1, y]);
        stack.push([x - 1, y]);
        stack.push([x, y + 1]);
        stack.push([x, y - 1]);
      }

      return filledCount;
    };

    let lastFilledCount = 0;
    (fillHistory || []).forEach((entry) => {
      if (typeof entry.x !== 'number' || typeof entry.y !== 'number') return;
      const cnt = floodFill(Math.floor(entry.x), Math.floor(entry.y), entry.color);
      if (typeof cnt === 'number') lastFilledCount = cnt;
    });

    this._lastFillCount = lastFilledCount;

    // 统计已涂色像素：buf 中 alpha>0 的像素数量就是“当前涂了多少”
    // 由于每次 rebuild 都从头重建，最终统计不会因为重复点击同一块而膨胀。
    let filledPixels = 0;
    const bufArr = this._paintPixels;
    for (let i = 3; i < bufArr.length; i += 4) {
      if (bufArr[i] > 0) filledPixels += 1;
    }
    const total = this._totalFillablePixels || 0;
    const percent = total > 0 ? Math.max(0, Math.min(100, Math.round((filledPixels * 100) / total))) : 0;
    const progressThumbLeftPercent = this._getProgressThumbLeftPercent(percent);

    if (
      this.data.coloringProgressPercent !== percent ||
      this.data.coloringProgressFilledPixels !== filledPixels ||
      this.data.progressThumbLeftPercent !== progressThumbLeftPercent
    ) {
      this.setData({
        coloringProgressPercent: percent,
        progressThumbLeftPercent,
        coloringProgressFilledPixels: filledPixels
      });
    }

    this._renderPaintPixels();
  }
});
