Component({
  data: {
    dropdownOpen: false,
    currentVoiceId: '',
    currentVoiceName: '基础音色（默认）',
    defaultVoiceId: 'voice_001',
    voiceList: [],
    isSwitchingVoice: false
  },

  lifetimes: {
    attached() {
      this._app = getApp();
      this._onVoiceChange = (payload) => {
        this.setData({
          currentVoiceId: (payload && payload.voiceId) || '',
          currentVoiceName: (payload && payload.voiceName) || '基础音色（默认）',
          defaultVoiceId: (payload && payload.defaultVoiceId) || 'voice_001',
          voiceList: (payload && payload.voices) || []
        });
      };

      if (this._app && this._app.subscribeVoiceChange) {
        this._app.subscribeVoiceChange(this._onVoiceChange);
      }

      this._syncFromApp();
      this._refreshVoiceList();
    },

    detached() {
      if (this._app && this._app.unsubscribeVoiceChange && this._onVoiceChange) {
        this._app.unsubscribeVoiceChange(this._onVoiceChange);
      }
    }
  },

  pageLifetimes: {
    show() {
      this._syncFromApp();
      this._refreshVoiceList();
    }
  },

  methods: {
    noop() {},

    _syncFromApp() {
      const app = this._app || getApp();
      const gd = (app && app.globalData) || {};
      this.setData({
        currentVoiceId: gd.voiceId || gd.defaultVoiceId || '',
        currentVoiceName: gd.globalVoiceName || gd.defaultVoiceName || '基础音色（默认）',
        defaultVoiceId: gd.defaultVoiceId || 'voice_001',
        voiceList: Array.isArray(gd.voiceList) ? gd.voiceList : []
      });
    },

    _refreshVoiceList() {
      const app = this._app || getApp();
      if (app && app.refreshVoiceList) {
        app.refreshVoiceList();
      }
    },

    onToggleDropdown() {
      this.setData({ dropdownOpen: !this.data.dropdownOpen });
    },

    onCloseDropdown() {
      this.setData({ dropdownOpen: false });
    },

    onChooseDefault() {
      const app = this._app || getApp();
      if (!app || !app.setDefaultVoice) return;
      if (this.data.isSwitchingVoice) return;

      this.setData({ isSwitchingVoice: true });
      app.setDefaultVoice((err) => {
        if (!err) {
          wx.showToast({ title: '已切换基础音色', icon: 'success' });
        } else {
          wx.showToast({ title: '切换失败', icon: 'none' });
        }
        this.setData({ dropdownOpen: false, isSwitchingVoice: false });
      });
    },

    onChooseVoice(e) {
      const ds = (e && e.currentTarget && e.currentTarget.dataset) || {};
      const voiceId = String(ds.voiceId || '').trim();
      const voiceName = String(ds.voiceName || voiceId).trim();
      if (!voiceId) return;
      if (this.data.isSwitchingVoice) return;
      if (String(this.data.currentVoiceId || '').trim() === voiceId) {
        this.setData({ dropdownOpen: false });
        return;
      }

      const app = this._app || getApp();
      if (!app || !app.setGlobalVoice) return;

      this.setData({ isSwitchingVoice: true });
      app.setGlobalVoice(voiceId, voiceName, (err) => {
        if (!err) {
          wx.showToast({ title: `已切换: ${voiceName}`, icon: 'success' });
        } else {
          wx.showToast({ title: '切换失败', icon: 'none' });
        }
        this.setData({ dropdownOpen: false, isSwitchingVoice: false });
      });
    },

    onGoTrain() {
      this.setData({ dropdownOpen: false });
      wx.switchTab({ url: '/pages/voice/voice' });
    },

    onManageVoices() {
      this.setData({ dropdownOpen: false });
      wx.navigateTo({ url: '/pages/voice-manage/voice-manage' });
    }
  }
});
