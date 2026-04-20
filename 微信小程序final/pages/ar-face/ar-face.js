const app = getApp();
const { toMiniprogramAssetUrl } = require("../../utils/asset-url.js");
const { getPetCoverUrl } = require("../../utils/pets-catalog.js");

const MASKS = [
  { id: 'bunny',    name: '兔子', url: '/assets/images/小兔.png'  },
  { id: 'cat',      name: '小猫', url: '/assets/images/小猫.png'  },
  { id: 'dog',      name: '小狗', url: '/assets/images/小狗.png'  },
  { id: 'squirrel', name: '松鼠', url: '/assets/images/松鼠.png'  },
  { id: 'sheep',    name: '绵羊', url: getPetCoverUrl('cute-dino') },
  { id: 'fox',      name: '狐狸', url: '/assets/images/狐狸.png'  },
];

const QUESTIONS = [
  '看着摄像头，用你的声音说出你今天最开心的事情吧！',
  '戴上动物面具，模仿这个动物的叫声或动作来介绍它！',
  '扮演一只小动物，讲一讲你住的森林里发生的故事！',
  '假如你是一只小兔子，你会怎么和新朋友打招呼呢？',
  '用最洪亮的声音，说出你最喜欢的一句话吧！',
];

Page({
  data: {
    masks: MASKS.map((m) => ({ ...m, url: toMiniprogramAssetUrl(m.url) })),
    arFaceBackIcon: toMiniprogramAssetUrl("/assets/images/返回.png"),
    currentMask: null,
    isTracking: false,

    questionText: '',
    questionVisible: false,

    isRecording: false,
    hasRecorded: false,
    recordSeconds: 0,
    lastAudioPath: '',

    evaluating: false,
    showResult: false,
    aiScore: 0,
    fullStars: 0,
    feedback: '',
    transcript: '',

    cameraError: false,
  },

  onLoad() {
    // 随机选题目
    const q = QUESTIONS[Math.floor(Math.random() * QUESTIONS.length)];
    this.setData({ questionText: q });

    setTimeout(() => {
      this.setData({ questionVisible: true });
    }, 400);

    // 模拟人脸检测就绪（实际应接入 wx.createVKSession face模式）
    this._initFaceTracking();

    // 初始化录音管理器
    this.recorder = wx.getRecorderManager();
    this.recorder.onStop((res) => this._onRecordStop(res));
    this.recorder.onError(() => {
      wx.showToast({ title: '录音失败，请重试', icon: 'none' });
      this._stopRecordTimer();
      this.setData({ isRecording: false });
    });
  },

  onUnload() {
    if (this._recordTimer) clearInterval(this._recordTimer);
    if (this._vkSession) {
      try { this._vkSession.stop(); } catch (e) { /* noop */ }
    }
  },

  // ─── 人脸检测初始化 ───
  _initFaceTracking() {
    // 尝试使用 VisionKit 进行人脸追踪
    // 不支持时降级为「模拟就绪」状态
    if (wx.createVKSession) {
      try {
        const session = wx.createVKSession({
          track: { face: { mode: 1 } },
          version: 'v1',
          gl: null,  // 纯 UI 模式，不需要 WebGL
        });
        session.start((err) => {
          if (err) {
            // 权限拒绝或设备不支持，降级
            this._fallbackTracking();
            return;
          }
          this._vkSession = session;
          session.on('updateAnchors', (anchors) => {
            this.setData({ isTracking: anchors && anchors.length > 0 });
          });
          session.on('removeAnchors', () => {
            this.setData({ isTracking: false });
          });
        });
      } catch (e) {
        this._fallbackTracking();
      }
    } else {
      this._fallbackTracking();
    }
  },

  _fallbackTracking() {
    // 不支持 VisionKit 时，1.5 秒后模拟"已就绪"
    setTimeout(() => {
      this.setData({ isTracking: true });
    }, 1500);
  },

  // ─── 面具选择 ───
  selectMask(e) {
    const mask = e.currentTarget.dataset.mask;
    this.setData({ currentMask: mask });
    wx.vibrateShort();
  },

  clearMask() {
    this.setData({ currentMask: null });
    wx.vibrateShort();
  },

  // ─── 录音控制 ───
  toggleRecord() {
    if (this.data.evaluating) return;
    this.data.isRecording ? this._stopRecord() : this._startRecord();
  },

  _startRecord() {
    this.recorder.start({
      duration: 60000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: 'mp3',
    });
    this._recordTimer = setInterval(() => {
      this.setData({ recordSeconds: this.data.recordSeconds + 1 });
    }, 1000);
    this.setData({ isRecording: true, recordSeconds: 0, hasRecorded: false });
    wx.vibrateShort();
  },

  _stopRecord() {
    this.recorder.stop();
    this._stopRecordTimer();
    this.setData({ isRecording: false });
  },

  _stopRecordTimer() {
    if (this._recordTimer) {
      clearInterval(this._recordTimer);
      this._recordTimer = null;
    }
  },

  _onRecordStop(res) {
    this.setData({
      lastAudioPath: res.tempFilePath,
      hasRecorded: true,
    });
  },

  // ─── 提交评分 ───
  submitSpeech() {
    if (!this.data.hasRecorded || this.data.evaluating) return;

    this.setData({ evaluating: true });

    const apiBase = (app && app.getApiBaseUrl) ? app.getApiBaseUrl() : 'http://127.0.0.1:9880';

    // 上传音频进行评分（接口与 speaker 页面一致）
    wx.uploadFile({
      url: `${apiBase}/speaker/evaluate`,
      filePath: this.data.lastAudioPath,
      name: 'audio',
      formData: {
        caption: this.data.questionText,
        mode: 'ar-face',
      },
      success: (res) => {
        try {
          const data = JSON.parse(res.data || '{}');
          this._showResult(data);
        } catch (e) {
          this._showResult({});
        }
      },
      fail: () => {
        // 接口不通时给一个鼓励性的模拟结果
        this._showResult({});
      },
    });
  },

  _showResult(data) {
    const score = data.score || Math.floor(Math.random() * 20) + 78;
    const fullStars = score >= 95 ? 5 : score >= 85 ? 4 : score >= 75 ? 3 : score >= 60 ? 2 : 1;
    const feedback = data.feedback || '哇，说得真棒！声音清晰有力，继续保持！🎉';
    const transcript = data.transcript || '';

    this.setData({
      evaluating: false,
      showResult: true,
      aiScore: score,
      fullStars,
      feedback,
      transcript,
    });

    // 奖励星星
    app.globalData.stars = (app.globalData.stars || 0) + 5;
    app.globalData.speakerTasks = (app.globalData.speakerTasks || 0) + 1;
    try {
      wx.setStorageSync('stars', app.globalData.stars);
      wx.setStorageSync('speakerTasks', app.globalData.speakerTasks);
      let completedGames = wx.getStorageSync('todayCompletedGames') || [];
      if (!completedGames.includes('ar-face')) {
        completedGames.push('ar-face');
        wx.setStorageSync('todayCompletedGames', completedGames);
      }
    } catch (e) { /* noop */ }

    wx.vibrateShort();
  },

  // ─── 再玩一次 ───
  playAgain() {
    const q = QUESTIONS[Math.floor(Math.random() * QUESTIONS.length)];
    this.setData({
      showResult: false,
      hasRecorded: false,
      recordSeconds: 0,
      lastAudioPath: '',
      evaluating: false,
      aiScore: 0,
      fullStars: 0,
      feedback: '',
      transcript: '',
      questionText: q,
    });
    wx.vibrateShort();
  },

  goBack() {
    wx.navigateBack();
  },

  onCameraError(e) {
    console.warn('Camera error:', e.detail);
    this.setData({ cameraError: true });
  },

  openSetting() {
    wx.openSetting();
  },
});
