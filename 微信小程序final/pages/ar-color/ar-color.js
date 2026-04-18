const app = getApp();
const { toMiniprogramAssetUrl } = require("../../utils/asset-url.js");

const PROCESS_TIPS = [
  '🔍 识别涂色角色中...',
  '🎨 分析颜色搭配...',
  '✨ 注入魔法能量...',
  '🌟 让角色动起来...',
  '🎉 魔法即将完成！',
];

Page({
  data: {
    step: 'upload',        // 'upload' | 'processing' | 'ar' | 'complete'
    uploadedImage: '',
    progress: 0,
    processTip: PROCESS_TIPS[0],
    planeDetected: false,
    floatClass: '',
    coloringWorks: 0,
    cameraError: false,
    arColorBackIcon: toMiniprogramAssetUrl("/assets/images/返回.png"),
  },

  onLoad() {
    const works = wx.getStorageSync('coloringWorks') || 0;
    this.setData({ coloringWorks: works });
  },

  onUnload() {
    this._clearProcessTimer();
    if (this._vkSession) {
      try { this._vkSession.stop(); } catch (e) { /* noop */ }
    }
  },

  // ─── 图片选择 ───
  choosePhoto() {
    // 点卡片时弹出选择（相册+相机二合一）
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        this.setData({ uploadedImage: res.tempFilePaths[0] });
        wx.vibrateShort();
      },
    });
  },

  takePhoto() {
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['camera'],
      success: (res) => {
        this.setData({ uploadedImage: res.tempFilePaths[0] });
        wx.vibrateShort();
      },
    });
  },

  chooseAlbum() {
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album'],
      success: (res) => {
        this.setData({ uploadedImage: res.tempFilePaths[0] });
        wx.vibrateShort();
      },
    });
  },

  // ─── 开始 AR 流程 ───
  startAR() {
    if (!this.data.uploadedImage) return;

    this.setData({ step: 'processing', progress: 0 });
    wx.vibrateShort();

    let progress = 0;
    let tipIdx = 0;

    this._processTimer = setInterval(() => {
      progress += Math.random() * 4 + 1;
      tipIdx = Math.min(Math.floor(progress / 20), PROCESS_TIPS.length - 1);

      if (progress >= 100) {
        progress = 100;
        this._clearProcessTimer();
        this.setData({ progress: 100, processTip: PROCESS_TIPS[4] });
        setTimeout(() => {
          this.setData({ step: 'ar' });
          this._initARScene();
        }, 600);
        return;
      }

      this.setData({
        progress: Math.min(Math.floor(progress), 99),
        processTip: PROCESS_TIPS[tipIdx],
      });
    }, 150);
  },

  _clearProcessTimer() {
    if (this._processTimer) {
      clearInterval(this._processTimer);
      this._processTimer = null;
    }
  },

  // ─── AR 场景初始化 ───
  _initARScene() {
    // 尝试使用 VisionKit 平面检测
    if (wx.createVKSession) {
      try {
        const session = wx.createVKSession({
          track: { plane: { mode: 1 } },
          version: 'v1',
          gl: null,
        });
        session.start((err) => {
          if (err) {
            this._fallbackARScene();
            return;
          }
          this._vkSession = session;
          session.on('updateAnchors', (anchors) => {
            if (!this.data.planeDetected && anchors && anchors.length > 0) {
              this.setData({ planeDetected: true, floatClass: 'floatAnim' });
              wx.vibrateShort();
            }
          });
        });
      } catch (e) {
        this._fallbackARScene();
      }
    } else {
      this._fallbackARScene();
    }
  },

  _fallbackARScene() {
    // 设备不支持平面检测，延迟模拟
    setTimeout(() => {
      this.setData({ planeDetected: true, floatClass: 'floatAnim' });
      wx.vibrateShort();
    }, 2000);
  },

  // ─── AR 操作 ───
  capturePhoto() {
    wx.showToast({ title: '📸 已保存至相册！', icon: 'none', duration: 2000 });
    // 实际项目中使用 wx.canvasToTempFilePath 或截图 API
  },

  finishAR() {
    if (!this.data.planeDetected) return;

    // 奖励星星
    app.globalData.stars = (app.globalData.stars || 0) + 8;
    app.globalData.coloringWorks = (app.globalData.coloringWorks || 0) + 1;
    const coloringWorks = app.globalData.coloringWorks;

    try {
      wx.setStorageSync('stars', app.globalData.stars);
      wx.setStorageSync('coloringWorks', coloringWorks);
      let completedGames = wx.getStorageSync('todayCompletedGames') || [];
      if (!completedGames.includes('ar-color')) {
        completedGames.push('ar-color');
        wx.setStorageSync('todayCompletedGames', completedGames);
      }
    } catch (e) { /* noop */ }

    if (this._vkSession) {
      try { this._vkSession.stop(); } catch (e) { /* noop */ }
    }

    this.setData({ step: 'complete', coloringWorks });
    wx.vibrateShort();
  },

  // ─── 完成界面操作 ───
  shareResult() {
    wx.showToast({ title: '分享功能即将上线 ✨', icon: 'none' });
  },

  resetPage() {
    this.setData({
      step: 'upload',
      uploadedImage: '',
      progress: 0,
      processTip: PROCESS_TIPS[0],
      planeDetected: false,
      floatClass: '',
    });
    wx.vibrateShort();
  },

  goBack() {
    wx.navigateBack();
  },

  onCameraError(e) {
    console.warn('AR Camera error:', e.detail);
    this.setData({ cameraError: true });
    wx.showToast({ title: '摄像头开启失败，请检查权限', icon: 'none', duration: 3000 });
  },
});
