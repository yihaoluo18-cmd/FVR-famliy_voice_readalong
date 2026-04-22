const app = getApp();
const { resolveApiBase } = require("../../utils/api-base.js");
const { isMainDone } = require("../../utils/guide-flow.js");

// 分类书屋：按后端 magic_books/index 的 tags 动态生成；缺失类别则自动新建
const CATEGORY_STYLE_BY_TAG = {
  "综合推荐": { ghostIcon: "📚", bgColor: "#fff5f7", accentColor: "#f0a3c2", desc: "先从这里随便逛逛" },
  "家人最懂我": { ghostIcon: "🤝", bgColor: "#fffbeb", accentColor: "#fde68a", desc: "亲子陪伴的温暖时刻" },
  "好好说话好朋友": { ghostIcon: "🫶", bgColor: "#fff7fb", accentColor: "#fbcfe8", desc: "做更会表达的小朋友" },
  "我会照顾自己": { ghostIcon: "🪥", bgColor: "#fdf2f8", accentColor: "#e879a9", desc: "自理与习惯，从小开始" },
  "情绪小侦探": { ghostIcon: "💗", bgColor: "#fff5f7", accentColor: "#f472b6", desc: "认识情绪，学会安抚自己" },
  "安全小勇士": { ghostIcon: "🚦", bgColor: "#fffbeb", accentColor: "#fbbf24", desc: "安全规则也可以很有趣" },
  "自然与生命": { ghostIcon: "🌿", bgColor: "#f0fdf4", accentColor: "#86efac", desc: "观察世界，感受生命" },
  "魔法想象屋": { ghostIcon: "🪄", bgColor: "#fce7f3", accentColor: "#f0a3c2", desc: "想象力开门，故事出发" },
  "我在长大": { ghostIcon: "🌱", bgColor: "#fffbeb", accentColor: "#fcd34d", desc: "成长的每一步都很棒" },
};

function slugifyTag(tag) {
  const s = String(tag || "").trim();
  if (!s) return "";
  return s
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9\u4e00-\u9fa5\-]/g, "");
}

function parsePageCount(raw, fallbackFromPagesObj) {
  const fromNumber = Number(raw);
  if (Number.isFinite(fromNumber) && fromNumber > 0) return Math.floor(fromNumber);

  const text = String(raw || "").trim();
  if (text) {
    const m = text.match(/\d+/);
    if (m) {
      const n = Number(m[0]);
      if (Number.isFinite(n) && n > 0) return Math.floor(n);
    }
  }

  if (fallbackFromPagesObj && typeof fallbackFromPagesObj === "object") {
    const keys = Object.keys(fallbackFromPagesObj);
    if (keys.length) return keys.length;
  }
  return 0;
}

Page({
  data: {
    activeTab: 'featured',
    totalBooks: 0,
    aiStories: [],
    aiStoriesCount: 0,
    shelfBooks: [],
    shelfBooksCount: 0,
    shelfLoading: false,
    shelfError: '',
    shelfCategories: [],
    shelfCategoriesRender: [],
    activeShelfCategoryId: "mixed",
    categorizedShelfBooks: {},
    currentCategoryBooks: [],
    featuredPlanItems: [],
    featuredRecommendItems: [],
    featuredRecommendRenderItems: [],
    featuredRecentItems: [],
    todayPlanDateKey: "",
    recommendScrollLeft: 0,
    recommendScrollWithAnimation: true,
    recommendFloatingPaused: false,
    categoryScrollLeft: 0,
    categoryScrollWithAnimation: true,
    categoryFloatingPaused: false,
    rotateClass: 'rotateClass',
    showGuide: false,
    guideSteps: [],
    guideStepIndex: 0,
    guideHighlight: '',
    guideTitle: '',
    guideDesc: '',
  },

  onLoad() {
    try {
      const sys = wx.getSystemInfoSync();
      const w = Number(sys && sys.windowWidth) || 375;
      this._rpx2px = w / 750;
    } catch (e) {
      this._rpx2px = 0.5;
    }
    this.loadAIStories();
    this.loadShelfBooks();
    this._syncFeaturedSections();
    this._startRecommendAutoScroll();
  },

  onShow() {
    this.loadAIStories();
    this.loadShelfBooks();
    this._syncFeaturedSections();
    this._startRecommendAutoScroll();
    this.initBooksGuide();
  },

  onHide() {
    this._stopRecommendAutoScroll();
    this._stopCategoryAutoScroll();
  },

  onUnload() {
    this._stopRecommendAutoScroll();
    this._stopCategoryAutoScroll();
  },

  loadAIStories() {
    try {
      const stories = wx.getStorageSync('aiStories') || [];
      this.setData({
        aiStories: Array.isArray(stories) ? stories : [],
        aiStoriesCount: Array.isArray(stories) ? stories.length : 0,
      });
    } catch (e) {
      this.setData({ aiStories: [], aiStoriesCount: 0 });
    }
  },

  switchToFeatured() {
    this.setData({ activeTab: 'featured' });
  },

  switchToAI() {
    this.setData({ activeTab: 'ai' });
    this.loadAIStories();
    this._syncCurrentCategoryBooks();
  },

  openBook(e) {
    const bookId = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/read/read?id=${bookId}` });
  },

  goToAIStory() {
    wx.navigateTo({ url: '/pages/ai-story/ai-story' });
  },

  openAIStory(e) {
    const id = String((e.currentTarget.dataset && e.currentTarget.dataset.id) || '');
    if (!id) return;
    wx.navigateTo({ url: `/pages/ai-story-view/ai-story-view?id=${encodeURIComponent(id)}` });
  },

  deleteAIStory(e) {
    const id = String((e.currentTarget.dataset && e.currentTarget.dataset.id) || '');
    if (!id) return;

    wx.showModal({
      title: '删除这个故事？',
      content: '删除后可重新生成，不影响其他故事。',
      confirmText: '删除',
      confirmColor: '#ef4444',
      success: (res) => {
        if (!res.confirm) return;
        try {
          const stories = wx.getStorageSync('aiStories') || [];
          const kept = stories.filter((s) => String((s && s.id) || '') !== id);
          wx.setStorageSync('aiStories', kept);
          this.loadAIStories();
          wx.showToast({ title: '已删除', icon: 'success' });
        } catch (e2) {
          wx.showToast({ title: '删除失败', icon: 'none' });
        }
      }
    });
  },

  loadShelfBooks() {
    const base = resolveApiBase(app);
    this.setData({ shelfLoading: true, shelfError: '' });

    wx.request({
      url: `${base}/magic_books/index`,
      method: 'GET',
      success: (res) => {
        const data = res && res.data ? res.data : {};
        const items = Array.isArray(data.items) ? data.items : [];
        const normUrl = (u) => {
          const str = String(u || '');
          if (!str) return '';
          if (/^https?:\/\//i.test(str)) return str;
          if (str.startsWith('/')) return `${base}${str}`;
          return `${base}/${str}`;
        };

        const shelfBooks = items.map((b) => ({
          id: String(b.title || b.id || ''),
          title: String(b.title || '绘本'),
          coverImage: normUrl(b.cover_url || ''),
          tags: Array.isArray(b.tags) ? b.tags.map((t) => String(t || "").trim()).filter(Boolean) : [],
          icon: String((b && b.icon) || "").trim(),
          pages: parsePageCount(
            b.pages || b.page_count || b.pageCount || b.total_pages || b.totalPages || "",
            b.pages_obj || b.pagesObj || null
          ),
          createdDate: '',
        })).filter((x) => x.id);
        // 用于过滤掉本地旧缓存里的“测试绘本”
        this._shelfIdSet = shelfBooks.reduce((m, b) => {
          m[String(b.id || '')] = 1;
          return m;
        }, {});
        const { categories, byCat } = this._buildShelfCategoriesAndMap(shelfBooks);
        this.setData(
          {
            shelfBooks,
            shelfBooksCount: shelfBooks.length,
            totalBooks: shelfBooks.length,
            shelfCategories: categories,
            shelfCategoriesRender: this._buildCategoryRenderItems(categories),
            categorizedShelfBooks: byCat,
            activeShelfCategoryId: (categories[0] && categories[0].id) ? categories[0].id : "mixed",
            categoryScrollLeft: 0,
            categoryScrollWithAnimation: true,
          },
          () => {
          this._syncCurrentCategoryBooks();
          this._syncFeaturedSections();
          this._resetCategoryLoopPosition();
          this._startCategoryAutoScroll();
        });
      },
      fail: (err) => {
        this.setData({
          shelfBooks: [],
          shelfBooksCount: 0,
          totalBooks: 0,
          shelfCategories: [],
          shelfCategoriesRender: [],
          activeShelfCategoryId: "mixed",
          categoryScrollLeft: 0,
          categorizedShelfBooks: {},
          currentCategoryBooks: [],
          shelfError: (err && err.errMsg) ? String(err.errMsg) : '加载失败',
        });
        wx.showToast({ title: '绘本集加载失败', icon: 'none' });
      },
      complete: () => {
        this.setData({ shelfLoading: false });
      }
    });
  },

  openShelfBook(e) {
    const bookId = String((e.currentTarget.dataset && e.currentTarget.dataset.id) || '');
    if (!bookId) return;
    wx.navigateTo({ url: `/pages/read/read?id=${encodeURIComponent(bookId)}&source=library` });
  },

  refreshShelfBooks() {
    this.loadShelfBooks();
  },

  openPlannedBook(e) {
    const d = (e && e.currentTarget && e.currentTarget.dataset) ? e.currentTarget.dataset : {};
    const bookId = String(d.id || "").trim();
    if (!bookId) return;
    const source = String(d.source || "").trim();
    const page = Math.max(0, Number(d.page || 0) || 0);
    const query = source === "library"
      ? `id=${encodeURIComponent(bookId)}&source=library&startPage=${page}`
      : `id=${encodeURIComponent(bookId)}&startPage=${page}`;
    wx.navigateTo({ url: `/pages/read/read?${query}` });
  },

  openRecentBook(e) {
    const d = (e && e.currentTarget && e.currentTarget.dataset) ? e.currentTarget.dataset : {};
    const bookId = String(d.id || "").trim();
    if (!bookId) return;
    const source = String(d.source || "").trim();
    const page = Math.max(0, Number(d.page || 0) || 0);
    const query = source === "library"
      ? `id=${encodeURIComponent(bookId)}&source=library&startPage=${page}`
      : `id=${encodeURIComponent(bookId)}&startPage=${page}`;
    wx.navigateTo({ url: `/pages/read/read?${query}` });
  },

  onSelectShelfCategory(e) {
    const cid = String((e.currentTarget.dataset && e.currentTarget.dataset.cid) || '');
    if (!cid || cid === this.data.activeShelfCategoryId) return;
    this.setData({ activeShelfCategoryId: cid }, () => this._syncCurrentCategoryBooks());
  },

  _buildShelfCategoriesAndMap(shelfBooks) {
    const books = Array.isArray(shelfBooks) ? shelfBooks : [];
    const byCat = {};
    const tagToCount = {};
    const push = (cid, book) => {
      if (!Array.isArray(byCat[cid])) byCat[cid] = [];
      byCat[cid].push(book);
    };

    // 综合推荐：包含所有书，固定放第一
    const mixedId = "mixed";
    byCat[mixedId] = [];
    books.forEach((b) => push(mixedId, b));

    // 真实分类：按后端 tags 分组；无 tags -> 未分类
    books.forEach((b) => {
      const tags = Array.isArray(b.tags) ? b.tags : [];
      if (!tags.length) {
        const t = "未分类";
        const cid = `tag-${slugifyTag(t) || "uncat"}`;
        tagToCount[t] = (tagToCount[t] || 0) + 1;
        push(cid, b);
        return;
      }
      tags.forEach((tRaw) => {
        const t = String(tRaw || "").trim();
        if (!t) return;
        const cid = `tag-${slugifyTag(t) || t}`;
        tagToCount[t] = (tagToCount[t] || 0) + 1;
        push(cid, b);
      });
    });

    const buildCat = (title, idOverride) => {
      const style = CATEGORY_STYLE_BY_TAG[title] || null;
      const baseHue = Math.abs(title.split("").reduce((s, ch) => s + ch.charCodeAt(0), 0)) % 360;
      const bg = style && style.bgColor
        ? style.bgColor
        : `hsl(${baseHue} 60% 94%)`;
      const accent = style && style.accentColor
        ? style.accentColor
        : `hsl(${baseHue} 75% 62%)`;
      const ghostIcon = (style && style.ghostIcon) ? style.ghostIcon : "🏠";
      const desc = (style && style.desc) ? style.desc : "来看看这一类的故事";
      return {
        id: idOverride || `tag-${slugifyTag(title) || title}`,
        title,
        desc,
        ghostIcon,
        bgColor: bg,
        accentColor: accent,
      };
    };

    const cats = [];
    cats.push(buildCat("综合推荐", mixedId));
    const tagsSorted = Object.keys(tagToCount).sort((a, b) => (tagToCount[b] || 0) - (tagToCount[a] || 0));
    tagsSorted.forEach((t) => {
      const cid = `tag-${slugifyTag(t) || t}`;
      cats.push(buildCat(t, cid));
    });

    // 只有综合推荐时，默认 active 为 mixed
    return { categories: cats, byCat };
  },

  _buildCategoryRenderItems(categories) {
    const list = Array.isArray(categories) ? categories : [];
    if (!list.length) return [];
    const triple = [...list, ...list, ...list];
    return triple.map((it, i) => ({ ...it, __k: `${String(it.id || 'c')}_${i}` }));
  },

  _syncCurrentCategoryBooks() {
    const cid = String(this.data.activeShelfCategoryId || "mixed");
    const m = this.data.categorizedShelfBooks || {};
    const listRaw = Array.isArray(m[cid]) ? m[cid] : [];
    const list = listRaw.map((b) => {
      const pages = Number((b && b.pages) || 0) || 0;
      return {
        ...b,
        pagesText: pages > 0 ? `${pages}页` : '未知页数',
      };
    });
    const allCats = (this.data.shelfCategories || []).map((c) => {
      const count = Array.isArray(m[c.id]) ? m[c.id].length : 0;
      const done = count > 0
        ? (Array.isArray(m[c.id]) ? m[c.id].filter((b) => String((b && b.createdDate) || '').trim().length > 0).length : 0)
        : 0;
      const progress = count > 0 ? Math.max(8, Math.min(100, Math.round((done / count) * 100))) : 0;
      return { ...c, count, progress };
    });
    this.setData({
      shelfCategories: allCats,
      shelfCategoriesRender: this._buildCategoryRenderItems(allCats),
      currentCategoryBooks: list,
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

  _syncFeaturedSections() {
    const dateKey = this._dateKey();
    const idSet = (this._shelfIdSet && typeof this._shelfIdSet === "object") ? this._shelfIdSet : {};
    const pool = this._buildFeaturedBookPool();
    const poolMap = pool.reduce((m, b) => {
      const id = String((b && b.bookId) || "");
      if (id) m[id] = b;
      return m;
    }, {});

    // 只保留后端书库里存在的记录，避免旧缓存“测试绘本”冒出来
    const recentRaw = this._loadRecentReadingRecords();
    const recent = recentRaw
      .filter((r) => {
        if (!r) return false;
        const bid = String((r && r.bookId) || "");
        if (!idSet[bid]) return false;
        // 兼容历史记录：source 为空也视为后端库记录
        const src = String((r && r.source) || "").trim();
        return !src || src === "library";
      })
      .map((r) => {
        const ref = poolMap[String(r.bookId || "")];
        return ref ? { ...r, source: "library", title: ref.title, coverImage: ref.coverImage } : r;
      });

    const plansRaw = this._loadFeaturedReadingPlans(dateKey, recent);
    const plans = plansRaw
      .map((p) => {
        const id = String((p && p.bookId) || "");
        const ref = poolMap[id];
        if (!id || !ref) return null;
        return {
          ...p,
          bookId: id,
          source: "library",
          title: ref.title,
          coverImage: ref.coverImage,
          totalPages: ref.totalPages,
        };
      })
      .filter(Boolean);

    const recommends = this._buildDailyRecommendItems(dateKey, plans);
    const picked = recommends.slice(0, 12);
    const render = this._buildRecommendRenderItems(picked);
    this.setData(
      {
        todayPlanDateKey: dateKey,
        featuredRecommendItems: picked,
        featuredRecommendRenderItems: render,
        featuredRecentItems: recent.slice(0, 4),
        featuredPlanItems: plans.slice(0, 4),
      },
      () => this._resetRecommendLoopPosition()
    );
  },

  _buildDailyRecommendItems(dateKey, plans) {
    const poolMap = this._buildFeaturedBookPool().reduce((m, b) => {
      const id = String((b && b.bookId) || "");
      if (id) m[id] = b;
      return m;
    }, {});
    const fromPlans = (Array.isArray(plans) ? plans : []).map((p) => {
      const id = String((p && p.bookId) || "");
      const ref = poolMap[id];
      if (!id || !ref) return null;
      return {
        bookId: id,
        title: ref.title,
        coverImage: ref.coverImage,
        source: "library",
        currentPageIndex: Math.max(0, Number((p && p.currentPageIndex) || 0) || 0),
      };
    }).filter(Boolean);

    const pool = this._buildFeaturedBookPool().map((p) => ({
      bookId: String(p.bookId || ""),
      title: String(p.title || "绘本"),
      coverImage: String(p.coverImage || ""),
      source: String(p.source || ""),
      currentPageIndex: 0,
    })).filter((x) => x.bookId && x.coverImage);

    const seedPicked = this._pickDailyRecommendedBooks(pool, 8, dateKey);
    const merged = [...fromPlans, ...seedPicked];
    const seen = {};
    return merged.filter((x) => {
      if (!x.bookId || seen[x.bookId]) return false;
      seen[x.bookId] = 1;
      return true;
    });
  },

  _buildRecommendRenderItems(items) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) return [];
    const triple = [...list, ...list, ...list];
    return triple.map((it, i) => ({ ...it, __k: `${String(it.bookId || 'b')}_${i}` }));
  },

  _recommendBaseCount() {
    const base = Array.isArray(this.data.featuredRecommendItems) ? this.data.featuredRecommendItems.length : 0;
    return Math.max(0, base);
  },

  _recommendSegmentWidthPx() {
    const n = this._recommendBaseCount();
    return Math.max(0, n * this._recommendItemStepPx());
  },

  _recommendScrollOffsetPx() {
    const rpx2px = Number(this._rpx2px || 0) || 0.5;
    // 与 wxss: .recommend-shelf-row padding-left 18rpx 保持一致
    return Math.max(0, Math.round(18 * rpx2px));
  },

  _resetRecommendLoopPosition() {
    const seg = this._recommendSegmentWidthPx();
    if (seg <= 0) return;
    const off = this._recommendScrollOffsetPx();
    const start = off + seg; // 中间段开头
    this._recommendScrollLeft = start;
    this.setData({ recommendScrollLeft: start });
  },

  _ensureRecommendLoopInMiddle() {
    const seg = this._recommendSegmentWidthPx();
    if (seg <= 0) return null;
    const off = this._recommendScrollOffsetPx();
    let cur = Number(this._recommendScrollLeft || this.data.recommendScrollLeft || 0) || 0;
    const min = off + seg;
    const max = off + seg * 2;
    if (cur >= max) cur -= seg;
    if (cur < min) cur += seg;
    this._recommendScrollLeft = cur;
    return cur;
  },

  _startRecommendAutoScroll() {
    this._stopRecommendAutoScroll();
    const itemCount = this._recommendBaseCount();
    if (itemCount <= 3) return;
    if (!Array.isArray(this.data.featuredRecommendRenderItems) || this.data.featuredRecommendRenderItems.length < itemCount * 3) return;
    this._recommendAutoTimer = setInterval(() => {
      if (this._recommendUserTouching) return;
      const seg = this._recommendSegmentWidthPx();
      if (seg <= 0) return;
      const cur0 = Number(this._recommendScrollLeft || this.data.recommendScrollLeft || 0) || 0;
      const cur = this._ensureRecommendLoopInMiddle() ?? cur0;
      let next = cur + this._recommendItemStepPx();

      // 到右边界时无动画回跳一个段宽，实现单向无限滚动
      const off = this._recommendScrollOffsetPx();
      const max = off + seg * 2;
      if (next >= max) {
        const jumped = next - seg;
        this._recommendScrollLeft = jumped;
        this.setData({ recommendScrollWithAnimation: false, recommendScrollLeft: jumped }, () => {
          this.setData({ recommendScrollWithAnimation: true });
        });
        return;
      }
      this._recommendScrollLeft = next;
      this.setData({ recommendScrollLeft: next });
    }, 1600);
  },

  _stopRecommendAutoScroll() {
    if (this._recommendAutoTimer) {
      clearInterval(this._recommendAutoTimer);
      this._recommendAutoTimer = null;
    }
  },

  _recommendItemStepPx() {
    const rpx2px = Number(this._rpx2px || 0) || 0.5;
    // 对应 wxss: 192rpx 宽 + 18rpx gap
    return Math.max(1, Math.round((192 + 18) * rpx2px));
  },

  _recommendViewportApproxPx() {
    const rpx2px = Number(this._rpx2px || 0) || 0.5;
    // board 左右 padding 14rpx + 14rpx，预留一点安全边距
    return Math.max(1, Math.round((750 - 32 * 2 - 14 * 2) * rpx2px));
  },

  // ===== 分类书屋：自动单向无限滚动（逻辑同每日推荐） =====
  _categoryBaseCount() {
    const base = Array.isArray(this.data.shelfCategories) ? this.data.shelfCategories.length : 0;
    return Math.max(0, base);
  },

  _categoryItemStepPx() {
    const rpx2px = Number(this._rpx2px || 0) || 0.5;
    // 对应 wxss: .category-house-card width 248rpx + gap 22rpx
    return Math.max(1, Math.round((248 + 22) * rpx2px));
  },

  _categoryScrollOffsetPx() {
    const rpx2px = Number(this._rpx2px || 0) || 0.5;
    // 对应 wxss: .category-houses-row padding-left 8rpx
    return Math.max(0, Math.round(8 * rpx2px));
  },

  _categorySegmentWidthPx() {
    const n = this._categoryBaseCount();
    return Math.max(0, n * this._categoryItemStepPx());
  },

  _resetCategoryLoopPosition() {
    const seg = this._categorySegmentWidthPx();
    if (seg <= 0) return;
    const off = this._categoryScrollOffsetPx();
    const start = off + seg;
    this._categoryScrollLeft = start;
    this.setData({ categoryScrollLeft: start });
  },

  _ensureCategoryLoopInMiddle() {
    const seg = this._categorySegmentWidthPx();
    if (seg <= 0) return null;
    const off = this._categoryScrollOffsetPx();
    let cur = Number(this._categoryScrollLeft || this.data.categoryScrollLeft || 0) || 0;
    const min = off + seg;
    const max = off + seg * 2;
    if (cur >= max) cur -= seg;
    if (cur < min) cur += seg;
    this._categoryScrollLeft = cur;
    return cur;
  },

  _startCategoryAutoScroll() {
    this._stopCategoryAutoScroll();
    const n = this._categoryBaseCount();
    if (n <= 2) return;
    if (!Array.isArray(this.data.shelfCategoriesRender) || this.data.shelfCategoriesRender.length < n * 3) return;
    this._categoryAutoTimer = setInterval(() => {
      if (this._categoryUserTouching) return;
      const seg = this._categorySegmentWidthPx();
      if (seg <= 0) return;
      const cur0 = Number(this._categoryScrollLeft || this.data.categoryScrollLeft || 0) || 0;
      const cur = this._ensureCategoryLoopInMiddle() ?? cur0;
      let next = cur + this._categoryItemStepPx();
      const off = this._categoryScrollOffsetPx();
      const max = off + seg * 2;
      if (next >= max) {
        const jumped = next - seg;
        this._categoryScrollLeft = jumped;
        this.setData({ categoryScrollWithAnimation: false, categoryScrollLeft: jumped }, () => {
          this.setData({ categoryScrollWithAnimation: true });
        });
        return;
      }
      this._categoryScrollLeft = next;
      this.setData({ categoryScrollLeft: next });
    }, 2000);
  },

  _stopCategoryAutoScroll() {
    if (this._categoryAutoTimer) {
      clearInterval(this._categoryAutoTimer);
      this._categoryAutoTimer = null;
    }
  },

  onCategoryScroll(e) {
    const x = Number((e && e.detail && e.detail.scrollLeft) || 0) || 0;
    this._categoryScrollLeft = Math.max(0, x);
  },

  onCategoryTouchStart() {
    this._categoryUserTouching = true;
    this.setData({ categoryFloatingPaused: true });
    this._stopCategoryAutoScroll();
  },

  onCategoryTouchEnd() {
    this._categoryUserTouching = false;
    const n = this._categoryBaseCount();
    const step = this._categoryItemStepPx();
    const seg = this._categorySegmentWidthPx();
    const off = this._categoryScrollOffsetPx();
    const cur = Number(this._categoryScrollLeft || this.data.categoryScrollLeft || 0) || 0;
    if (!n || seg <= 0 || step <= 0) {
      this._startCategoryAutoScroll();
      return;
    }
    const rawIdx = Math.round((cur - off) / step);
    const k = ((rawIdx % n) + n) % n;
    const target = off + seg + k * step;
    this._categoryScrollLeft = target;
    const normalized = this._ensureCategoryLoopInMiddle() ?? target;
    this.setData({ categoryScrollLeft: normalized, categoryFloatingPaused: false }, () => this._startCategoryAutoScroll());
  },

  onRecommendScroll(e) {
    const x = Number((e && e.detail && e.detail.scrollLeft) || 0) || 0;
    // 滚动过程中不要 setData（会导致卡顿），只记录到内存
    this._recommendScrollLeft = Math.max(0, x);
  },

  onRecommendTouchStart() {
    this._recommendUserTouching = true;
    this.setData({ recommendFloatingPaused: true });
    this._stopRecommendAutoScroll();
  },

  onRecommendTouchEnd() {
    this._recommendUserTouching = false;
    const n = this._recommendBaseCount();
    const step = this._recommendItemStepPx();
    const seg = this._recommendSegmentWidthPx();
    const off = this._recommendScrollOffsetPx();
    const cur = Number(this._recommendScrollLeft || this.data.recommendScrollLeft || 0) || 0;
    if (!n || seg <= 0 || step <= 0) {
      this.setData({ recommendFloatingPaused: false }, () => this._startRecommendAutoScroll());
      return;
    }
    // cur 对齐到“最近一本书的封面起点”，并始终吸附到中间段
    const rawIdx = Math.round((cur - off) / step);
    const k = ((rawIdx % n) + n) % n;
    const target = off + seg + k * step;
    this._recommendScrollLeft = target;
    const normalized = this._ensureRecommendLoopInMiddle() ?? target;
    this.setData({ recommendScrollLeft: normalized, recommendFloatingPaused: false }, () => this._startRecommendAutoScroll());
  },

  _loadRecentReadingRecords() {
    try {
      const raw = wx.getStorageSync("readingRecent");
      const list = Array.isArray(raw) ? raw : [];
      return list
        .map((r) => {
          const title = String((r && r.title) || "绘本");
          const pageIndex = Math.max(0, Number((r && r.pageIndex) || 0) || 0);
          const totalPages = Math.max(1, Number((r && r.totalPages) || 1) || 1);
          const progressPercent = Math.max(0, Math.min(100, Math.round(((pageIndex + 1) / totalPages) * 100)));
          const theme = this._resolveCategoryTheme(title);
          return {
            bookId: String((r && r.bookId) || "").trim(),
            title,
            coverImage: String((r && r.coverImage) || ""),
            source: String((r && r.source) || ""),
            pageIndex,
            totalPages,
            progressPercent,
            encourageText: this._resolveEncourageText(progressPercent),
            continueBgColor: String(theme.bgColor || "#eef5e9"),
            progressColor: String(theme.accentColor || "#7ba8ff"),
            updatedAt: Number((r && r.updatedAt) || 0) || 0,
          };
        })
        .filter((x) => !!x.bookId)
        .sort((a, b) => b.updatedAt - a.updatedAt);
    } catch (e) {
      return [];
    }
  },

  _resolveCategoryTheme(title) {
    const txt = String(title || "").toLowerCase();
    const cats = Array.isArray(this.data.shelfCategories) ? this.data.shelfCategories : [];
    if (!cats.length) return { bgColor: "#f2eef8", accentColor: "#80abff" };

    // 优先命中“标题包含分类名”的动态分类
    for (let i = 0; i < cats.length; i += 1) {
      const c = cats[i];
      const ctitle = String((c && c.title) || "").toLowerCase();
      if (!ctitle || ctitle === "综合推荐") continue;
      if (txt.includes(ctitle)) return c;
    }

    // 其次按预设风格 tag 名做包含匹配
    const tagNames = Object.keys(CATEGORY_STYLE_BY_TAG).filter((k) => k && k !== "综合推荐");
    for (let i = 0; i < tagNames.length; i += 1) {
      const t = String(tagNames[i] || "").toLowerCase();
      if (!t) continue;
      if (txt.includes(t)) {
        const hit = cats.find((c) => String((c && c.title) || "").toLowerCase() === t);
        if (hit) return hit;
      }
    }

    return cats.find((c) => c.id === "mixed") || cats[0] || { bgColor: "#f2eef8", accentColor: "#80abff" };
  },

  _resolveEncourageText(progressPercent) {
    const p = Number(progressPercent || 0) || 0;
    if (p >= 85) return "快完成啦";
    if (p >= 55) return "继续保持";
    if (p >= 25) return "Keep it up!";
    return "今天继续加油";
  },

  _loadFeaturedReadingPlans(dateKey, recentList) {
    const storageKey = `readingPlans.${dateKey}`;
    const readingMinutesToday = this._getReadingMinutesToday(dateKey);
    const recents = Array.isArray(recentList) ? recentList : [];
    const recentMap = {};
    recents.forEach((r) => { recentMap[r.bookId] = r; });
    let plansRaw = [];
    try {
      const cached = wx.getStorageSync(storageKey);
      plansRaw = Array.isArray(cached) ? cached : [];
    } catch (e) {}
    if (!plansRaw.length) {
      plansRaw = this._buildDefaultPlans();
      try { wx.setStorageSync(storageKey, plansRaw); } catch (e) {}
    }
    const planCount = Math.max(1, plansRaw.length);
    const perPlanMinutes = Math.max(0, Math.round(readingMinutesToday / planCount));
    return plansRaw.map((p) => {
      const id = String((p && p.bookId) || "");
      const totalPages = Math.max(1, Number((p && p.totalPages) || 1) || 1);
      const targetPage = Math.max(1, Math.min(totalPages, Number((p && p.targetPage) || 1) || 1));
      const targetMinutes = Math.max(5, Number((p && p.targetMinutes) || 10) || 10);
      const last = recentMap[id] || null;
      const currentPageIndex = last ? Math.max(0, Number(last.pageIndex || 0) || 0) : 0;
      const currentPage = last ? currentPageIndex + 1 : 0;
      const pageProgress = Math.max(0, Math.min(100, Math.round((currentPage / targetPage) * 100)));
      const timeProgress = Math.max(0, Math.min(100, Math.round((perPlanMinutes / targetMinutes) * 100)));
      return {
        ...p,
        targetPage,
        targetMinutes,
        currentPageIndex,
        currentPage,
        currentMinutes: perPlanMinutes,
        pageProgress,
        timeProgress,
      };
    });
  },

  _buildDefaultPlans() {
    const pool = this._buildFeaturedBookPool();
    const favorites = (app && app.globalData && Array.isArray(app.globalData.favorites))
      ? app.globalData.favorites
      : [];
    const favIds = favorites.map((f) => String((f && f.id) || "").trim()).filter(Boolean);
    let chosen = pool.filter((b) => favIds.includes(String(b.bookId)));
    if (!chosen.length) {
      chosen = this._pickDailyRecommendedBooks(pool, 2, this._dateKey());
    }
    return chosen.slice(0, 4).map((b, idx) => {
      const totalPages = Math.max(1, Number(b.totalPages || 1) || 1);
      const targetPage = Math.max(1, Math.min(totalPages, Math.ceil(totalPages * (0.35 + idx * 0.08))));
      return {
        bookId: b.bookId,
        title: b.title,
        coverImage: b.coverImage,
        source: b.source,
        totalPages,
        targetPage,
        targetMinutes: Math.max(10, Math.round(targetPage * 1.8)),
      };
    });
  },

  _buildFeaturedBookPool() {
    const shelf = (Array.isArray(this.data.shelfBooks) ? this.data.shelfBooks : []).map((b) => ({
      bookId: String((b && b.id) || ""),
      title: String((b && b.title) || "绘本"),
      coverImage: String((b && b.coverImage) || ""),
      totalPages: Number((b && b.pages) || 0) || 1,
      source: "library",
    }));
    const seen = {};
    return [...shelf].filter((b) => {
      if (!b.bookId || seen[b.bookId]) return false;
      seen[b.bookId] = 1;
      return true;
    });
  },

  _pickDailyRecommendedBooks(pool, count, dateKey) {
    const list = Array.isArray(pool) ? pool.slice() : [];
    if (!list.length) return [];
    const seed = String(dateKey || "")
      .split("")
      .reduce((s, ch) => s + ch.charCodeAt(0), 0);
    return list
      .map((item, idx) => ({ item, score: (seed + idx * 37 + item.bookId.length * 13) % 997 }))
      .sort((a, b) => a.score - b.score)
      .slice(0, Math.max(1, Number(count) || 1))
      .map((x) => x.item);
  },

  _getReadingMinutesToday(dateKey) {
    try {
      const key = `readingMinutes.${dateKey}`;
      return Math.max(0, Number(wx.getStorageSync(key) || 0) || 0);
    } catch (e) {
      return 0;
    }
  },

  initBooksGuide() {
    if (!isMainDone("voiceDone")) return;
    if (isMainDone("readDone")) return;
    const steps = [
      {
        highlight: 'recommend',
        title: '选择一本绘本开始听读',
        desc: '先从推荐书架点开一本，进入阅读页体验音色朗读。',
      },
      {
        highlight: 'recent',
        title: '阅读进度会自动记录',
        desc: '读到哪里都会保存，下次可从最近阅读继续。',
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
