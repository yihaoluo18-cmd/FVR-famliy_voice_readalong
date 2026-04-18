const app = getApp();
const FRONTEND_HIDDEN_VOICE_IDS = new Set(['voice_003']);

function getApiBase() {
  // 优先使用全局配置 / 本地存储的 apiBaseUrl，避免真机跑到 127.0.0.1
  try {
    if (app && typeof app.getApiBaseUrl === "function") return app.getApiBaseUrl();
    if (app && app.globalData && app.globalData.apiBaseUrl) return app.globalData.apiBaseUrl;
    const stored = wx.getStorageSync("apiBaseUrl");
    if (stored) return stored;
  } catch (e) {}
  return 'http://127.0.0.1:9880';
}

Page({
  data: {
    voiceList: [],
    currentVoiceId: '',
    currentVoiceName: '基础音色（默认）',
    defaultVoiceId: 'voice_001',
    loading: false,
  },

  onLoad(options) {
    const from = String((options && options.from) || '').trim();
    this._fromRead = from === 'read';
    this._manualStartAfterPick = String((options && (options.manualStart || options.autoPlay)) || '').trim() === '1';
    this.refreshVoiceList();
  },

  onShow() {
    this.refreshVoiceList();
  },

  refreshVoiceList() {
    this.setData({ loading: true });
    if (app && app.refreshVoiceList) {
      app.refreshVoiceList((_err, voices) => {
        const list = Array.isArray(voices) ? voices : (app.globalData.voiceList || []);
        this.setData({
          voiceList: list,
          currentVoiceId: String((app.globalData && app.globalData.voiceId) || ''),
          currentVoiceName: String((app.globalData && app.globalData.globalVoiceName) || '基础音色（默认）'),
          defaultVoiceId: String((app.globalData && app.globalData.defaultVoiceId) || 'voice_001'),
          loading: false,
        });
      });
      return;
    }

    const base = getApiBase();
    wx.request({
      url: `${base}/voices`,
      method: 'GET',
      success: (res) => {
        const raw = (res && res.data && Array.isArray(res.data.voices)) ? res.data.voices : [];
        const list = raw.filter((v) => !FRONTEND_HIDDEN_VOICE_IDS.has(String((v && v.voice_id) || '').trim()));
        this.setData({ voiceList: list, loading: false });
      },
      fail: () => this.setData({ loading: false }),
    });
  },

  chooseDefault() {
    if (!app || !app.setDefaultVoice) return;
    app.setDefaultVoice((err) => {
      if (err) {
        wx.showToast({ title: '切换失败', icon: 'none' });
        return;
      }
      const currentId = String((app && app.globalData && app.globalData.voiceId) || this.data.defaultVoiceId || 'voice_001').trim();
      const currentName = String((app && app.globalData && app.globalData.globalVoiceName) || '基础音色（默认）').trim();
      if (this._shouldReturnToRead()) {
        this._markReadVoicePick(currentId, currentName);
        wx.navigateBack({ delta: 1 });
        return;
      }
      wx.showToast({ title: '已切换基础音色', icon: 'success' });
      this.refreshVoiceList();
    });
  },

  chooseVoice(e) {
    const ds = (e && e.currentTarget && e.currentTarget.dataset) || {};
    const voiceId = String(ds.voiceId || '').trim();
    const voiceName = String(ds.voiceName || voiceId).trim();
    if (!voiceId) return;

    if (!app || !app.setGlobalVoice) return;
    app.setGlobalVoice(voiceId, voiceName, (err) => {
      if (err) {
        wx.showToast({ title: '切换失败', icon: 'none' });
        return;
      }
      if (this._shouldReturnToRead()) {
        this._markReadVoicePick(voiceId, voiceName);
        wx.navigateBack({ delta: 1 });
        return;
      }
      wx.showToast({ title: '已切换音色', icon: 'success' });
      this.refreshVoiceList();
    });
  },


  _shouldReturnToRead() {
    return !!(this._fromRead && this._manualStartAfterPick);
  },

  _markReadVoicePick(voiceId, voiceName) {
    try {
      wx.setStorageSync('read.voice.manage.selected', '1');
      wx.setStorageSync('read.voice.manage.ts', Date.now());
      wx.setStorageSync('read.voice.manage.voiceId', String(voiceId || '').trim());
      wx.setStorageSync('read.voice.manage.voiceName', String(voiceName || '').trim());
    } catch (e) {}
  },

  deleteVoice(e) {
    const ds = (e && e.currentTarget && e.currentTarget.dataset) || {};
    const voiceId = String(ds.voiceId || '').trim();
    const voiceName = String(ds.voiceName || voiceId).trim();
    const isDefault = String(ds.isDefault || '0') === '1';
    const isBuiltin = String(ds.isBuiltin || '0') === '1';
    const canDelete = String(ds.canDelete || '1') !== '0';
    if (!voiceId) return;
    if (isDefault || isBuiltin || !canDelete || voiceId === 'voice_001' || voiceId === 'voice_002' || voiceId === this.data.defaultVoiceId) {
      wx.showToast({ title: '基础音色不可删除', icon: 'none' });
      return;
    }

    wx.showModal({
      title: '删除音色',
      content: `确认删除音色“${voiceName}”？删除后无法恢复。`,
      confirmText: '删除',
      confirmColor: '#dc2626',
      cancelText: '取消',
      success: (res) => {
        if (!(res && res.confirm)) return;
        this._deleteVoiceConfirm(voiceId, voiceName);
      }
    });
  },

  _deleteVoiceConfirm(voiceId, voiceName) {
    const base = getApiBase();
    wx.request({
      url: `${base}/voices/${encodeURIComponent(voiceId)}`,
      method: 'DELETE',
      success: (res) => {
        const data = (res && res.data) || {};
        const ok = (res.statusCode === 200) && (Number(data.code) === 0 || Number(data.code) === 200);
        if (!ok) {
          wx.showToast({ title: data.message || '删除失败', icon: 'none' });
          return;
        }

        const currentId = String((app && app.globalData && app.globalData.voiceId) || '');
        if (currentId && currentId === voiceId && app && app.setDefaultVoice) {
          app.setDefaultVoice(() => {
            wx.showToast({ title: `已删除：${voiceName}`, icon: 'success' });
            this.refreshVoiceList();
          });
          return;
        }

        wx.showToast({ title: `已删除：${voiceName}`, icon: 'success' });
        this.refreshVoiceList();
      },
      fail: () => {
        wx.showToast({ title: '删除请求失败', icon: 'none' });
      }
    });
  },

  goToClone() {
    wx.switchTab({ url: '/pages/voice/voice' });
  }
});
