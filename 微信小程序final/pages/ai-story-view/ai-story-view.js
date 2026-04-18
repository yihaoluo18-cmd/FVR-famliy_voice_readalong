const app = getApp();

Page({
  data: {
    loading: true,
    empty: false,
    storyId: '',
    storyIndex: 0,
    storyCount: 0,
    storyTitle: '',
    storyAge: '',
    coverImage: '',
    caption: '',
    pages: [],
    currentPage: 0,
    totalPages: 0,
    currentText: '',
    isPlaying: false,
  },

  onLoad(options = {}) {
    this._requestedStoryId = String(options.id || '').trim();
    this.loadStories();
  },

  onShow() {
    this.loadStories(true);
  },

  goBack() {
    if (getCurrentPages().length > 1) {
      wx.navigateBack();
      return;
    }
    wx.switchTab({ url: '/pages/books/books' });
  },

  loadStories(keepCurrent = false) {
    const stories = wx.getStorageSync('aiStories') || [];
    if (!Array.isArray(stories) || !stories.length) {
      this.setData({ loading: false, empty: true, storyCount: 0, pages: [] });
      return;
    }

    let targetId = this._requestedStoryId;
    if (keepCurrent && this.data.storyId) targetId = this.data.storyId;

    let idx = stories.findIndex((s) => String((s && s.id) || '') === String(targetId || ''));
    if (idx < 0) idx = 0;
    this.applyStory(stories, idx, keepCurrent ? this.data.currentPage : null);
  },

  applyStory(stories, storyIndex, preferredPage) {
    const story = stories[storyIndex] || {};
    const rawPages = Array.isArray(story.pages) ? story.pages : [];
    const pages = rawPages.map((p) => {
      if (p && typeof p === 'object') return String(p.text || '').trim();
      return String(p || '').trim();
    }).filter(Boolean);

    const totalPages = pages.length;
    const fallbackPage = Number(story.currentPage || 0);
    let currentPage = Number(preferredPage);
    if (Number.isNaN(currentPage)) currentPage = fallbackPage;
    if (Number.isNaN(currentPage)) currentPage = 0;
    currentPage = Math.max(0, Math.min(currentPage, Math.max(totalPages - 1, 0)));

    this.setData({
      loading: false,
      empty: !pages.length,
      storyId: String(story.id || ''),
      storyIndex,
      storyCount: stories.length,
      storyTitle: String(story.title || 'AI魔法绘本'),
      storyAge: String(story.age || ''),
      coverImage: String(story.coverImage || ''),
      caption: String(story.caption || ''),
      pages,
      currentPage,
      totalPages,
      currentText: pages[currentPage] || '',
    });

    if (pages.length) this.persistProgress(currentPage);
  },

  persistProgress(currentPage) {
    try {
      const stories = wx.getStorageSync('aiStories') || [];
      const idx = stories.findIndex((s) => String((s && s.id) || '') === this.data.storyId);
      if (idx < 0) return;
      stories[idx] = { ...stories[idx], currentPage: Number(currentPage || 0), updatedAt: Date.now() };
      wx.setStorageSync('aiStories', stories);
    } catch (e) {}
  },

  prevPage() {
    if (this.data.currentPage <= 0) return;
    this.stopPlaying();
    const currentPage = this.data.currentPage - 1;
    this.setData({ currentPage, currentText: this.data.pages[currentPage] || '' });
    this.persistProgress(currentPage);
    wx.vibrateShort();
  },

  nextPage() {
    if (this.data.currentPage >= this.data.totalPages - 1) return;
    this.stopPlaying();
    const currentPage = this.data.currentPage + 1;
    this.setData({ currentPage, currentText: this.data.pages[currentPage] || '' });
    this.persistProgress(currentPage);
    wx.vibrateShort();
  },

  prevStory() {
    if (this.data.storyIndex <= 0) return;
    const stories = wx.getStorageSync('aiStories') || [];
    this.stopPlaying();
    this.applyStory(stories, this.data.storyIndex - 1, 0);
  },

  nextStory() {
    if (this.data.storyIndex >= this.data.storyCount - 1) return;
    const stories = wx.getStorageSync('aiStories') || [];
    this.stopPlaying();
    this.applyStory(stories, this.data.storyIndex + 1, 0);
  },


  _resolveVoiceId() {
    const fromGetter = (app && app.getVoiceId) ? String(app.getVoiceId() || '').trim() : '';
    if (fromGetter) return fromGetter;
    const gd = (app && app.globalData) ? app.globalData : {};
    return String((gd && gd.defaultVoiceId) || 'voice_001').trim();
  },

  _ensureVoiceReady() {
    return new Promise((resolve) => {
      const voiceId = this._resolveVoiceId();
      if (voiceId) {
        resolve(voiceId);
        return;
      }
      if (app && app.setDefaultVoice) {
        app.setDefaultVoice(() => resolve(this._resolveVoiceId() || 'voice_001'));
        return;
      }
      resolve('voice_001');
    });
  },

  ensureAudio() {
    if (this._audio) return;
    this._audio = wx.createInnerAudioContext();
    this._audio.autoplay = false;
    this._audio.onEnded(() => this.setData({ isPlaying: false }));
    this._audio.onError(() => {
      this.setData({ isPlaying: false });
      wx.showToast({ title: '朗读失败，请稍后再试', icon: 'none' });
    });
  },

  buildTtsUrl(text, resolvedVoiceId) {
    const t = String(text || '').trim();
    if (!t) return '';

    const base = (app && app.getApiBaseUrl) ? app.getApiBaseUrl() : 'http://127.0.0.1:9880';
    const voiceId = String(resolvedVoiceId || this._resolveVoiceId() || 'voice_001').trim();
    const q = [
      `voice_id=${encodeURIComponent(voiceId)}`,
      `text=${encodeURIComponent(t)}`,
      'text_language=zh',
      'media_type=wav',
      'stream_mode=close',
      `ts=${Date.now()}`,
    ].join('&');

    return `${base}/synthesize/stream?${q}`;
  },

  async togglePlay() {
    if (this.data.isPlaying) {
      this.stopPlaying();
      return;
    }
    const voiceId = await this._ensureVoiceReady();
    const url = this.buildTtsUrl(this.data.currentText, voiceId);
    if (!url) {
      wx.showToast({ title: '当前页暂无文字', icon: 'none' });
      return;
    }

    this.ensureAudio();
    try {
      this._audio.stop();
      this._audio.src = url;
      this._audio.play();
      this.setData({ isPlaying: true });
    } catch (e) {
      this.setData({ isPlaying: false });
      wx.showToast({ title: '播放失败', icon: 'none' });
    }
  },

  stopPlaying() {
    try {
      if (this._audio) this._audio.stop();
    } catch (e) {}
    if (this.data.isPlaying) this.setData({ isPlaying: false });
  },

  deleteStory() {
    const sid = this.data.storyId;
    if (!sid) return;

    wx.showModal({
      title: '删除这个故事？',
      content: '删除后无法恢复，可以重新生成同类型故事。',
      confirmText: '删除',
      confirmColor: '#ef4444',
      success: (res) => {
        if (!res.confirm) return;
        const stories = (wx.getStorageSync('aiStories') || []).filter((s) => String((s && s.id) || '') !== sid);
        wx.setStorageSync('aiStories', stories);
        this.stopPlaying();
        if (!stories.length) {
          this.setData({ empty: true, storyCount: 0, pages: [] });
          return;
        }
        const nextIdx = Math.max(0, this.data.storyIndex - 1);
        this.applyStory(stories, Math.min(nextIdx, stories.length - 1), 0);
        wx.showToast({ title: '已删除', icon: 'success' });
      }
    });
  },

  goGenerate() {
    wx.navigateTo({ url: '/pages/ai-story/ai-story' });
  },

  onTouchStart(e) {
    this._touchStartX = Number((e && e.changedTouches && e.changedTouches[0] && e.changedTouches[0].clientX) || 0);
  },

  onTouchEnd(e) {
    const endX = Number((e && e.changedTouches && e.changedTouches[0] && e.changedTouches[0].clientX) || 0);
    const delta = endX - Number(this._touchStartX || 0);
    if (delta > 80) this.prevPage();
    else if (delta < -80) this.nextPage();
  },

  onUnload() {
    this.stopPlaying();
    if (this._audio) {
      this._audio.destroy();
      this._audio = null;
    }
  }
});
