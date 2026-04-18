const app = getApp();
const { calculateLevel, MAX_LEVEL } = require('../../utils/star-level.js');

Page({
  data: {
    isLoggedIn: false,
    stars: 0,
    level: 1,
    levelTitle: '萌芽读者',
    levelIcon: '📖',
    
    // 升级进度
    hasNextLevel: true,
    progressPercent: 0,
    starsToNextLevel: 50,
    
    // 统计数据
    booksReadCount: 0,
    gamesCompletedCount: 0,
    achievementsUnlockedCount: 0,
    
    // 列表数据
    booksRead: [],
    gamesCompleted: [],
    achievements: [], // 成就会动态计算
  },

  onLoad() {
    this.loadData();
  },

  onShow() {
    this.loadData();
  },

  // 加载数据：区分登录/未登录状态
  loadData() {
    const isLoggedIn = app.globalData.isLoggedIn;
    this.setData({ isLoggedIn });

    if (!isLoggedIn) {
      // 未登录：重置为0，成就全部锁定
      this.setData({
        stars: 0,
        level: 1,
        levelTitle: '萌芽读者',
        levelIcon: '📖',
        hasNextLevel: true,
        progressPercent: 0,
        starsToNextLevel: 50,
        booksReadCount: 0,
        gamesCompletedCount: 0,
        booksRead: [],
        gamesCompleted: [],
        achievements: this.getAchievements(true), // 强制全部锁着
        achievementsUnlockedCount: 0,
      });
      return;
    }

    // 已登录：从全局数据读取真实用户数据
    const stars = app.globalData.stars || 0;
    const levelInfo = calculateLevel(stars);
    const booksRead = this._getRecentBooksFromStorage();
    const gamesCompleted = this._getCompletedGamesFromStorage();

    // 生成真实成就状态
    const realAchievements = this.getAchievements(false);
    const unlockedCount = realAchievements.filter(a => a.unlocked).length;

    this.setData({
      stars: stars,
      level: levelInfo.level,
      levelTitle: levelInfo.title,
      levelIcon: levelInfo.icon,
      hasNextLevel: levelInfo.level < MAX_LEVEL,
      progressPercent: levelInfo.progressPercent,
      starsToNextLevel: levelInfo.starsToNextLevel,
      booksReadCount: booksRead.length,
      gamesCompletedCount: gamesCompleted.length,
      booksRead: booksRead,
      gamesCompleted: gamesCompleted,
      achievements: realAchievements,
      achievementsUnlockedCount: unlockedCount,
    });
  },

  // ======================
  // 核心：真实成就系统
  // ======================
  getAchievements(forceLocked) {
    const gd = app.globalData;
    const totalStars = gd.stars || 0;
    const totalBooks = gd.totalBooks || 0;
    const readDays = gd.readDays || 0;
    const coloringCount = gd.coloringWorks || 0;

    return [
      {
        icon: "🏆",
        label: "阅读小达人",
        desc: "连续阅读7天",
        unlocked: forceLocked ? false : readDays >= 7,
      },
      {
        icon: "🎨",
        label: "涂色大师",
        desc: "完成10幅涂色",
        unlocked: forceLocked ? false : coloringCount >= 10,
      },
      {
        icon: "⭐",
        label: "星星收藏家",
        desc: "获得50颗星",
        unlocked: forceLocked ? false : totalStars >= 50,
      },
      {
        icon: "📚",
        label: "故事王",
        desc: "阅读30本绘本",
        unlocked: forceLocked ? false : totalBooks >= 30,
      },
    ];
  },

  // ======================
  // 本地存储读取（阅读记录）
  // ======================
  _getRecentBooksFromStorage() {
    try {
      const raw = wx.getStorageSync('readingRecent');
      const list = Array.isArray(raw) ? raw : [];
      return list.slice(0, 4).map(item => ({
        id: item.bookId,
        title: item.title || '未知绘本',
        date: item.date || this._formatDate(new Date()),
        stars: item.stars || 0,
        progress: item.progress || 0,
        emoji: item.emoji || '📚'
      }));
    } catch (e) {
      return [];
    }
  },

  // ======================
  // 本地存储读取（游戏记录）
  // ======================
  _getCompletedGamesFromStorage() {
    try {
      const raw = wx.getStorageSync('gamesCompleted');
      const list = Array.isArray(raw) ? raw : [];
      return list.slice(0, 3).map(item => ({
        id: item.id,
        title: item.title || '未知游戏',
        date: item.date || this._formatDate(new Date()),
        stars: item.stars || 0,
        type: item.type || 'other',
        typeLabel: item.typeLabel || '其他'
      }));
    } catch (e) {
      return [];
    }
  },

  // 日期格式化
  _formatDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  },

  // 查看全部书籍
  seeAllBooks() {
    wx.switchTab({
      url: '/pages/books/books'
    });
  },
});