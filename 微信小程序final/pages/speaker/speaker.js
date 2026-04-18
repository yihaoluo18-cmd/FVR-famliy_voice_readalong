const app = getApp();
const { toMiniprogramAssetUrl } = require("../../utils/asset-url.js");

Page({
  data: {
    apiBaseUrl: '',

    // 模式：题库配图 / 自选图片
    mode: 'bank', // bank | album

    // 练习进度（先保留原结构）
    currentQuestion: 1,
    totalQuestions: 100,
    progressPercent: 20,

    // 图片与参考文本
    currentImage: '',
    caption: '',
    captionHint: '点右上角换图，AI 会给出参考描述',
    captionLoading: false,

    // 题库与配图索引
    qbank: [], // [{id,title,intro,tips,tags}]
    imageIndex: {}, // {qid: "/assets/practice/speaker_images/q001.png"}
    generatedIds: [], // ["q001", ...]
    currentItem: null, // 当前题目对象（题库模式）

    // 录音与评测
    isRecording: false,
    hasRecorded: false,
    recordTime: 0,
    lastAudioPath: '',
    lastAudioFormat: 'wav',
    lastAudioSize: 0,
    evaluating: false,

    // 结果弹窗
    showScore: false,
    aiScore: 0,
    fullStars: 0,
    evalResult: null, // {stars, transcript, feedback}
    speakerRefreshIcon: "",
  },

  onLoad() {
    const base = (app && app.getApiBaseUrl) ? app.getApiBaseUrl() : 'http://127.0.0.1:9880'
    this.setData({
      apiBaseUrl: base,
      speakerRefreshIcon: toMiniprogramAssetUrl("/assets/icons/back.png"),
    })

    // 从本地存储恢复上次进度
    const savedProgress = wx.getStorageSync('speakerProgress');
    if (savedProgress) {
      const { currentQuestion, totalQuestions } = savedProgress;
      const progressPercent = (currentQuestion / totalQuestions) * 100;
      this.setData({ currentQuestion, totalQuestions, progressPercent });
    }

    this._initRecorder()

    // 默认进入“题库配图”模式：加载题库 + 已生成图片索引，然后选一题
    this._loadBank()
  },

  onShow() {
    // 题库模式下，定时查看时可能有新图生成，这里刷新一次索引即可
    if (this.data.mode === 'bank') {
      this._loadImageIndex()
    }
  },

  switchMode(e) {
    const mode = (e && e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.mode) || 'bank'
    if (mode === this.data.mode) return
    this.setData({
      mode,
      showScore: false,
      evaluating: false,
      isRecording: false,
      hasRecorded: false,
      recordTime: 0,
      lastAudioPath: '',
      lastAudioSize: 0,
      evalResult: null,
      aiScore: 0,
      fullStars: 0,
      caption: '',
      captionLoading: false,
      captionHint: mode === 'album' ? '点右上角换图，AI 会给出参考描述' : '',
    })
    if (mode === 'bank') {
      this._loadBank()
    } else {
      // 自选图：清空图，等待用户点刷新选择
      this.setData({ currentImage: '', currentItem: null })
    }
  },

  refreshImage() {
    if (this.data.isRecording || this.data.captionLoading || this.data.evaluating) return

    if (this.data.mode === 'bank') {
      this._pickRandomGeneratedQuestion()
      return
    }

    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      success: (res) => {
        const p = (res && res.tempFilePaths && res.tempFilePaths[0]) || ''
        if (!p) return

        this.setData({
          currentImage: p,
          caption: '',
          captionLoading: true,
          captionHint: '正在识别图片...',
          hasRecorded: false,
          recordTime: 0,
          lastAudioPath: '',
          lastAudioSize: 0,
          showScore: false,
          evalResult: null,
        })

        this._fetchCaptionOne(p)
      }
    })
  },

  // 切换录音
  toggleRecording() {
    this.data.isRecording ? this.stopRecording() : this.startRecording();
  },

  // 开始录音
  startRecording() {
    if (this.data.captionLoading) {
      wx.showToast({ title: '图片识别中，稍等哦', icon: 'none' })
      return
    }
    if (!this.data.currentImage) {
      wx.showToast({ title: '请先换一张图', icon: 'none' })
      return
    }
    if (!this.data.caption) {
      wx.showToast({ title: this.data.mode === 'bank' ? '题目还没准备好' : '等待参考描述生成完成', icon: 'none' })
      return
    }

    try {
      this.recorder.start({
        duration: 60000,
        sampleRate: 32000,
        numberOfChannels: 1,
        encodeBitRate: 128000,
        format: 'wav'
      })
    } catch (e) {
      console.log('start recorder failed', e)
      wx.showToast({ title: '录音启动失败', icon: 'none' })
      return
    }

    this.setData({ isRecording: true, recordTime: 0 })
    wx.vibrateShort()
    this._startTimer()
  },

  // 停止录音
  stopRecording() {
    try { this.recorder.stop() } catch (e) {}
  },

  finishSpeaking() {
    // 兼容原按钮文案：现在“完成演说”= 触发评测（录音停止会自动评测）
    if (!this.data.lastAudioPath) {
      wx.showToast({ title: '请先录音哦', icon: 'none' })
      return
    }
    if (this.data.evaluating) return
    this._evaluate()
  },

  // 继续下一题 → 进度+1，切换图片，隐藏评分弹窗
  nextQuestion() {
    const { currentQuestion, totalQuestions } = this.data;
    const newQuestion = Math.min(currentQuestion + 1, totalQuestions);
    const newProgress = (newQuestion / totalQuestions) * 100;

    this.setData({
      currentQuestion: newQuestion,
      progressPercent: newProgress,
      showScore: false,
      hasRecorded: false,
      recordTime: 0,
      lastAudioPath: '',
      lastAudioSize: 0,
      evalResult: null,
      aiScore: 0,
      fullStars: 0,
    });

    // 持久化进度到本地存储
    try {
      wx.setStorageSync('speakerProgress', {
        currentQuestion: newQuestion,
        totalQuestions: totalQuestions
      });
    } catch (e) {
      console.log('保存进度失败', e);
    }

    wx.vibrateShort();
  },

  _startTimer() {
    this._stopTimer()
    this._timer = setInterval(() => {
      this.setData({ recordTime: (this.data.recordTime || 0) + 1 })
    }, 1000)
  },

  _stopTimer() {
    if (this._timer) {
      clearInterval(this._timer)
      this._timer = null
    }
  },

  _initRecorder() {
    this.recorder = wx.getRecorderManager()

    this.recorder.onStop((res) => {
      const tempFilePath = res && res.tempFilePath
      const fileSize = Number((res && res.fileSize) || 0)
      this._stopTimer()

      const extMatch = tempFilePath ? String(tempFilePath).toLowerCase().match(/\.([a-z0-9]+)(?:\?|$)/) : null
      const fmt = (extMatch && extMatch[1]) || 'wav'

      this.setData({
        isRecording: false,
        hasRecorded: !!tempFilePath,
        lastAudioPath: tempFilePath || '',
        lastAudioFormat: fmt,
        lastAudioSize: fileSize,
      })

      if (tempFilePath) {
        setTimeout(() => this._evaluate(), 200)
      }
    })

    this.recorder.onError((err) => {
      console.log('recorder error', err)
      this._stopTimer()
      this.setData({ isRecording: false })
      wx.showToast({ title: '录音失败', icon: 'none' })
    })
  },

    _buildReadalongUploadUrls(pathname) {
      const base = String((this.data && this.data.apiBaseUrl) || ((app && app.getApiBaseUrl) ? app.getApiBaseUrl() : '') || '').trim().replace(/\/+$/, '')
      const path = String(pathname || '').trim()
      const urls = []
      if (base && path) {
        urls.push(base + path)
      }
      if (base.includes(':9880')) urls.push(base.replace(':9880', ':9881') + path)
      if (base.includes(':9980')) urls.push(base.replace(':9980', ':9981') + path)
      return Array.from(new Set(urls.filter(Boolean)))
    },
    _uploadFileWithFallback(urls, options = {}) {
      const list = Array.isArray(urls) ? urls.filter(Boolean) : []
      const filePath = options.filePath
      const name = options.name || 'file'
      const formData = options.formData || {}
      const timeout = Number(options.timeout || 120000)

      return new Promise((resolve, reject) => {
        const tryAt = (idx) => {
          if (idx >= list.length) {
            reject(new Error('all endpoints failed'))
            return
          }
          const url = list[idx]
          wx.uploadFile({
            url,
            filePath,
            name,
            formData,
            timeout,
            success: (res) => {
              if (!res || res.statusCode >= 300) {
                tryAt(idx + 1)
                return
              }
              let data = {}
              try {
                data = typeof res.data === 'string' ? JSON.parse(res.data || '{}') : (res.data || {})
              } catch (e) {
                tryAt(idx + 1)
                return
              }
              resolve({ data, res, url })
            },
            fail: () => tryAt(idx + 1),
          })
        }
        tryAt(0)
      })
    },
    _normalizePlaybackUrl(pathOrUrl) {
      const raw = String(pathOrUrl || '').trim()
      if (!raw) return ''
      if (/^https?:\/\//i.test(raw)) return raw
      const base = String((this.data && this.data.apiBaseUrl) || ((app && app.getApiBaseUrl) ? app.getApiBaseUrl() : '') || '').trim().replace(/\/+$/, '')
      if (!base) return raw
      return raw.startsWith('/') ? `${base}${raw}` : `${base}/${raw}`
    },

    _normalizeSpeakerImagePath(pathOrUrl) {
      const raw = String(pathOrUrl || '').trim();
      if (!raw) return '';
      if (/^https?:\/\//i.test(raw)) return raw;
      const withLeadingSlash = raw.startsWith('/') ? raw : `/${raw}`;
      if (withLeadingSlash.startsWith('/assets/')) return withLeadingSlash;
      if (withLeadingSlash.startsWith('/practice_static/')) {
        return `/assets/practice/${withLeadingSlash.slice('/practice_static/'.length)}`;
      }
      if (withLeadingSlash.startsWith('/practice/')) return `/assets${withLeadingSlash}`;
      return withLeadingSlash;
    },

    _playFeedbackAudio(pathOrUrl) {
      const url = this._normalizePlaybackUrl(pathOrUrl)
      if (!url) return
      try {
        if (!this._feedbackAudioCtx) this._feedbackAudioCtx = wx.createInnerAudioContext()
        this._feedbackAudioCtx.stop()
        this._feedbackAudioCtx.src = url
        this._feedbackAudioCtx.autoplay = true
        this._feedbackAudioCtx.play()
      } catch (e) {
        console.log('play feedback audio failed', e)
      }
    },

    _fetchCaptionOne(filePath) {
      const urls = this._buildReadalongUploadUrls('/readalong/image_caption')
      this._uploadFileWithFallback(urls, {
        filePath,
        name: 'file',
        formData: {},
        timeout: 120000,
      }).then(({ data }) => {
        if (!data || !data.ok) throw new Error('bad response')
        const caption = String(data.caption || '').trim()
        if (!caption) throw new Error('empty caption')
        this.setData({
          caption,
          captionHint: '参考描述已准备好，点击麦克风开始讲故事',
          captionLoading: false,
        })
      }).catch((e) => {
        console.log('upload image failed', e)
        const msg = String((e && e.message) || '')
        const isTimeout = msg.includes('timeout') || msg.includes('time out')
        this.setData({ captionLoading: false, captionHint: isTimeout ? '识别超时：可换更小的图' : '识别失败，请重试' })
        wx.showToast({ title: '图片识别失败', icon: 'none' })
      })
    },
    _evaluate() {
      if (this.data.evaluating || this.data.captionLoading) return

      const filePath = this.data.lastAudioPath
      const expectedText = this.data.caption
      if (!filePath) return
      if (!expectedText) {
        wx.showToast({ title: '等待参考描述准备完成', icon: 'none' })
        return
      }
      if (Number(this.data.lastAudioSize || 0) > 0 && Number(this.data.lastAudioSize || 0) < 2048) {
        wx.showToast({ title: '录音太短，请重试', icon: 'none' })
        return
      }
      try { if (this._feedbackAudioCtx) this._feedbackAudioCtx.stop() } catch (e) {}
      this.setData({ evaluating: true })
      const urls = this._buildReadalongUploadUrls('/readalong/evaluate')

      this._uploadFileWithFallback(urls, {
        filePath,
        name: 'file',
        formData: {
          expected_text: expectedText,
          book_id: (this.data.mode === 'bank' && this.data.currentItem && this.data.currentItem.id) ? this.data.currentItem.id : 'image_caption',
          sentence_index: '0',
          audio_format: this.data.lastAudioFormat || 'wav',
          eval_mode: 'free_description'
        },
        timeout: 180000,
      }).then(({ data }) => {
        if (!data || !data.ok) throw new Error('bad response')
        const starCount = Math.max(1, Math.min(5, Number(data.stars || 4)))
        const score = Math.round((starCount / 5) * 100)
          const feedbackText = String(data.feedback_text || data.feedback || '').trim()
          const recognizedText = String(data.recognized_text || data.transcript || '').trim()
          const asrErrorRaw = String(data.asr_error || '').trim()
          const asrError = asrErrorRaw.toLowerCase()
          const audioUrl = this._normalizePlaybackUrl(data.feedback_audio_url || '')

          if (recognizedText) {
            this._rewardStarsOnce()
          } else {
            const asrServiceDown = asrError.includes('invalid_api_key')
              || asrError.includes('asr_disabled')
              || asrError.includes('401')
              || asrError.includes('404')
              || asrError.includes('429')
              || asrError.includes('transcriptions:')
              || asrError.includes('chat_audio')
              || asrError.includes('dashscope_mm')
            wx.showToast({
              title: asrServiceDown ? '语音识别服务暂不可用，本次不计星' : '这次没听清，请放慢一点再说',
              icon: 'none'
            })
          }

          this.setData({
          evalResult: {
            stars: starCount,
            feedback: feedbackText,
            transcript: recognizedText
          },
          showScore: true,
          aiScore: score,
          fullStars: starCount,
        })
        this._playFeedbackAudio(audioUrl)
        wx.vibrateShort()
      }).catch((e) => {
        console.log('eval upload failed', e)
        wx.showToast({ title: '评测失败：请检查后端地址与端口', icon: 'none' })
      }).finally(() => {
        this.setData({ evaluating: false })
      })
    },

    async _loadBank() {
    await this._loadQuestions()
    await this._loadImageIndex()
    this._pickRandomGeneratedQuestion()
  },

  _loadQuestions() {
    return new Promise((resolve) => {
      const apiBaseUrl = this.data.apiBaseUrl
      wx.request({
        url: `${apiBaseUrl}/practice/speaker/questions?limit=200`,
        method: 'GET',
        timeout: 15000,
        success: (res) => {
          const items = (res && res.data && res.data.items) || []
          this.setData({ qbank: Array.isArray(items) ? items : [] })
          resolve(true)
        },
        fail: () => resolve(false),
      })
    })
  },

  _loadImageIndex() {
    return new Promise((resolve) => {
      const apiBaseUrl = this.data.apiBaseUrl
      const applyIndex = (data) => {
        const rawIdx = (data && typeof data === 'object') ? data : {}
        const idx = {}
        Object.keys(rawIdx || {}).forEach((k) => {
          idx[k] = this._normalizeSpeakerImagePath(rawIdx[k])
        })
        const ids = Object.keys(idx || {}).sort()
        const totalQuestions = ids.length || 1
        const currentQuestion = Math.min(this.data.currentQuestion || 1, totalQuestions)
        const progressPercent = (currentQuestion / totalQuestions) * 100
        this.setData({ imageIndex: idx, generatedIds: ids, totalQuestions, currentQuestion, progressPercent })
        resolve(true)
      }

      wx.request({
        url: `${apiBaseUrl}/assets/practice/speaker_images_index.json`,
        method: 'GET',
        timeout: 15000,
        success: (res) => {
          if (res && res.statusCode === 200 && res.data) {
            applyIndex(res.data)
            return
          }
          wx.request({
            url: `${apiBaseUrl}/practice_static/speaker_images_index.json`,
            method: 'GET',
            timeout: 15000,
            success: (legacyRes) => {
              if (legacyRes && legacyRes.statusCode === 200 && legacyRes.data) {
                applyIndex(legacyRes.data)
                return
              }
              resolve(false)
            },
            fail: () => resolve(false),
          })
        },
        fail: () => {
          wx.request({
            url: `${apiBaseUrl}/practice_static/speaker_images_index.json`,
            method: 'GET',
            timeout: 15000,
            success: (legacyRes) => {
              if (legacyRes && legacyRes.statusCode === 200 && legacyRes.data) {
                applyIndex(legacyRes.data)
                return
              }
              resolve(false)
            },
            fail: () => resolve(false),
          })
        },
      })
    })
  },

  _pickRandomGeneratedQuestion() {
    const keys = this.data.generatedIds || []
    if (!keys.length) {
      wx.showToast({ title: '配图还在生成中…', icon: 'none' })
      return
    }
    const qid = keys[Math.floor(Math.random() * keys.length)]
    this._selectQuestionById(qid)
  },

  selectQuestion(e) {
    const qid = (e && e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.qid) || ''
    if (!qid) return
    this._selectQuestionById(qid)
  },

  _selectQuestionById(qid) {
    const apiBaseUrl = this.data.apiBaseUrl
    const idx = this.data.imageIndex || {}
    const rel = idx[qid] || ''
    const url = rel ? `${apiBaseUrl}${rel}` : ''
    const item = (this.data.qbank || []).find(x => String(x.id) === String(qid)) || null
    const ids = this.data.generatedIds || []
    const pos = ids.indexOf(String(qid))
    const currentQuestion = (pos >= 0 ? (pos + 1) : (this.data.currentQuestion || 1))
    const totalQuestions = this.data.totalQuestions || (ids.length || 1)
    const progressPercent = (currentQuestion / totalQuestions) * 100

    this.setData({
      currentItem: item,
      currentImage: url,
      captionLoading: false,
      caption: item ? String(item.intro || item.title || '').trim() : '',
      captionHint: item ? '看图讲讲这个问题吧' : '题目加载中…',
      currentQuestion,
      progressPercent,
      hasRecorded: false,
      recordTime: 0,
      lastAudioPath: '',
      lastAudioSize: 0,
      showScore: false,
      evalResult: null,
      aiScore: 0,
      fullStars: 0,
    })
  },

  _rewardStarsOnce() {
    // 同一次录音只奖励一次，避免重复触发
    if (this._rewardedForPath === this.data.lastAudioPath) return
    this._rewardedForPath = this.data.lastAudioPath

    const { reportAmusementParkTaskDone } = require("../../utils/amusement-park-stars.js");
    reportAmusementParkTaskDone(app, "speaker");
  },

  onUnload() {
      this._stopTimer()
      try {
        if (this._feedbackAudioCtx) {
          this._feedbackAudioCtx.stop()
          this._feedbackAudioCtx.destroy()
          this._feedbackAudioCtx = null
        }
      } catch (e) {}
    }
});
