const app = getApp();
const { buildAiStoryPrompt, PROMPT_EDIT_HINT } = require('../../utils/ai-story-prompt.js');

function getApiBase() {
  return (app && app.getApiBaseUrl) ? app.getApiBaseUrl() : 'http://127.0.0.1:9880';
}

const AI_STORY_ENDPOINTS = [
  '/practice/ai_story_from_image',
  '/readalong/ai_story_from_image',
  '/ai_story_from_image',
];

Page({
  data: {
    step: 'upload',
    isGenerating: false,
    uploadedImage: '',
    progress: 0,
    rotateClass: 'rotateClass',
    ageOptions: [
      { label: '2-3岁', desc: '短句重复，更多拟声词' },
      { label: '4-5岁', desc: '情节清晰，适合亲子共读' },
      { label: '6-8岁', desc: '细节更丰富，增加思考点' },
    ],
    ageIndex: 1,
    storyId: '',
    storyTitle: '',
    storyPages: [],
    currentPage: 0,
    totalPages: 0,
    currentPageText: '',
    imageCaption: '',
    aiUsed: false,
  },

  onLoad() {
    const profileAge = String((app && app.globalData && app.globalData.userData && app.globalData.userData.babyAge) || '').trim();
    const ageNum = parseInt(profileAge, 10);
    let ageIndex = 1;
    if (!Number.isNaN(ageNum)) {
      if (ageNum <= 3) ageIndex = 0;
      else if (ageNum >= 6) ageIndex = 2;
    }
    this.setData({ ageIndex });
    this._promptEditHint = PROMPT_EDIT_HINT;
  },

  goBack() {
    wx.navigateBack();
  },

  takePhoto() {
    if (this.data.isGenerating) return;
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['camera'],
      success: (res) => this.handleImageSelected(res.tempFilePaths[0])
    });
  },

  chooseImage() {
    if (this.data.isGenerating) return;
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album'],
      success: (res) => this.handleImageSelected(res.tempFilePaths[0])
    });
  },

  _isDomainListError(msg) {
    const m = String(msg || '').toLowerCase();
    return m.includes('not in domain list') || m.includes('url not in domain');
  },

  _makeReasonError(message, reason, detail = '') {
    const err = new Error(message || '生成失败');
    err.reason = reason || 'UNKNOWN';
    if (detail) err.detail = String(detail);
    return err;
  },

  _wrapNetworkError(err, fallbackTitle) {
    const raw = String((err && err.errMsg) || err || fallbackTitle || '网络请求失败');
    if (this._isDomainListError(raw)) {
      const base = (app && app.getApiBaseUrl) ? app.getApiBaseUrl() : 'http://127.0.0.1:9880';
      wx.showModal({
        title: '域名未在白名单',
        content: `当前接口域名未加入白名单：${base}。请在小程序后台开发设置-服务器域名添加该域名。`,
        showCancel: false
      });
      return this._makeReasonError('接口域名未在小程序白名单，请按提示处理后重试', 'DOMAIN_WHITELIST', raw);
    }
    return this._makeReasonError(raw || fallbackTitle || '网络请求失败', 'NETWORK_ERROR', raw);
  },

  _classifyDisplayError(err) {
    const reason = String((err && err.reason) || 'UNKNOWN');
    const message = String((err && err.message) || '生成失败');
    const detail = String((err && err.detail) || message);

    if (reason === 'DOMAIN_WHITELIST') {
      return { title: '域名白名单未配置', detail: '请在小程序后台配置服务器域名后重试。' };
    }
    if (reason === 'STORY_ENDPOINT_MISSING') {
      return { title: '绘本接口未部署', detail: '当前后端未提供 ai_story_from_image 路由。请检查后端服务版本。' };
    }
    if (reason === 'CAPTION_ENDPOINT_MISSING') {
      return { title: '识图接口未部署', detail: '当前后端未提供 /readalong/image_caption 路由。请先启动 readalong 服务。' };
    }
    if (reason === 'CAPTION_WEAK') {
      return { title: '图片理解太弱', detail: '识图结果过于笼统，已阻止生成无关故事。建议换一张主体更清晰的照片。' };
    }
    if (reason === 'CAPTION_FAIL') {
      return { title: '图片识别失败', detail: '无法获得有效图片描述，请稍后重试。' };
    }
    if (reason === 'ALIGNMENT_BLOCKED') {
      return { title: '图文一致性过低', detail: '已阻止可能跑题的生成结果，请重试。' };
    }
    if (reason === 'NETWORK_ERROR') {
      return { title: '网络请求失败', detail };
    }
    if (reason === 'SERVER_ERROR') {
      return { title: '后端服务异常', detail };
    }
    return { title: message.slice(0, 18), detail };
  },

  _startProgress() {
    this._progressTimer && clearInterval(this._progressTimer);
    this._progressTimer = setInterval(() => {
      const p = this.data.progress;
      if (p >= 92) return;
      this.setData({ progress: p + (p < 40 ? 6 : 3) });
    }, 220);
  },

  _stopProgress(finalProgress = 100) {
    if (this._progressTimer) {
      clearInterval(this._progressTimer);
      this._progressTimer = null;
    }
    this.setData({ progress: finalProgress });
  },

  _getSelectedAgeLabel() {
    const idx = Number(this.data.ageIndex || 0);
    const options = Array.isArray(this.data.ageOptions) ? this.data.ageOptions : [];
    const hit = options[idx] || options[1] || options[0] || { label: '4-5岁' };
    return String(hit.label || '4-5岁');
  },

  onAgeChange(e) {
    if (this.data.isGenerating) return;
    const idx = Number((e && e.detail && e.detail.value) || 0);
    this.setData({ ageIndex: Number.isNaN(idx) ? 1 : idx });
  },

  _uploadStoryByEndpoint(imagePath, endpoint, extraFormData = {}) {
    const base = getApiBase();
    const age = this._getSelectedAgeLabel();
    return new Promise((resolve, reject) => {
      wx.uploadFile({
        url: `${base}${endpoint}`,
        filePath: imagePath,
        name: 'file',
        formData: {
          age,
          tone: '温暖鼓励',
          lang: '中文',
          ...extraFormData,
        },
        timeout: 180000,
        success: (res) => {
          let data = {};
          try { data = JSON.parse(res.data || '{}'); } catch (e) {}
          if (res.statusCode === 404) {
            const err = this._makeReasonError(`接口不存在: ${endpoint}`, 'STORY_ENDPOINT_MISSING', endpoint);
            err.notFound = true;
            reject(err);
            return;
          }
          if (res.statusCode >= 500) {
            const detailMsg = String((data && (data.message || data.detail)) || '').trim();
            const msg = detailMsg || `服务异常(${res.statusCode})`;
            reject(this._makeReasonError(msg, 'SERVER_ERROR', detailMsg || endpoint));
            return;
          }
          resolve({ data, statusCode: res.statusCode, endpoint });
        },
        fail: (err) => reject(this._wrapNetworkError(err, `生成失败(${endpoint})`))
      });
    });
  },

  _normalizeStoryPayload(rawResult) {
    const result = rawResult || {};
    const data = result.data || {};
    const payload = (data && typeof data.data === 'object' && data.data) ? data.data : data;

    const code = Number(payload.code);
    const ok = payload.ok === true || code === 0 || code === 200;
    if (!ok) {
      throw new Error(payload.message || '生成失败');
    }

    const pagesRaw = payload.pages || payload.story_pages || (payload.story && payload.story.pages) || [];
    const pages = Array.isArray(pagesRaw) ? pagesRaw.filter(Boolean).map((t) => String(t)) : [];
    if (!pages.length) {
      throw new Error('故事内容为空，请重试');
    }

    return {
      title: String(payload.title || (payload.story && payload.story.title) || '宝宝的魔法冒险'),
      pages,
      caption: String(payload.caption || ''),
      ai_used: payload.ai_used !== undefined ? !!payload.ai_used : true,
    };
  },

  _normalizeCaption(caption) {
    return String(caption || '')
      .replace(/[\r\n]+/g, ' ')
      .replace(/[，。！？；：,.!?;:()（）【】\[\]<>《》“”"']/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  },

  _isWeakCaption(caption) {
    const text = this._normalizeCaption(caption);
    if (!text || text.length < 6) return true;
    const weakHints = [
      '这是一张图片',
      '很有趣的图片',
      '你可以说说里面发生了什么',
      '请你先说说看到了什么',
      '当前为兜底描述',
    ];
    return weakHints.some((k) => text.includes(k));
  },

  _getCaptionApiCandidates() {
    const base = getApiBase();
    const list = [
      `${base}/readalong/image_caption`,
    ];

    // 开发环境常见情况：9880 未代理 readalong，但 9881 服务可用。
    if (/:9880(?:$|\/)/.test(base)) {
      list.push(base.replace(':9880', ':9881') + '/readalong/image_caption');
    }

    const uniq = [];
    const seen = new Set();
    list.forEach((u) => {
      if (!seen.has(u)) {
        seen.add(u);
        uniq.push(u);
      }
    });
    return uniq;
  },

  _fetchImageCaption(imagePath) {
    const candidates = this._getCaptionApiCandidates();

    return new Promise((resolve, reject) => {
      const tryAt = (idx) => {
        if (idx >= candidates.length) {
          reject(this._makeReasonError('图片识别接口不存在', 'CAPTION_ENDPOINT_MISSING', candidates.join(' | ')));
          return;
        }

        const url = candidates[idx];
        wx.uploadFile({
          url,
          filePath: imagePath,
          name: 'file',
          timeout: 120000,
          success: (res) => {
            if (!res || res.statusCode === 404) {
              tryAt(idx + 1);
              return;
            }
            if (res.statusCode >= 300) {
              reject(this._makeReasonError('图片识别失败', 'CAPTION_FAIL', `status=${res.statusCode}`));
              return;
            }
            try {
              const data = JSON.parse(res.data || '{}');
              if (!data || !data.ok) {
                reject(this._makeReasonError(data && data.message ? data.message : '图片识别失败', 'CAPTION_FAIL'));
                return;
              }
              const caption = this._normalizeCaption(String(data.caption || ''));
              if (!caption) {
                reject(this._makeReasonError('图片描述为空', 'CAPTION_FAIL'));
                return;
              }
              if (this._isWeakCaption(caption)) {
                reject(this._makeReasonError('图片识别结果过于笼统，请重试', 'CAPTION_WEAK', caption));
                return;
              }
              resolve(caption);
            } catch (e) {
              reject(this._makeReasonError('图片识别结果解析失败', 'CAPTION_FAIL'));
            }
          },
          fail: (err) => {
            const wrapped = this._wrapNetworkError(err, '图片识别失败');
            if (wrapped && wrapped.reason === 'DOMAIN_WHITELIST') {
              reject(wrapped);
              return;
            }
            tryAt(idx + 1);
          },
        });
      };

      tryAt(0);
    });
  },

  _extractCaptionKeywords(caption) {
    const normalized = this._normalizeCaption(caption);
    if (!normalized) return [];

    const connectors = /和|与|跟|及|还有|以及|正在|看着|抱着|拿着|在|里|上|下|旁边|前面|后面|中间/g;
    const stopwords = new Set(['一个', '一只', '一些', '还有', '以及', '然后', '正在', '看着', '里面', '旁边', '上面', '下面', '这个', '那个', '图片', '画面', '照片', '正在']);

    const roughTokens = normalized
      .split(' ')
      .map((t) => t.trim())
      .filter((t) => t && t.length >= 2);

    const refined = [];
    roughTokens.forEach((token) => {
      const parts = token.split(connectors).map((x) => x.trim()).filter(Boolean);
      if (!parts.length) {
        refined.push(token);
        return;
      }
      parts.forEach((p) => {
        if (/^[\u4e00-\u9fa5]{2,}$/.test(p) && p.length > 8) {
          for (let i = 0; i < p.length; i += 2) {
            const seg = p.slice(i, i + 4).trim();
            if (seg.length >= 2) refined.push(seg);
          }
        } else {
          refined.push(p);
        }
      });
    });

    const tokens = refined
      .map((t) => t.trim())
      .filter((t) => t && t.length >= 2 && t.length <= 10 && !stopwords.has(t));

    const uniq = [];
    const seen = new Set();
    tokens.forEach((t) => {
      if (!seen.has(t)) {
        seen.add(t);
        uniq.push(t);
      }
    });
    return uniq.slice(0, 10);
  },

  _buildAlignmentPrompt(caption) {
    const age = this._getSelectedAgeLabel();
    const normalizedCaption = this._normalizeCaption(caption);
    const keywords = this._extractCaptionKeywords(normalizedCaption);
    return buildAiStoryPrompt({
      age,
      caption: normalizedCaption || '无',
      keywords,
    });
  },

  _calcCharOverlapRatio(caption, storyText) {
    const a = String(caption || '').replace(/\s+/g, '');
    const b = String(storyText || '').replace(/\s+/g, '');
    if (!a || !b) return 0;

    const aset = new Set(a.split(''));
    let hit = 0;
    b.split('').forEach((ch) => {
      if (aset.has(ch)) hit += 1;
    });
    return Math.min(1, hit / Math.max(1, b.length));
  },

  _calcHallucinationPenalty(captionKeywords, storyKeywords) {
    if (!Array.isArray(storyKeywords) || !storyKeywords.length) return 0;
    if (!Array.isArray(captionKeywords) || !captionKeywords.length) return 0;
    const extra = storyKeywords.filter((k) => !captionKeywords.some((c) => k.includes(c) || c.includes(k)));
    return Math.min(0.26, extra.length * 0.03);
  },

  _scoreStoryAlignment(pages, caption) {
    const list = Array.isArray(pages) ? pages.map((p) => String(p || '')) : [];
    if (!list.length) return 0;

    const normalizedCaption = this._normalizeCaption(caption);
    if (!normalizedCaption) return 0;

    const storyText = this._normalizeCaption(list.join(' '));
    const captionKeywords = this._extractCaptionKeywords(normalizedCaption);
    const storyKeywords = this._extractCaptionKeywords(storyText);

    if (!captionKeywords.length) {
      return this._calcCharOverlapRatio(normalizedCaption, storyText);
    }

    let hit = 0;
    captionKeywords.forEach((k) => {
      if (storyText.includes(k)) hit += 1;
    });

    const coverage = hit / captionKeywords.length;
    const overlap = this._calcCharOverlapRatio(normalizedCaption, storyText);
    const penalty = this._calcHallucinationPenalty(captionKeywords, storyKeywords);
    const score = (coverage * 0.7) + (overlap * 0.3) - penalty;
    return Math.max(0, Math.min(1, score));
  },

  _anchorStoryToCaption(story, caption) {
    const pages = Array.isArray(story && story.pages) ? story.pages.map((t) => String(t || '')) : [];
    if (!pages.length) return story;
    const keywords = this._extractCaptionKeywords(caption);
    if (!keywords.length) return story;

    const anchoredPages = pages.map((text, idx) => {
      const hasKeyword = keywords.some((k) => text.includes(k));
      if (hasKeyword) return text;
      const kw = keywords[idx % keywords.length];
      return `${text} 画面里还有${kw}。`;
    });

    const firstLead = this._normalizeCaption(caption).slice(0, 36);
    if (firstLead) {
      anchoredPages[0] = `画面中可以看到${firstLead}。${anchoredPages[0] || ''}`;
    }

    return {
      ...story,
      pages: anchoredPages,
    };
  },

  _buildStoryFromCaption(caption) {
    const age = this._getSelectedAgeLabel();
    const hero = age === '2-3岁' ? '小宝贝' : (age === '6-8岁' ? '小小探险家' : '小朋友');
    const safeCaption = String(caption || '一张温暖的照片').replace(/[。！!？?]+$/g, '').slice(0, 80);
    const pages = [
      `今天，${hero}看见了${safeCaption}。`,
      `${hero}轻轻地说：“原来这里藏着一个有趣的小故事！”`,
      `接着，${hero}认真观察，发现每个细节都在告诉我们要勇敢和善良。`,
      `最后，${hero}把这段经历讲给家人听，大家都露出了开心的笑容。`
    ];
    return {
      title: `${hero}的照片奇遇记`,
      pages,
      caption: safeCaption,
      ai_used: false,
    };
  },

  async _generateStoryFromImage(imagePath) {
    let lastErr = null;
    let allNotFound = true;
    let caption = '';
    let captionErr = null;

    try {
      caption = await this._fetchImageCaption(imagePath);
    } catch (e) {
      caption = '';
      captionErr = e || null;
    }

    const alignmentPrompt = this._buildAlignmentPrompt(caption);
    const alignKeywords = this._extractCaptionKeywords(caption).join(',');
    const extraFormData = {
      image_caption: caption,
      custom_prompt: alignmentPrompt,
      align_keywords: alignKeywords,
      require_image_faithfulness: '1',
      alignment_mode: 'strict',
    };

    for (let i = 0; i < AI_STORY_ENDPOINTS.length; i += 1) {
      const endpoint = AI_STORY_ENDPOINTS[i];
      try {
        const raw = await this._uploadStoryByEndpoint(imagePath, endpoint, extraFormData);
        const normalized = this._normalizeStoryPayload(raw);
        const serverCaption = this._normalizeCaption(normalized.caption || '');
        const effectiveCaption = caption || (this._isWeakCaption(serverCaption) ? '' : serverCaption);

        if (!effectiveCaption) {
          throw this._makeReasonError('图片理解失败，已阻止生成无关故事，请重试', 'CAPTION_WEAK');
        }

        const alignmentScore = this._scoreStoryAlignment(normalized.pages, effectiveCaption);
        if (alignmentScore < 0.22) {
          return this._buildStoryFromCaption(effectiveCaption);
        }
        if (alignmentScore < 0.45) {
          return this._anchorStoryToCaption(normalized, effectiveCaption);
        }
        return {
          ...normalized,
          caption: effectiveCaption,
        };
      } catch (err) {
        lastErr = err;
        if (!err || !err.notFound) allNotFound = false;
      }
    }

    if (allNotFound || (lastErr && String(lastErr.message || '').includes('接口不存在'))) {
      try {
        const fallbackCaption = caption || (await this._fetchImageCaption(imagePath));
        return this._buildStoryFromCaption(fallbackCaption);
      } catch (e) {
        if (captionErr && captionErr.reason === 'CAPTION_ENDPOINT_MISSING') {
          throw this._makeReasonError('识图与绘本接口均不可用，请先检查后端路由', 'CAPTION_ENDPOINT_MISSING');
        }
        throw this._makeReasonError('图片识别失败，已阻止生成无关故事。请稍后重试', 'STORY_ENDPOINT_MISSING');
      }
    }

    throw lastErr || new Error('生成失败');
  },

  async handleImageSelected(imagePath) {
    if (this.data.isGenerating) return;

    try {
      const info = await new Promise((resolve, reject) => {
        wx.getFileInfo({ filePath: imagePath, success: resolve, fail: reject });
      });
      const size = Number((info && info.size) || 0);
      if (size > 6 * 1024 * 1024) {
        wx.showToast({ title: '图片太大，请选择6MB以内照片', icon: 'none' });
        return;
      }
    } catch (e) {}

    this.setData({
      uploadedImage: imagePath,
      step: 'generating',
      isGenerating: true,
      progress: 3,
      storyId: '',
      storyTitle: '',
      storyPages: [],
      currentPage: 0,
      totalPages: 0,
      currentPageText: '',
      imageCaption: '',
      aiUsed: false,
    });
    wx.vibrateShort();
    this._startProgress();

    try {
      const data = await this._generateStoryFromImage(imagePath);
      const pages = Array.isArray(data.pages) ? data.pages.filter(Boolean).map((t) => ({ text: String(t) })) : [];
      if (!pages.length) throw new Error('故事内容为空，请重试');

      this._stopProgress(100);
      this.setData({
        step: 'preview',
        isGenerating: false,
        storyTitle: String(data.title || '宝宝的魔法冒险'),
        storyPages: pages,
        totalPages: pages.length,
        currentPage: 0,
        currentPageText: pages[0].text,
        imageCaption: String(data.caption || ''),
        aiUsed: !!data.ai_used,
      });
      wx.vibrateShort();
    } catch (err) {
      this._stopProgress(0);
      this.setData({ step: 'upload', isGenerating: false });
      const uiErr = this._classifyDisplayError(err);
      wx.showToast({ title: uiErr.title || '生成失败', icon: 'none', duration: 3000 });
      if (uiErr && uiErr.detail) {
        wx.showModal({
          title: '生成失败原因',
          content: uiErr.detail,
          showCancel: false,
        });
      }
    }
  },

  prevPage() {
    if (this.data.currentPage === 0) return;
    const newPage = this.data.currentPage - 1;
    this.setData({ currentPage: newPage, currentPageText: this.data.storyPages[newPage].text });
    wx.vibrateShort();
  },

  nextPage() {
    if (this.data.currentPage >= this.data.totalPages - 1) return;
    const newPage = this.data.currentPage + 1;
    this.setData({ currentPage: newPage, currentPageText: this.data.storyPages[newPage].text });
    wx.vibrateShort();
  },

  _upsertStory() {
    const nowId = String(this.data.storyId || '').trim();
    const story = {
      id: nowId || Date.now().toString(),
      title: this.data.storyTitle,
      coverImage: this.data.uploadedImage,
      pages: this.data.storyPages,
      caption: this.data.imageCaption,
      age: this._getSelectedAgeLabel(),
      aiUsed: !!this.data.aiUsed,
      currentPage: Number(this.data.currentPage || 0),
      createdDate: new Date().toLocaleDateString('zh-CN'),
      updatedAt: Date.now(),
    };

    const aiStories = wx.getStorageSync('aiStories') || [];
    const index = aiStories.findIndex((x) => String((x && x.id) || '') === story.id);
    if (index >= 0) aiStories[index] = { ...aiStories[index], ...story };
    else aiStories.unshift(story);
    wx.setStorageSync('aiStories', aiStories);
    this.setData({ storyId: story.id });
    return story;
  },

  saveStory() {
    try {
      this._upsertStory();
      wx.showToast({ title: '保存成功！', icon: 'success' });
      wx.vibrateShort();
    } catch (e) {
      wx.showToast({ title: '保存失败', icon: 'none' });
    }
  },

  readStoryNow() {
    try {
      const story = this._upsertStory();
      wx.navigateTo({ url: `/pages/ai-story-view/ai-story-view?id=${encodeURIComponent(story.id)}` });
    } catch (e) {
      wx.showToast({ title: '打开阅读失败', icon: 'none' });
    }
  },

  retryGenerate() {
    this._stopProgress(0);
    this.setData({
      step: 'upload',
      isGenerating: false,
      uploadedImage: '',
      progress: 0,
      storyId: '',
      currentPage: 0,
      storyTitle: '',
      storyPages: [],
      totalPages: 0,
      currentPageText: '',
      imageCaption: '',
      aiUsed: false,
    });
  },

  onUnload() {
    this._stopProgress(this.data.progress || 0);
  }
});
