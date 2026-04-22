const app = getApp();
const { resolveApiBase } = require("../../utils/api-base.js");
const { reportEggProgress, reportCompanionReadXp } = require("../../utils/pet-growth.js");
const { PETS_CATALOG, getPetById } = require("../../utils/pets-catalog.js");
const { toMiniprogramAssetUrl } = require("../../utils/asset-url.js");
const { isMainDone, markMainDone } = require("../../utils/guide-flow.js");

Page({
  data: {
    bookId: '',
    book: null,
    pageIndex: 0,
    totalPages: 0,
    currentText: '',
    isPlaying: null, // 'custom' or null
    selectedVoiceName: '',
    currentVoiceId: '',
    isFavorite: false,
    source: '',
    bookLoading: false,
    bookError: '',
    
    // 翻页控制
    isFirstPage: true,
    isLastPage: false,
    canGoPrev: false,
    canGoNext: true,
    
    // 上/下一本书
    hasPrevBook: false,
    hasNextBook: false,
    prevBookTitle: '',
    nextBookTitle: '',
    
    // 动画
    textAnimation: {},
    sparkleClass: 'sparkleClass',
    hasReportedReadTask: false,
    showReadSettingsPanel: false,
    showCompanionPanel: false,
    readFontScale: "md",
    readFontSize: 32,
    readFontLineHeight: 1.8,
    voiceOptions: [],
    companionOptions: [],
    selectedCompanionId: "cute-dog",
    summonedCompanionName: "柴柴小星",
    summonedCompanionEmoji: "🐶",
    showSummonedCompanion: false,
    readPlayIconCustom: toMiniprogramAssetUrl("/assets/images/mom1.png"),
    showReadStartButton: false,
    showGuide: false,
    guideSteps: [],
    guideStepIndex: 0,
    guideHighlight: '',
    guideTitle: '',
    guideDesc: '',
  },

  onLoad(options) {
    // 今日阅读时长：进入开始计时，离开/隐藏时累加到本地（按日期）
    this._readingStartTs = Date.now();
    this._readingAccumulatedMs = 0;
    // 注意：书架跳转时会 encodeURIComponent，这里必须先 decode，避免二次编码导致后端找不到书
    let bookId = options.id || '';
    try { bookId = decodeURIComponent(String(bookId)) } catch (e) {}
    const source = String(options.source || '').trim() || 'library'
    this._requestedStartPage = Math.max(0, Number(options.startPage || 0) || 0);
    this._loadReadSettings();
    this._loadCompanionState();
    this.setData({ source })
    if (!String(bookId || '').trim()) {
      this.setData({ bookLoading: false, bookError: "请从书架选择一本绘本再打开阅读。" });
      return;
    }
    this.loadBook(bookId, source);
    this.refreshVoiceStatus();
    this.initReadGuide();
  },
  goBack() {
    wx.navigateBack();
  },

  onShow() {
    // 从后台回来继续累计
    if (!this._readingStartTs) this._readingStartTs = Date.now();
    // 刷新收藏状态
    this.checkFavoriteStatus();
    this.refreshVoiceStatus();
    this._loadCompanionState();
    this._syncVoicePickFromManage();
  },

  onHide() {
    this._flushReadingMinutes();
    this._saveRecentReading();
  },

  // 加载绘本
  loadBook(bookId, source) {
    // 已移除内置测试绘本：统一从后端绘本库加载
    this.setData({ source: String(source || '').trim() || 'library' });
    this.loadLibraryBook(String(bookId || ''));
  },

  loadLibraryBook(bookId) {
    if (!bookId) return
    const base = resolveApiBase(app)
    this.setData({ bookLoading: true, bookError: '' })

    wx.request({
      url: `${base}/magic_books/book?title=${encodeURIComponent(bookId)}`,
      method: 'GET',
      success: (res) => {
        const data = res && res.data ? res.data : {}
        const normUrl = (u) => {
          const s = String(u || '')
          if (!s) return ''
          if (/^https?:\/\//i.test(s)) return s
          if (s.startsWith('/')) return `${base}${s}`
          return `${base}/${s}`
        }
        const parasRaw = Array.isArray(data.paras) ? data.paras : []
        const pages = this._buildLibraryPagesWithImageFallback(parasRaw, normUrl)

        const book = {
          id: String(bookId),
          title: String(data.title || bookId || '绘本'),
          subtitle: '',
          image: pages[0] ? pages[0].image : '',
          pages
        }
        const initialIndex = Math.max(0, Math.min(pages.length - 1, Number(this._requestedStartPage || 0) || 0));

        this.setData({
          bookId: book.id,
          book,
          pageIndex: initialIndex,
          totalPages: pages.length,
          currentText: pages[initialIndex] ? (pages[initialIndex].text || pages[initialIndex].prompt || '') : '',
          isFirstPage: initialIndex === 0,
          isLastPage: initialIndex >= pages.length - 1,
          canGoPrev: initialIndex > 0,
          canGoNext: initialIndex < pages.length - 1,
          hasPrevBook: false,
          hasNextBook: false,
          prevBookTitle: '',
          nextBookTitle: '',
          hasReportedReadTask: false,
        })

        this.checkFavoriteStatus()
      },
      fail: (err) => {
        console.log('加载绘本详情失败', err)
        this.setData({
          bookError: (err && err.errMsg) ? String(err.errMsg) : '加载失败',
        })
        wx.showToast({ title: '加载绘本失败', icon: 'none' })
      },
      complete: () => {
        this.setData({ bookLoading: false })
      }
    })
  },

  _buildLibraryPagesWithImageFallback(parasRaw, normUrl) {
    const list = Array.isArray(parasRaw) ? parasRaw : []
    const pool = []
    const poolSeen = {}
    const pages = list.map((p) => {
      const imgsRaw = (p && Array.isArray(p.images)) ? p.images : []
      const imgs = imgsRaw
        .map((u) => normUrl(u))
        .filter(Boolean)
      imgs.forEach((u) => {
        if (!poolSeen[u]) {
          poolSeen[u] = 1
          pool.push(u)
        }
      })
      return {
        images: imgs,
        text: String((p && p.text) || ''),
        prompt: String((p && p.prompt) || ''),
      }
    })

    let lastImage = ''
    return pages.map((p, idx) => {
      const own = (Array.isArray(p.images) && p.images.length) ? String(p.images[0] || '') : ''
      let picked = own
      if (!picked && lastImage) picked = lastImage
      if (!picked && pool.length) picked = pool[idx % pool.length]
      if (picked) lastImage = picked
      return {
        image: picked || '',
        text: p.text,
        prompt: p.prompt || '',
      }
    })
  },

  // 检查收藏状态
  checkFavoriteStatus() {
    const favorites = app.globalData.favorites || [];
    const isFavorite = favorites.some(fav => fav.id === this.data.bookId);
    this.setData({ isFavorite });
  },

  // 上一页
  prevPage() {
    if (this.data.pageIndex === 0) return;
    
    const newIndex = this.data.pageIndex - 1;
    this.changePage(newIndex);
  },

  // 下一页
  nextPage() {
    if (this.data.pageIndex >= this.data.totalPages - 1) return;
    
    const newIndex = this.data.pageIndex + 1;
    this.changePage(newIndex);
  },

  // 切换页面
  changePage(newIndex) {
    // 翻页时先停掉朗读
    if (this.data.isPlaying) this.stopPlaying()

    // 创建淡出动画
    const animation = wx.createAnimation({
      duration: 200,
      timingFunction: 'ease-out',
    });
    animation.opacity(0).translateY(-20).step();

    this.setData({
      textAnimation: animation.export()
    });

    // 延迟更新内容并淡入
    setTimeout(() => {
      const animation2 = wx.createAnimation({
        duration: 200,
        timingFunction: 'ease-out',
      });
      animation2.opacity(1).translateY(0).step();

      const page = (this.data.book && Array.isArray(this.data.book.pages)) ? this.data.book.pages[newIndex] : null
      const nextText = (page && (page.text || page.prompt)) ? (page.text || page.prompt) : ''
      const nextCover = page && page.image ? page.image : (this.data.book ? this.data.book.image : '')

      this.setData({
        pageIndex: newIndex,
        currentText: nextText,
        book: {
          ...(this.data.book || {}),
          image: nextCover
        },
        isFirstPage: newIndex === 0,
        isLastPage: newIndex === this.data.totalPages - 1,
        canGoPrev: newIndex > 0,
        canGoNext: newIndex < this.data.totalPages - 1,
        textAnimation: animation2.export()
      });
      this.reportReadTaskIfCompleted();
      this._saveRecentReading();
    }, 200);

  
  },

  reportReadTaskIfCompleted() {
    if (!this.data.isLastPage || this.data.hasReportedReadTask) return;
    const currentBookId = String(this.data.bookId || "").trim();
    if (!currentBookId) return;
    this.setData({ hasReportedReadTask: true });
    const payload = {
      book_id: currentBookId,
      page_index: this.data.pageIndex,
      total_pages: this.data.totalPages,
    };
    reportEggProgress("read_task_completed", payload).catch(() => {
      this.setData({ hasReportedReadTask: false });
    });
    let mascotId = "cute-dog";
    try {
      const saved = String(wx.getStorageSync("selectedMascot") || "").trim();
      if (saved) mascotId = saved;
    } catch (e) {}
    reportCompanionReadXp(mascotId, payload).catch(() => {});
    markMainDone("readDone");
    this.closeGuide();
  },


  refreshVoiceStatus() {
    const voiceName = (app && app.globalData && app.globalData.globalVoiceName) ? String(app.globalData.globalVoiceName) : '';
    this.setData({
      selectedVoiceName: voiceName || '基础音色（默认）',
      currentVoiceId: this._resolveVoiceId() || '',
    });
    this._refreshVoiceOptions();
  },

  _refreshVoiceOptions() {
    const list = (app && app.globalData && Array.isArray(app.globalData.voiceList)) ? app.globalData.voiceList : [];
    const selectedId = this._resolveVoiceId();
    const selectedName = this.data.selectedVoiceName || '基础音色（默认）';
    let options = list.map((v) => ({
      id: String(v.voice_id || ''),
      name: String(v.name || v.voice_id || ''),
      isBuiltin: !!(v && v.is_builtin),
      priority: this._voicePriority(v),
    })).filter((x) => x.id);
    options.sort((a, b) => Number(a.priority || 99) - Number(b.priority || 99) || String(a.name || '').localeCompare(String(b.name || '')));
    options = options.map((x) => ({ id: x.id, name: x.name }));
    if (!options.length) {
      const fallbackId = selectedId || this._getAnyAvailableVoiceId();
      options = fallbackId ? [{ id: fallbackId, name: selectedName }] : [];
    }
    this.setData({ voiceOptions: options });
  },

  _voicePriority(row) {
    const id = String((row && (row.voice_id || row.id)) || '').trim();
    if (id === 'voice_001') return 0;
    if (id === 'voice_002') return 1;
    if (row && row.is_builtin) return 2;
    return 10;
  },

  _findVoiceMetaById(voiceId) {
    const id = String(voiceId || '').trim();
    if (!id) return null;
    const list = (app && app.globalData && Array.isArray(app.globalData.voiceList)) ? app.globalData.voiceList : [];
    const hit = list.find((v) => String((v && v.voice_id) || '').trim() === id);
    if (hit) return { id, name: String(hit.name || hit.voice_id || id) };
    const opts = Array.isArray(this.data.voiceOptions) ? this.data.voiceOptions : [];
    const hit2 = opts.find((x) => String((x && x.id) || '').trim() === id);
    if (hit2) return { id, name: String(hit2.name || id) };
    return null;
  },

  _getBaseVoiceForRole(roleKey) {
    const role = String(roleKey || '').trim();
    const targetId = role === 'dad' ? 'voice_002' : 'voice_001';
    const direct = this._findVoiceMetaById(targetId);
    if (direct) return direct;

    const list = (app && app.globalData && Array.isArray(app.globalData.voiceList)) ? app.globalData.voiceList : [];
    const targetGender = role === 'dad' ? 'male' : 'female';
    const byGender = list.find((v) => String((v && v.gender) || '').trim().toLowerCase() === targetGender && (v && (v.is_builtin || String(v.voice_group || '') === 'qwen_base')));
    if (byGender) {
      return {
        id: String(byGender.voice_id || '').trim(),
        name: String(byGender.name || byGender.voice_id || ''),
      };
    }

    const anyBuiltin = list.find((v) => !!(v && v.is_builtin));
    if (anyBuiltin) {
      return {
        id: String(anyBuiltin.voice_id || '').trim(),
        name: String(anyBuiltin.name || anyBuiltin.voice_id || ''),
      };
    }
    return { id: '', name: '' };
  },

  _loadReadSettings() {
    let scale = "md";
    try {
      const saved = String(wx.getStorageSync("readFontScale") || "md");
      if (saved === "sm" || saved === "md" || saved === "lg") scale = saved;
    } catch (e) {}
    this._applyReadFontScale(scale);
  },

  _applyReadFontScale(scale) {
    const s = String(scale || "md");
    if (s === "sm") {
      this.setData({ readFontScale: "sm", readFontSize: 28, readFontLineHeight: 1.72 });
      return;
    }
    if (s === "lg") {
      this.setData({ readFontScale: "lg", readFontSize: 36, readFontLineHeight: 1.9 });
      return;
    }
    this.setData({ readFontScale: "md", readFontSize: 32, readFontLineHeight: 1.8 });
  },

  onToggleReadSettingsPanel() {
    this.setData({
      showReadSettingsPanel: !this.data.showReadSettingsPanel,
      showCompanionPanel: false,
    });
  },

  onToggleCompanionPanel() {
    this.setData({
      showCompanionPanel: !this.data.showCompanionPanel,
      showReadSettingsPanel: false,
    });
  },

  onSelectReadFont(e) {
    const scale = String((e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.scale) || "md");
    this._applyReadFontScale(scale);
    try { wx.setStorageSync("readFontScale", scale); } catch (e2) {}
  },

  onSelectReadVoice(e) {
    const voiceId = String((e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.voiceId) || "").trim();
    if (!voiceId) return;

    const current = String((this.data && this.data.currentVoiceId) || '').trim();
    if (current && current === voiceId) {
      return;
    }

    const row = (this.data.voiceOptions || []).find((x) => x.id === voiceId);
    const voiceName = row ? row.name : "基础音色（默认）";
    if (!app || !app.setGlobalVoice) return;
    app.setGlobalVoice(voiceId, voiceName, (err) => {
      if (err) {
        wx.showToast({ title: '音色切换失败', icon: 'none' });
        return;
      }
      this.refreshVoiceStatus();
      wx.showToast({ title: '音色已切换', icon: 'success' });
    });
  },

  _loadCompanionState() {
    const options = (Array.isArray(PETS_CATALOG) ? PETS_CATALOG : []).map((p) => ({
      id: String(p.id || ''),
      name: String(p.name || '小伴宠'),
      emoji: String(p.emoji || '🐾'),
    })).filter((x) => x.id);
    let selected = "cute-dog";
    try {
      const saved = String(wx.getStorageSync("selectedMascot") || "").trim();
      if (saved) selected = saved;
    } catch (e) {}
    const pet = getPetById(selected) || getPetById("cute-dog") || null;
    this.setData({
      companionOptions: options,
      selectedCompanionId: pet ? pet.id : selected,
      summonedCompanionName: pet ? String(pet.name || '小伴宠') : '小伴宠',
      summonedCompanionEmoji: pet ? String(pet.emoji || '🐾') : '🐾',
    });
  },

  onToggleSummonedCompanion() {
    this.setData({ showSummonedCompanion: !this.data.showSummonedCompanion });
  },

  onSelectCompanion(e) {
    const id = String((e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.mascotId) || "").trim();
    if (!id) return;
    const pet = getPetById(id) || null;
    if (!pet) return;
    try { wx.setStorageSync("selectedMascot", id); } catch (e) {}
    this.setData({
      selectedCompanionId: id,
      summonedCompanionName: String(pet.name || '小伴宠'),
      summonedCompanionEmoji: String(pet.emoji || '🐾'),
      showSummonedCompanion: true,
    });
  },

  _getAnyAvailableVoiceId() {
    const fromCurrent = String((this.data && this.data.currentVoiceId) || '').trim();
    if (fromCurrent) return fromCurrent;

    const female = this._getBaseVoiceForRole('mom');
    if (female && female.id) return female.id;
    const male = this._getBaseVoiceForRole('dad');
    if (male && male.id) return male.id;

    const gd = (app && app.globalData) ? app.globalData : {};
    const list = Array.isArray(gd.voiceList) ? gd.voiceList : [];
    const fromList = list.find((v) => String((v && v.voice_id) || '').trim());
    if (fromList) return String(fromList.voice_id || '').trim();

    const opts = Array.isArray(this.data.voiceOptions) ? this.data.voiceOptions : [];
    const fromOpts = opts.find((x) => String((x && x.id) || '').trim());
    return fromOpts ? String(fromOpts.id || '').trim() : '';
  },

  _resolveVoiceId() {
    const fromGetter = (app && app.getVoiceId) ? String(app.getVoiceId() || '').trim() : '';
    if (fromGetter) return fromGetter;

    const gd = (app && app.globalData) ? app.globalData : {};
    const fallback = String((gd && gd.defaultVoiceId) || '').trim();
    const list = Array.isArray(gd.voiceList) ? gd.voiceList : [];
    if (fallback && list.some((v) => String((v && v.voice_id) || '').trim() === fallback)) return fallback;

    return this._getAnyAvailableVoiceId();
  },

  _ensureVoiceReady() {
    return new Promise((resolve) => {
      const voiceId = this._resolveVoiceId();
      if (voiceId) {
        this.refreshVoiceStatus();
        resolve(voiceId);
        return;
      }

      if (app && app.setDefaultVoice) {
        app.setDefaultVoice(() => {
          const v2 = this._resolveVoiceId();
          this.refreshVoiceStatus();
          resolve(v2 || this._getAnyAvailableVoiceId() || '');
        });
        return;
      }

      resolve(this._getAnyAvailableVoiceId() || '');
    });
  },


  _resolvePlaybackVoice(roleKey) {
    const role = String(roleKey || '').trim();
    const roleEnabled = role === 'mom' || role === 'dad';
    const appRole = roleEnabled && (app && app.getVoiceByRole) ? app.getVoiceByRole(role) : null;
    const roleVoiceId = String((appRole && appRole.voiceId) || '').trim();
    const roleVoiceName = String((appRole && appRole.voiceName) || '').trim();
    const roleBase = roleEnabled ? this._getBaseVoiceForRole(role) : { id: '', name: '' };

    const globalVoiceId = this._resolveVoiceId();
    const fallbackName = (app && app.globalData && app.globalData.globalVoiceName)
      ? String(app.globalData.globalVoiceName)
      : '基础音色（默认）';

    const pickedId = roleVoiceId || globalVoiceId || roleBase.id || this._getAnyAvailableVoiceId() || '';
    const pickedMeta = this._findVoiceMetaById(pickedId);
    return {
      voiceId: pickedId,
      voiceName: roleVoiceName || (pickedMeta && pickedMeta.name) || roleBase.name || fallbackName || '基础音色（默认）'
    };
  },

  onTapCustomReadVoice() {
    if (this.data.isPlaying) {
      this.stopPlaying();
    }
    this.setData({ showReadStartButton: true });
    this._goSelectReadVoice();
  },

  _goSelectReadVoice() {
    wx.navigateTo({
      url: '/pages/voice-manage/voice-manage?from=read&manualStart=1',
      fail: () => {
        wx.showToast({ title: '打开音色管理失败', icon: 'none' });
      }
    });
  },

  _syncVoicePickFromManage() {
    let picked = false;
    let pickedName = '';
    try {
      picked = String(wx.getStorageSync('read.voice.manage.selected') || '') === '1';
      pickedName = String(wx.getStorageSync('read.voice.manage.voiceName') || '').trim();
      if (picked) {
        wx.removeStorageSync('read.voice.manage.selected');
        wx.removeStorageSync('read.voice.manage.ts');
        wx.removeStorageSync('read.voice.manage.voiceId');
        wx.removeStorageSync('read.voice.manage.voiceName');
      }
    } catch (e) {}

    if (!picked) return;
    const safeName = pickedName || this.data.selectedVoiceName || '基础音色（默认）';
    this.setData({
      showReadStartButton: true,
      selectedVoiceName: safeName,
    });
    wx.showToast({ title: `当前音色：${safeName}`, icon: 'none' });
  },

  onTapStartReadBySelectedVoice() {
    if (this.data.isPlaying) {
      this.stopPlaying();
      return;
    }
    if (!this._isSpeakableText(this.data.currentText || '')) {
      wx.showToast({ title: '当前页没有可朗读文字', icon: 'none' });
      return;
    }
    Promise.resolve(this.startPlaying('custom')).catch((err) => {
      console.log('手动启动朗读失败', err);
    });
  },


  _isSpeakableText(text) {
    return /[0-9A-Za-z\u4e00-\u9fff]/.test(String(text || ''))
  },

  _normalizeReadTextForTts(text) {
    return String(text || '')
      .replace(/\r/g, '')
      .replace(/[“”]/g, '"')
      .replace(/[‘’]/g, "'")
      .replace(/…+/g, '。')
      .replace(/[ \t]+/g, '')
      .replace(/\n+/g, '\n')
      .trim()
  },

  _buildBookPageTtsContext() {
    const bookId = String((this.data && this.data.bookId) || '').trim()
    const pageIndex = Math.max(0, Number((this.data && this.data.pageIndex) || 0) || 0)
    if (!bookId) return null
    return {
      book_id: bookId,
      book_title: bookId,
      page_index: pageIndex,
      use_book_page_text: true,
    }
  },

  _splitLongByMinorPunc(part, maxLen) {
    const src = String(part || '').trim()
    if (!src) return []
    if (src.length <= maxLen) return [src]

    const out = []
    let rest = src
    const lowerBound = Math.max(10, Math.floor(maxLen * 0.6))
    const isMinorPunc = (ch) => /[，,、：:]/.test(ch)

    while (rest.length > maxLen) {
      let cut = -1
      for (let i = maxLen; i >= lowerBound; i--) {
        const ch = rest.charAt(i - 1)
        if (isMinorPunc(ch)) {
          cut = i
          break
        }
      }
      if (cut < 0) cut = maxLen
      out.push(rest.slice(0, cut))
      rest = rest.slice(cut)
    }
    if (rest) out.push(rest)
    return out
  },

  _isBuiltinVoice(voiceId) {
    const vid = String(voiceId || '').trim()
    return vid === 'voice_001' || vid === 'voice_002'
  },

  _isLongReadTextForStreaming(text) {
    const norm = this._normalizeReadTextForTts(text)
    if (!norm) return false
    const puncCount = (norm.match(/[。！？!?；;\n]/g) || []).length
    return norm.length >= 120 || (norm.length >= 96 && puncCount >= 4)
  },

  _isVeryLongReadText(text) {
    const norm = this._normalizeReadTextForTts(text)
    if (!norm) return false
    const puncCount = (norm.match(/[。！？!?；;\n]/g) || []).length
    return norm.length >= 220 || (norm.length >= 170 && puncCount >= 8)
  },

  _splitReadText(text, maxLen = 86) {
    const norm = this._normalizeReadTextForTts(text)
    if (!norm) return []

    const units = norm.split(/([。！？!?；;\n])/).filter(Boolean)
    const sentences = []
    let cur = ''
    for (let i = 0; i < units.length; i++) {
      const part = units[i]
      if (/^[。！？!?；;\n]$/.test(part)) {
        cur += part
        if (cur) {
          sentences.push(cur)
          cur = ''
        }
      } else {
        cur += part
      }
    }
    if (cur) sentences.push(cur)

    const out = []
    let buf = ''
    for (let i = 0; i < sentences.length; i++) {
      const s = String(sentences[i] || '').trim()
      if (!s) continue

      if (s.length > maxLen) {
        if (buf) {
          out.push(buf)
          buf = ''
        }
        const parts = this._splitLongByMinorPunc(s, maxLen)
        parts.forEach((p) => {
          const item = String(p || '').trim()
          if (!item) return
          if (item.length < 4 && out.length) {
            out[out.length - 1] += item
          } else {
            out.push(item)
          }
        })
        continue
      }

      if ((buf + s).length <= maxLen) {
        buf += s
      } else {
        if (buf) out.push(buf)
        buf = s
      }
    }
    if (buf) out.push(buf)

    const merged = []
    out.forEach((chunk) => {
      const c = String(chunk || '').trim()
      if (!c) return
      if (c.length < 4 && merged.length) {
        merged[merged.length - 1] += c
      } else {
        merged.push(c)
      }
    })

    return merged.filter((x) => this._isSpeakableText(x))
  },

  _buildReadPlayPlan(text, resolvedVoiceId) {
    const voiceId = String(resolvedVoiceId || this._resolveVoiceId() || this._getAnyAvailableVoiceId() || '').trim()
    if (!voiceId) return []
    const isBuiltin = this._isBuiltinVoice(voiceId)
    const isLongText = this._isLongReadTextForStreaming(text)
    const chunkLen = isLongText ? (isBuiltin ? 72 : 64) : (isBuiltin ? 92 : 80)
    const chunks = this._splitReadText(text, chunkLen)
    return chunks.map((chunk) => this._buildTtsCandidateUrls(chunk, voiceId, isLongText)).filter((x) => Array.isArray(x) && x.length)
  },

  _switchAudioSource(url) {
    if (!this._audio || !url) return
    // 手动切换 src 时，短时间忽略 stop 引发的 ended/error 伪事件，避免跳段漏读。
    this._ignoreAudioEventsUntil = Date.now() + 500
    try { this._audio.stop() } catch (e) {}
    this._audio.src = url
    this._audio.play()
  },

  _isCloneVoice(voiceId) {
    return !!String(voiceId || '').trim() && !this._isBuiltinVoice(voiceId)
  },

  _toAbsoluteAudioUrl(rawUrl) {
    const u = String(rawUrl || '').trim()
    if (!u) return ''
    if (/^https?:\/\//i.test(u)) return u
    const base = resolveApiBase(app)
    if (u.startsWith('/')) return `${base}${u}`
    return `${base}/${u}`
  },

  _requestOneShotAudioUrl(text, voiceId, safer = false) {
    const t = this._normalizeReadTextForTts(text)
    if (!t || !voiceId) return Promise.reject(new Error('invalid one-shot input'))
    const base = resolveApiBase(app)
    const isCloneVoice = this._isCloneVoice(voiceId)
    const isLongText = this._isLongReadTextForStreaming(t)
    const pageCtx = this._buildBookPageTtsContext() || {}
    const data = safer ? {
      voice_id: voiceId,
      text: t,
      text_language: 'zh',
      return_url: true,
          ...pageCtx,
      max_ref_samples: isCloneVoice ? 6 : 3,
      max_aux_refs: isCloneVoice ? 2 : 1,
      top_k: isCloneVoice ? 14 : 14,
      top_p: isCloneVoice ? 0.70 : 0.78,
      temperature: isCloneVoice ? 0.22 : 0.32,
      repetition_penalty: isCloneVoice ? 1.20 : 1.12,
      sample_steps: isCloneVoice ? (isLongText ? 40 : 44) : 38,
      speed: isCloneVoice ? (isLongText ? 1.0 : 0.98) : 1.0,
      hq_user_voice_asr_rerank: isCloneVoice ? true : undefined,
      hq_user_voice_asr_min_ratio: isCloneVoice ? 0.72 : undefined,
      hq_user_voice_asr_timeout_sec: isCloneVoice ? 22 : undefined,
      hq_user_voice_force_policy: isCloneVoice ? (!isLongText) : undefined,
      hq_user_voice_long_trim: isCloneVoice ? false : undefined,
      hq_user_voice_retry_low_energy: isCloneVoice ? true : undefined,
      hq_user_voice_allow_cache_hint: isCloneVoice ? false : undefined,
    } : {
      voice_id: voiceId,
      text: t,
      text_language: 'zh',
      return_url: true,
      ...pageCtx,
      max_ref_samples: isCloneVoice ? 6 : 3,
      max_aux_refs: isCloneVoice ? 2 : 1,
      top_k: isCloneVoice ? 15 : 16,
      top_p: isCloneVoice ? 0.72 : 0.82,
      temperature: isCloneVoice ? 0.24 : 0.34,
      repetition_penalty: isCloneVoice ? 1.18 : 1.12,
      sample_steps: isCloneVoice ? (isLongText ? 36 : 40) : 36,
      speed: isCloneVoice ? (isLongText ? 1.0 : 0.99) : 1.0,
      hq_user_voice_asr_rerank: isCloneVoice ? true : undefined,
      hq_user_voice_asr_min_ratio: isCloneVoice ? 0.70 : undefined,
      hq_user_voice_asr_timeout_sec: isCloneVoice ? 20 : undefined,
      hq_user_voice_force_policy: isCloneVoice ? (!isLongText) : undefined,
      hq_user_voice_long_trim: isCloneVoice ? false : undefined,
      hq_user_voice_retry_low_energy: isCloneVoice ? true : undefined,
      hq_user_voice_allow_cache_hint: isCloneVoice ? false : undefined,
    }

    return new Promise((resolve, reject) => {
      wx.request({
        url: `${base}/synthesize`,
        method: 'POST',
        header: { 'Content-Type': 'application/json' },
        data,
        timeout: 120000,
        success: (res) => {
          const body = (res && res.data) || {}
          if (res.statusCode === 200 && Number(body.code) === 0 && body.audio_url) {
            const abs = this._toAbsoluteAudioUrl(body.audio_url)
            if (!abs) {
              reject(new Error('one-shot audio_url empty'))
              return
            }
            resolve(abs)
            return
          }
          reject(new Error(body.message || 'one-shot 合成失败'))
        },
        fail: (err) => reject(new Error((err && err.errMsg) || 'one-shot 请求失败')),
      })
    })
  },


  _startOneShotPlayback(text, voiceId, safer = false) {
    return this._requestOneShotAudioUrl(text, voiceId, safer).then((url) => {
      if (!this.data.isPlaying) return
      this._playMode = 'single'
      this._singleSafeRetried = !!safer
      this._singleMeta = { text, voiceId }
      this._switchAudioSource(url)
    })
  },

  _handleSingleAudioError(err) {
    if (!this.data.isPlaying) {
      this.stopPlaying()
      return
    }
    const meta = this._singleMeta || {}
    const text = String(meta.text || '')
    const voiceId = String(meta.voiceId || '').trim()
    if (!voiceId || !text) {
      this.stopPlaying()
      return
    }

    if (!this._singleSafeRetried) {
      this._singleSafeRetried = true
      wx.showToast({ title: '正在重试整段朗读...', icon: 'none' })
      this._startOneShotPlayback(text, voiceId, true).catch((e) => {
        console.log('single 安全重试失败，回退 buffered', e)
        this._startBufferedPlayback(text, voiceId).catch((e2) => {
          console.log('buffered 回退失败，改用实时分段', e2)
          const plan = this._buildReadPlayPlan(text, voiceId)
          if (Array.isArray(plan) && plan.length) {
            this._playMode = 'plan'
            this._ttsPlayPlan = plan
            this._ttsChunkIndex = 0
            this._ttsCandidateIndex = 0
            this._playCurrentPlanNode()
            return
          }
          wx.showToast({ title: '音频播放错误', icon: 'none' })
          this.stopPlaying()
        })
      })
      return
    }

    console.log('single 模式连续失败', err)
    wx.showToast({ title: '音频播放错误', icon: 'none' })
    this.stopPlaying()
  },

  _requestBufferedTask(text, voiceId) {
    const t = this._normalizeReadTextForTts(text)
    if (!t || !voiceId) return Promise.reject(new Error('invalid buffered input'))
    const base = resolveApiBase(app)
    const isLongText = this._isLongReadTextForStreaming(t)
    const isVeryLongText = this._isVeryLongReadText(t)
    const isCloneVoice = this._isCloneVoice(voiceId)
    const bufferSegments = isVeryLongText ? 3 : (isLongText ? 2 : 1)
    const cloneLongCutPunc = '。？！；：!?;:…'
    const pageCtx = this._buildBookPageTtsContext() || {}
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${base}/synthesize`,
        method: 'POST',
        header: { 'Content-Type': 'application/json' },
        data: {
          voice_id: voiceId,
          text: t,
          text_language: 'zh',
          media_type: 'wav',
          ...pageCtx,
          buffered: true,
          buffer_segments: bufferSegments,
          max_ref_samples: isCloneVoice ? 6 : 3,
          max_aux_refs: isCloneVoice ? 2 : 1,
          top_k: isCloneVoice ? 15 : 16,
          top_p: isCloneVoice ? 0.72 : 0.82,
          temperature: isCloneVoice ? 0.24 : 0.34,
          repetition_penalty: isCloneVoice ? 1.18 : 1.12,
          long_text_stream: isLongText,
          cut_punc: isLongText ? (isCloneVoice ? cloneLongCutPunc : '，。？！；：,.!?;:、…') : undefined,
          max_text_len: isLongText ? (isCloneVoice ? 84 : 110) : undefined,
          sample_steps: isCloneVoice ? (isLongText ? 36 : 40) : 34,
          speed: isCloneVoice ? (isLongText ? 1.0 : 0.99) : 1.0,
          strict_segmented: isCloneVoice ? false : undefined,
          hq_user_voice_asr_rerank: isCloneVoice ? true : undefined,
          hq_user_voice_asr_min_ratio: isCloneVoice ? 0.72 : undefined,
          hq_user_voice_asr_timeout_sec: isCloneVoice ? 22 : undefined,
          hq_user_voice_force_policy: isCloneVoice ? (!isLongText) : undefined,
          hq_user_voice_long_trim: isCloneVoice ? false : undefined,
          hq_user_voice_retry_low_energy: isCloneVoice ? true : undefined,
          hq_user_voice_allow_cache_hint: isCloneVoice ? false : undefined,
        },
        success: (res) => {
          const data = (res && res.data) || {}
          if (res.statusCode === 200 && Number(data.code) === 0 && data.task_id) {
            const segs = Array.isArray(data.segments) ? data.segments.map((x) => this._toAbsoluteAudioUrl(x)).filter(Boolean) : []
            resolve({ taskId: String(data.task_id), total: Number(data.total_segments || 0), segments: segs })
            return
          }
          reject(new Error(data.message || 'buffered 任务创建失败'))
        },
        fail: (err) => reject(new Error((err && err.errMsg) || 'buffered 请求失败')),
      })
    })
  },



  _fetchBufferedSegment(taskId, index, retry = 0, maxRetry = 100) {
    const base = resolveApiBase(app)
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${base}/synthesize/buffered/segment?task_id=${encodeURIComponent(taskId)}&index=${encodeURIComponent(index)}`,
        method: 'GET',
        success: (res) => {
          const data = (res && res.data) || {}
          if (res.statusCode === 200 && Number(data.code) === 0 && data.audio_url) {
            resolve(this._toAbsoluteAudioUrl(data.audio_url))
            return
          }
          if (res.statusCode === 202 || Number(data.code) === 1) {
            if (retry >= Number(maxRetry || 100)) {
              reject(new Error('buffered 分片等待超时'))
              return
            }
            const waitMs = retry < 16 ? 220 : 320
            setTimeout(() => {
              this._fetchBufferedSegment(taskId, index, retry + 1, maxRetry).then(resolve).catch(reject)
            }, waitMs)
            return
          }
          reject(new Error(data.message || 'buffered 分片获取失败'))
        },
        fail: (err) => reject(new Error((err && err.errMsg) || 'buffered 分片请求失败')),
      })
    })
  },


  _fetchBufferedStatus(taskId) {
    const base = resolveApiBase(app)
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${base}/synthesize/buffered/status?task_id=${encodeURIComponent(taskId)}`,
        method: 'GET',
        success: (res) => {
          const data = (res && res.data) || {}
          if (res.statusCode === 200 && Number(data.code) === 0) {
            resolve(data)
            return
          }
          reject(new Error(data.message || 'buffered 状态获取失败'))
        },
        fail: (err) => reject(new Error((err && err.errMsg) || 'buffered 状态请求失败')),
      })
    })
  },

  _waitBufferedReady(taskId, state = {}) {
    const retry = Number(state.retry || 0)
    const lastReady = Number(state.lastReady ?? -1)
    const startedAt = Number(state.startedAt || Date.now())
    const maxWaitMs = 9500

    return this._fetchBufferedStatus(taskId).then((st) => {
      const total = Number(st.total || 0)
      const ready = Number(st.ready || 0)
      const done = !!st.done
      const mergedUrl = this._toAbsoluteAudioUrl(st.merged_url)

      if (mergedUrl) return mergedUrl
      if (total > 0 && (ready >= total || done)) return ''

      const elapsed = Date.now() - startedAt
      if (elapsed >= maxWaitMs || retry >= 30) {
        throw new Error('buffered 合并等待超时，改走快速回退')
      }

      const progressed = ready > lastReady
      const delay = progressed ? 140 : Math.min(820, 220 + retry * 45)
      return new Promise((resolve, reject) => {
        setTimeout(() => {
          this._waitBufferedReady(taskId, {
            retry: retry + 1,
            lastReady: Math.max(lastReady, ready),
            startedAt,
          }).then(resolve).catch(reject)
        }, delay)
      })
    })
  },

  _fetchBufferedMerged(taskId, retry = 0) {
    const base = resolveApiBase(app)
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${base}/synthesize/buffered/merged?task_id=${encodeURIComponent(taskId)}`,
        method: 'GET',
        success: (res) => {
          const data = (res && res.data) || {}
          if (res.statusCode === 200 && Number(data.code) === 0 && data.audio_url) {
            resolve(this._toAbsoluteAudioUrl(data.audio_url))
            return
          }
          if (res.statusCode === 202 || Number(data.code) === 1) {
            if (retry >= 12) {
              reject(new Error('buffered 合并音频等待超时'))
              return
            }
            const delay = Math.min(900, 180 + retry * 80)
            setTimeout(() => {
              this._fetchBufferedMerged(taskId, retry + 1).then(resolve).catch(reject)
            }, delay)
            return
          }
          reject(new Error(data.message || 'buffered 合并音频获取失败'))
        },
        fail: (err) => reject(new Error((err && err.errMsg) || 'buffered 合并音频请求失败')),
      })
    })
  },

  _startBufferedMergedPlayback(text, voiceId) {
    return this._requestBufferedTask(text, voiceId).then((task) => {
      if (!task || !task.taskId || Number(task.total || 0) <= 0) {
        throw new Error('buffered 合并任务无有效分片')
      }
      return this._waitBufferedReady(task.taskId).then((readyUrl) => {
        if (readyUrl) return readyUrl
        return this._fetchBufferedMerged(task.taskId)
      }).then((url) => {
        if (!this.data.isPlaying) return
        this._playMode = 'merged'
        this._mergedMeta = { text, voiceId, taskId: task.taskId }
        this._mergedRetried = false
        this._switchAudioSource(url)
      })
    })
  },

  _countBufferedReady(st) {
    const segs = (st && Array.isArray(st.segments)) ? st.segments : []
    let ready = 0
    for (let i = 0; i < segs.length; i++) {
      if (segs[i]) ready += 1
    }
    return ready
  },

  _ensureBufferedSegment(index) {
    const st = this._bufferedPlayback
    if (!st || !this.data.isPlaying) return Promise.reject(new Error('buffered playback stopped'))
    const idx = Number(index || 0)
    if (idx < 0 || idx >= Number(st.total || 0)) return Promise.reject(new Error('buffered index out of range'))

    const hit = st.segments[idx]
    if (hit) return Promise.resolve(hit)

    if (!st.pendingFetchMap || typeof st.pendingFetchMap !== 'object') {
      st.pendingFetchMap = {}
    }
    if (st.pendingFetchMap[idx]) return st.pendingFetchMap[idx]

    st.pendingFetchMap[idx] = this._fetchBufferedSegment(st.taskId, idx, 0, Number(st.segmentFetchMaxRetry || 40)).then((url) => {
      if (!url) throw new Error('buffered segment empty')
      st.segments[idx] = url
      return url
    }).finally(() => {
      if (st.pendingFetchMap && st.pendingFetchMap[idx]) delete st.pendingFetchMap[idx]
    })
    return st.pendingFetchMap[idx]
  },

  _prefetchBufferedAhead(fromIndex = -1, distance = 2) {
    const st = this._bufferedPlayback
    if (!st || !this.data.isPlaying || this._playMode !== 'buffered') return
    const total = Number(st.total || 0)
    if (total <= 0) return

    const baseIndex = Number(fromIndex)
    const start = (Number.isFinite(baseIndex) && baseIndex >= 0)
      ? baseIndex + 1
      : Number(st.currentIndex || 0) + 1
    const ahead = Math.max(1, Number(distance || st.preloadAhead || 2))
    const end = Math.min(total, start + ahead)

    for (let i = start; i < end; i++) {
      if (!st.segments[i]) {
        this._ensureBufferedSegment(i).catch(() => {})
      }
    }
  },

  _waitBufferedWarmup(minReady = 1, timeoutMs = 3200) {
    const st = this._bufferedPlayback
    if (!st || !this.data.isPlaying || this._playMode !== 'buffered') return Promise.resolve()

    const total = Number(st.total || 0)
    const target = Math.max(1, Math.min(total, Number(minReady || 1)))
    if (target <= 1) return Promise.resolve()

    const startedAt = Date.now()
    const loop = (retry = 0) => {
      if (!this.data.isPlaying || this._playMode !== 'buffered') return Promise.resolve()
      const localReady = this._countBufferedReady(st)
      if (localReady >= target) return Promise.resolve()
      if (Date.now() - startedAt >= Number(timeoutMs || 0)) return Promise.resolve()

      return this._fetchBufferedStatus(st.taskId).catch(() => null).then((bs) => {
        if (bs && Number(bs.code) === 0) {
          const remoteReady = Math.max(0, Number(bs.ready || 0))
          const cap = Math.min(total, remoteReady)
          const jobs = []
          for (let i = 0; i < cap; i++) {
            if (!st.segments[i]) jobs.push(this._ensureBufferedSegment(i).catch(() => null))
          }
          if (jobs.length) return Promise.all(jobs)
        }
        return null
      }).then(() => {
        const nowReady = this._countBufferedReady(st)
        if (nowReady >= target) return
        const delay = Math.min(760, 140 + retry * 55)
        return new Promise((resolve) => setTimeout(resolve, delay)).then(() => loop(retry + 1))
      })
    }

    return loop()
  },

  _playBufferedIndex(index) {
    const st = this._bufferedPlayback
    if (!st || !this.data.isPlaying) return Promise.reject(new Error('buffered playback stopped'))
    const idx = Number(index || 0)
    if (idx < 0 || idx >= Number(st.total || 0)) return Promise.reject(new Error('buffered index out of range'))

    return this._ensureBufferedSegment(idx).then((url) => {
      if (!url) throw new Error('buffered segment empty')
      st.currentIndex = idx
      st.errorRetries = 0
      st.stallRetry = 0
      this._switchAudioSource(url)
      this._prefetchBufferedAhead(idx, st.preloadAhead)
    })
  },

  _advanceBufferedPlayback() {
    const st = this._bufferedPlayback
    if (!st || !this.data.isPlaying) {
      this.stopPlaying()
      return
    }
    const next = Number(st.currentIndex || 0) + 1
    if (next >= Number(st.total || 0)) {
      this.stopPlaying()
      return
    }
    this._playBufferedIndex(next).catch((err) => {
      st.stallRetry = Number(st.stallRetry || 0) + 1
      const maxStallRetry = Number(st.maxStallRetry || 10)
      if (st.stallRetry <= maxStallRetry && this.data.isPlaying && this._playMode === 'buffered') {
        this._prefetchBufferedAhead(next - 1, Number(st.preloadAhead || 2) + 1)
        const delay = Math.min(1000, 160 + st.stallRetry * 90)
        setTimeout(() => {
          if (!this.data.isPlaying || this._playMode !== 'buffered') return
          this._advanceBufferedPlayback()
        }, delay)
        return
      }
      console.log('buffered 下一段播放失败', err)
      wx.showToast({ title: '朗读分片加载失败', icon: 'none' })
      this.stopPlaying()
    })
  },

  _handleBufferedAudioError(err) {
    const st = this._bufferedPlayback
    if (!st || !this.data.isPlaying) {
      this.stopPlaying()
      return
    }
    st.errorRetries = Number(st.errorRetries || 0) + 1
    if (st.errorRetries > 2) {
      console.log('buffered 分片连续失败', err)
      wx.showToast({ title: '音频播放错误', icon: 'none' })
      this.stopPlaying()
      return
    }
    const cur = Number(st.currentIndex || 0)
    this._prefetchBufferedAhead(cur - 1, Number(st.preloadAhead || 2) + 1)
    this._playBufferedIndex(cur).catch((e) => {
      console.log('buffered 分片重试失败', e)
      wx.showToast({ title: '音频播放错误', icon: 'none' })
      this.stopPlaying()
    })
  },

  _handleMergedAudioError(err) {
    const meta = this._mergedMeta || {}
    const text = String(meta.text || '')
    const voiceId = String(meta.voiceId || '').trim()
    if (!this.data.isPlaying || !text || !voiceId) {
      this.stopPlaying()
      return
    }

    if (!this._mergedRetried) {
      this._mergedRetried = true
      wx.showToast({ title: '正在回退分片朗读...', icon: 'none' })
      this._startBufferedPlayback(text, voiceId).catch((e) => {
        console.log('merged 回退 buffered 分片失败', e)
        const plan = this._buildReadPlayPlan(text, voiceId)
        if (Array.isArray(plan) && plan.length) {
          this._playMode = 'plan'
          this._ttsPlayPlan = plan
          this._ttsChunkIndex = 0
          this._ttsCandidateIndex = 0
          this._playCurrentPlanNode()
          return
        }
        wx.showToast({ title: '音频播放错误', icon: 'none' })
        this.stopPlaying()
      })
      return
    }

    console.log('merged 模式连续失败', err)
    wx.showToast({ title: '音频播放错误', icon: 'none' })
    this.stopPlaying()
  },

  _startBufferedPlayback(text, voiceId) {
    return this._requestBufferedTask(text, voiceId).then((task) => {
      if (!task || !task.taskId || Number(task.total || 0) <= 0) {
        throw new Error('buffered 任务无有效分片')
      }

      const total = Number(task.total || 0)
      const isLongText = this._isLongReadTextForStreaming(text)
      const isVeryLongText = this._isVeryLongReadText(text)
      const preloadAhead = isVeryLongText ? 8 : (isLongText ? 6 : 3)
      const minReadyToStart = isVeryLongText ? Math.min(total, 4) : (isLongText ? Math.min(total, 3) : 1)
      const warmupTimeoutMs = isVeryLongText ? 22000 : (isLongText ? 15000 : 4000)

      this._bufferedPlayback = {
        taskId: task.taskId,
        total,
        segments: Array.from({ length: total }, () => ''),
        currentIndex: 0,
        errorRetries: 0,
        stallRetry: 0,
        maxStallRetry: isVeryLongText ? 60 : (isLongText ? 45 : 18),
        segmentFetchMaxRetry: isVeryLongText ? 240 : (isLongText ? 200 : 100),
        preloadAhead,
        minReadyToStart,
        warmupTimeoutMs,
        pendingFetchMap: {},
      }
      task.segments.forEach((u, i) => {
        if (i < this._bufferedPlayback.segments.length) this._bufferedPlayback.segments[i] = u
      })
      this._playMode = 'buffered'
      this._prefetchBufferedAhead(-1, preloadAhead)
      return this._waitBufferedWarmup(minReadyToStart, warmupTimeoutMs).catch(() => null).then(() => this._playBufferedIndex(0))
    })
  },


  _playCurrentPlanNode() {
    const plan = Array.isArray(this._ttsPlayPlan) ? this._ttsPlayPlan : []
    if (!plan.length) {
      this.stopPlaying()
      return
    }
    const ci = Number(this._ttsChunkIndex || 0)
    if (ci >= plan.length) {
      this.stopPlaying()
      return
    }
    const cand = Array.isArray(plan[ci]) ? plan[ci] : []
    const vi = Number(this._ttsCandidateIndex || 0)
    if (vi >= cand.length) {
      this.stopPlaying()
      return
    }
    this._currentPlanChunk = ci
    const url = cand[vi]
    this._switchAudioSource(url)
  },

  _markPlanChunkPlayed(idx) {
    if (!this._ttsPlayedChunkMap || typeof this._ttsPlayedChunkMap !== 'object') {
      this._ttsPlayedChunkMap = {}
    }
    if (Number.isInteger(idx) && idx >= 0) {
      this._ttsPlayedChunkMap[idx] = true
    }
  },

  _verifyAndFinalizePlanPlayback() {
    const plan = Array.isArray(this._ttsPlayPlan) ? this._ttsPlayPlan : []
    if (!plan.length) {
      this.stopPlaying()
      return
    }

    const playedMap = (this._ttsPlayedChunkMap && typeof this._ttsPlayedChunkMap === 'object') ? this._ttsPlayedChunkMap : {}
    const missing = []
    for (let i = 0; i < plan.length; i++) {
      if (!playedMap[i]) missing.push(i)
    }

    if (!missing.length) {
      this.stopPlaying()
      return
    }

    const retried = Number(this._planFinalizeRetry || 0)
    if (retried >= 2) {
      wx.showToast({ title: '尾段补齐失败', icon: 'none' })
      this.stopPlaying()
      return
    }

    const target = missing[0]
    this._planFinalizeRetry = retried + 1
    this._ttsChunkIndex = target
    this._ttsCandidateIndex = 0
    this._playMode = 'plan'
    wx.showToast({ title: '正在补齐尾段...', icon: 'none' })
    this._playCurrentPlanNode()
  },


  _buildTtsCandidateUrls(text, resolvedVoiceId, forceStrictLong = false) {
    const t = this._normalizeReadTextForTts(text)
    if (!t) return []

    const base = resolveApiBase(app)
    const voiceId = String(resolvedVoiceId || this._resolveVoiceId() || this._getAnyAvailableVoiceId() || '').trim()
    if (!voiceId) return []
    const builtin = this._isBuiltinVoice(voiceId)
    const isLongText = !!forceStrictLong || this._isLongReadTextForStreaming(t)
    const isCloneVoice = this._isCloneVoice(voiceId)
    const cloneLongCutPunc = encodeURIComponent('。？！；：!?;:…')

    const pageCtx = this._buildBookPageTtsContext()
    const pageQuery = pageCtx ? [
      `book_id=${encodeURIComponent(pageCtx.book_id || '')}`,
      `book_title=${encodeURIComponent(pageCtx.book_title || '')}`,
      `page_index=${encodeURIComponent(String(pageCtx.page_index || 0))}`,
      `use_book_page_text=1`,
    ] : []

    const build = (vid, params) => {
      const q = [
        `voice_id=${encodeURIComponent(vid)}`,
        `text=${encodeURIComponent(t)}`,
        `text_language=zh`,
        `media_type=wav`,
        `stream_mode=close`,
        ...pageQuery,
        isCloneVoice ? `max_ref_samples=6` : `max_ref_samples=3`,
        isCloneVoice ? `max_aux_refs=2` : `max_aux_refs=1`,
        isCloneVoice ? `hq_user_voice_asr_rerank=1` : '',
        isCloneVoice ? `hq_user_voice_asr_min_ratio=0.72` : '',
        isCloneVoice ? `hq_user_voice_force_policy=${isLongText ? 0 : 1}` : '',
        isCloneVoice ? `hq_user_voice_long_trim=0` : '',
        isCloneVoice ? `hq_user_voice_retry_low_energy=1` : '',
        isCloneVoice ? `hq_user_voice_allow_cache_hint=0` : '',
        isCloneVoice && isLongText ? `cut_punc=${cloneLongCutPunc}` : '',
        isCloneVoice && isLongText ? `max_text_len=84` : '',
        ...params,
        `ts=${Date.now()}`,
      ].filter(Boolean).join('&')
      return `${base}/synthesize/stream?${q}`
    }

    if (builtin) {
      return [
        build(voiceId, ['top_k=16', 'top_p=0.80', 'temperature=0.32', 'repetition_penalty=1.12', 'sample_steps=34', 'speed=1.0']),
        build(voiceId, ['top_k=14', 'top_p=0.76', 'temperature=0.30', 'repetition_penalty=1.10', 'sample_steps=30', 'speed=1.0']),
      ]
    }

    // 克隆音色优先稳态：降低速率并抬高采样步数，次选保留可接受速度。
    return [
      build(voiceId, [`top_k=15`, `top_p=0.72`, `temperature=0.24`, `repetition_penalty=1.18`, `sample_steps=${isLongText ? 36 : 40}`, `speed=${isLongText ? 1.0 : 0.99}`]),
      build(voiceId, [`top_k=14`, `top_p=0.70`, `temperature=0.22`, `repetition_penalty=1.20`, `sample_steps=${isLongText ? 34 : 38}`, `speed=${isLongText ? 1.02 : 0.98}`]),
    ]
  },


  _playTtsCandidates(urls) {
    const list = Array.isArray(urls) ? urls.filter(Boolean) : []
    if (!list.length) {
      wx.showToast({ title: '没有可朗读的文字', icon: 'none' })
      this.stopPlaying()
      return
    }
    this._ttsCandidateUrls = list
    this._ttsCandidateIndex = 0
    this._switchAudioSource(list[0])
  },

  // 开始播放
  async startPlaying(voice) {
    const playMode = String(voice || 'custom').trim() || 'custom';
    this.setData({
      isPlaying: playMode
    });

    await this._ensureVoiceReady();
    const roleKey = playMode === 'mom' ? 'mom' : (playMode === 'dad' ? 'dad' : '');
    const selected = this._resolvePlaybackVoice(roleKey);
    this.setData({ selectedVoiceName: selected.voiceName });

    this.ensureAudio()
    this._playMode = ''
    this._bufferedPlayback = null
    this._mergedMeta = null
    this._mergedRetried = false
    this._singleSafeRetried = false
    this._singleMeta = null
    this._ttsPlayedChunkMap = {}
    this._planFinalizeRetry = 0
    this._currentPlanChunk = -1

    const rawText = this.data.currentText || ''
    const isLongText = this._isLongReadTextForStreaming(rawText)

    if (this._isBuiltinVoice(selected.voiceId)) {
      try {
        await this._startOneShotPlayback(rawText, selected.voiceId, false)
        return
      } catch (eBaseOneShot) {
        console.log('基础音色 one-shot 失败，回退 buffered', eBaseOneShot)
      }
      try {
        await this._startBufferedPlayback(rawText, selected.voiceId)
        return
      } catch (eBaseBuffered) {
        console.log('基础音色 buffered 失败，回退 plan', eBaseBuffered)
      }
    }

    if (isLongText) {
      const isVeryLongText = this._isVeryLongReadText(rawText)
      if (isVeryLongText) {
        try {
          await this._startBufferedMergedPlayback(rawText, selected.voiceId)
          return
        } catch (eMergedLong) {
          console.log('超长文本合并缓冲失败，回退分段缓冲', eMergedLong)
        }
      }

      try {
        await this._startBufferedPlayback(rawText, selected.voiceId)
        return
      } catch (eLong) {
        console.log('长文本分段缓冲失败，回退 plan 分段', eLong)
      }

      const longPlan = this._buildReadPlayPlan(rawText, selected.voiceId)
      if (Array.isArray(longPlan) && longPlan.length) {
        this._playMode = 'plan'
        this._ttsPlayPlan = longPlan
        this._ttsChunkIndex = 0
        this._ttsCandidateIndex = 0
        this._ttsPlayedChunkMap = {}
        this._planFinalizeRetry = 0
        this._currentPlanChunk = 0
        this._playCurrentPlanNode()
        return
      }
    }

    if (this._isCloneVoice(selected.voiceId)) {
      try {
        await this._startBufferedMergedPlayback(rawText, selected.voiceId)
        return
      } catch (e0) {
        console.log('buffered merged 模式失败，回退 single', e0)
        try {
          await this._startOneShotPlayback(rawText, selected.voiceId, false)
          return
        } catch (e) {
          console.log('single 模式失败，回退 buffered 分片', e)
          try {
            await this._startBufferedPlayback(rawText, selected.voiceId)
            return
          } catch (e2) {
            console.log('buffered 分片模式失败，回退实时分段', e2)
          }
        }
      }
    }

    const plan = this._buildReadPlayPlan(rawText, selected.voiceId)
    if (!Array.isArray(plan) || !plan.length) {
      wx.showToast({ title: '当前音色不可用或文本为空', icon: 'none' })
      this.stopPlaying()
      return
    }

    try {
      this._playMode = 'plan'
      this._ttsPlayPlan = plan
      this._ttsChunkIndex = 0
      this._ttsCandidateIndex = 0
      this._ttsPlayedChunkMap = {}
      this._planFinalizeRetry = 0
      this._currentPlanChunk = 0
      this._playCurrentPlanNode()
    } catch (e) {
      console.log('播放失败', e)
      wx.showToast({ title: '播放失败', icon: 'none' })
      this.stopPlaying()
      return
    }

  },

  // 停止播放
  stopPlaying() {
    try {
      if (this._audio) this._audio.stop()
    } catch (e) {}
    this._ttsPlayPlan = []
    this._ttsChunkIndex = 0
    this._ttsCandidateIndex = 0
    this._ignoreAudioEventsUntil = 0
    this._playMode = ''
    this._bufferedPlayback = null
    this._mergedMeta = null
    this._mergedRetried = false
    this._singleSafeRetried = false
    this._singleMeta = null
    this._ttsPlayedChunkMap = {}
    this._planFinalizeRetry = 0
    this._currentPlanChunk = -1
    this.setData({
      isPlaying: null
    });
  },

  ensureAudio() {
    if (this._audio) return
    this._audio = wx.createInnerAudioContext()
    this._audio.autoplay = false
    this._audio.onEnded(() => {
      if (Date.now() < Number(this._ignoreAudioEventsUntil || 0)) return
      if (!this.data.isPlaying) return

      if (this._playMode === 'single') {
        this.stopPlaying()
        return
      }

      if (this._playMode === 'merged') {
        this.stopPlaying()
        return
      }

      if (this._playMode === 'buffered') {
        this._advanceBufferedPlayback()
        return
      }

      const plan = Array.isArray(this._ttsPlayPlan) ? this._ttsPlayPlan : []
      const ci = Number(this._ttsChunkIndex || 0)
      if (ci >= 0 && ci < plan.length) {
        this._markPlanChunkPlayed(ci)
      }
      if (ci + 1 < plan.length) {
        this._ttsChunkIndex = ci + 1
        this._ttsCandidateIndex = 0
        this._playCurrentPlanNode()
        return
      }
      this._verifyAndFinalizePlanPlayback()
    })
    this._audio.onError((err) => {
      if (Date.now() < Number(this._ignoreAudioEventsUntil || 0)) return
      console.log('音频错误', err)

      if (this._playMode === 'single') {
        this._handleSingleAudioError(err)
        return
      }

      if (this._playMode === 'merged') {
        this._handleMergedAudioError(err)
        return
      }

      if (this._playMode === 'buffered') {
        this._handleBufferedAudioError(err)
        return
      }

      const plan = Array.isArray(this._ttsPlayPlan) ? this._ttsPlayPlan : []
      const ci = Number(this._ttsChunkIndex || 0)
      const curList = Array.isArray(plan[ci]) ? plan[ci] : []
      const vi = Number(this._ttsCandidateIndex || 0)

      if (this.data.isPlaying && vi + 1 < curList.length) {
        this._ttsCandidateIndex = vi + 1
        wx.showToast({ title: '正在优化重试朗读...', icon: 'none' })
        try {
          this._playCurrentPlanNode()
          return
        } catch (e) {
          console.log('重试播放失败', e)
        }
      }

      if (this.data.isPlaying) this.setData({ isPlaying: null })
      wx.showToast({ title: '音频播放错误', icon: 'none' })
    })
  },

  buildTtsUrl(text, voice, resolvedVoiceId) {
    const t = String(text || '').trim()
    if (!t) return ''

    const base = resolveApiBase(app)
    const voiceId = String(resolvedVoiceId || this._resolveVoiceId() || this._getAnyAvailableVoiceId() || '').trim()
    if (!voiceId) return ''
    const isCloneVoice = this._isCloneVoice(voiceId)
    const isLongText = this._isLongReadTextForStreaming(t)
    const cloneLongCutPunc = encodeURIComponent('。？！；：!?;:…')

    const pageCtx = this._buildBookPageTtsContext()
    const pageQuery = pageCtx ? [
      `book_id=${encodeURIComponent(pageCtx.book_id || '')}`,
      `book_title=${encodeURIComponent(pageCtx.book_title || '')}`,
      `page_index=${encodeURIComponent(String(pageCtx.page_index || 0))}`,
      `use_book_page_text=1`,
    ] : []

    const q = [
      `voice_id=${encodeURIComponent(voiceId)}`,
      `text=${encodeURIComponent(t)}`,
      `text_language=zh`,
      `media_type=wav`,
      `stream_mode=close`,
      ...pageQuery,
      isCloneVoice ? `max_ref_samples=6` : `max_ref_samples=3`,
      isCloneVoice ? `max_aux_refs=2` : `max_aux_refs=1`,
      `top_k=${isCloneVoice ? 15 : 18}`,
      `top_p=${isCloneVoice ? 0.72 : 0.82}`,
      `temperature=${isCloneVoice ? 0.24 : 0.34}`,
      `repetition_penalty=${isCloneVoice ? 1.18 : 1.12}`,
      `sample_steps=${isCloneVoice ? (isLongText ? 36 : 40) : 36}`,
      `speed=${isCloneVoice ? (isLongText ? 1.0 : 0.99) : 1.0}`,
      isCloneVoice ? `hq_user_voice_asr_rerank=1` : '',
      isCloneVoice ? `hq_user_voice_asr_min_ratio=0.72` : '',
      isCloneVoice ? `hq_user_voice_force_policy=${isLongText ? 0 : 1}` : '',
      isCloneVoice ? `hq_user_voice_long_trim=0` : '',
      isCloneVoice ? `hq_user_voice_retry_low_energy=1` : '',
      isCloneVoice ? `hq_user_voice_allow_cache_hint=0` : '',
      isCloneVoice && isLongText ? `cut_punc=${cloneLongCutPunc}` : '',
      isCloneVoice && isLongText ? `max_text_len=84` : '',
    ].filter(Boolean).join('&')

    return `${base}/synthesize/stream?${q}`
  },


  // 切换收藏

  // 切换收藏
  toggleFavorite() {
    let favorites = app.globalData.favorites || [];
    const index = favorites.findIndex(fav => fav.id === this.data.bookId);

    if (index > -1) {
      // 取消收藏
      favorites.splice(index, 1);
      wx.showToast({
        title: '已取消收藏',
        icon: 'success',
      });
    } else {
      // 添加收藏
      favorites.push({
        id: this.data.bookId,
        title: this.data.book.title,
        cover: this.data.book.image,
      });
      wx.showToast({
        title: '收藏成功',
        icon: 'success',
      });
      
    
    }

    // 更新全局数据
    app.globalData.favorites = favorites;
    
    // 保存到本地
    try {
      wx.setStorageSync('favorites', favorites);
    } catch (e) {
      console.log('保存失败', e);
    }

    // 更新状态
    this.checkFavoriteStatus();
  },

  // 跳转到上一本书
  gotoPrevBook() {
    // 已移除内置测试绘本：上一/下一本由后端返回的列表或推荐页承担
    wx.showToast({ title: "请返回书架选择绘本", icon: "none" });
  },

  // 跳转到下一本书
  gotoNextBook() {
    wx.showToast({ title: "请返回书架选择绘本", icon: "none" });
  },

  onUnload() {
    this._flushReadingMinutes();
    this._saveRecentReading();
    this.stopPlaying()
    try {
      if (this._audio) this._audio.destroy()
    } catch (e) {}
  },

  _dateKey() {
    const d = new Date();
    const m = d.getMonth() + 1;
    const day = d.getDate();
    const mm = m < 10 ? `0${m}` : `${m}`;
    const dd = day < 10 ? `0${day}` : `${day}`;
    return `${d.getFullYear()}-${mm}-${dd}`;
  },

  _flushReadingMinutes() {
    try {
      const now = Date.now();
      const start = Number(this._readingStartTs || 0) || 0;
      if (start > 0 && now > start) {
        this._readingAccumulatedMs = Number(this._readingAccumulatedMs || 0) + (now - start);
      }
      this._readingStartTs = 0;
      const ms = Number(this._readingAccumulatedMs || 0) || 0;
      if (ms < 10 * 1000) return; // 少于10秒不计，防止误触
      const minutes = Math.max(0, Math.round(ms / 60000));
      const key = this._dateKey();
      const storageKey = `readingMinutes.${key}`;
      const prev = Number(wx.getStorageSync(storageKey) || 0) || 0;
      wx.setStorageSync(storageKey, Math.max(0, prev + minutes));
      this._readingAccumulatedMs = 0;
    } catch (e) {}
  },

  _saveRecentReading() {
    try {
      const book = this.data.book || {};
      const bookId = String(this.data.bookId || "").trim();
      if (!bookId) return;
      const title = String(book.title || "绘本");
      const source = String(this.data.source || "");
      const pageIndex = Math.max(0, Number(this.data.pageIndex || 0) || 0);
      const totalPages = Math.max(1, Number(this.data.totalPages || 1) || 1);
      let coverImage = "";
      if (source === "library") {
        const pages = Array.isArray(book.pages) ? book.pages : [];
        const p = pages[pageIndex] || pages[0] || {};
        coverImage = String((p && p.image) || book.image || "");
      } else {
        coverImage = String(book.image || "");
      }
      const now = Date.now();
      const oldRaw = wx.getStorageSync("readingRecent");
      const oldList = Array.isArray(oldRaw) ? oldRaw : [];
      const nextItem = { bookId, title, coverImage, source, pageIndex, totalPages, updatedAt: now };
      const merged = [nextItem, ...oldList.filter((x) => String((x && x.bookId) || "") !== bookId)].slice(0, 20);
      wx.setStorageSync("readingRecent", merged);
    } catch (e) {}
  },

  initReadGuide() {
    if (!isMainDone("voiceDone")) return;
    if (isMainDone("readDone")) return;
    const steps = [
      {
        highlight: "voice",
        title: "用刚训练的音色朗读",
        desc: "点击“听你想听的声音读”先选音色，再点击“开始朗读”播放当前音色。",
      },
      {
        highlight: "next",
        title: "翻到末页完成阅读",
        desc: "读完最后一页会上报完成事件，并推动伴宠成长。",
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
