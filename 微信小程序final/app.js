// app.js - 小程序全局逻辑
const { GUIDE_STORAGE_KEY, isMainDone, markMainDone } = require('./utils/guide-flow.js')
const DEFAULT_API_BASE_URL = 'http://127.0.0.1:9880'
const STORAGE_KEY_API_URL = 'apiBaseUrl'
const LEGACY_STORAGE_KEY_API_URL = 'readalong.apiBaseUrl'
const STORAGE_KEY_VOICE_ROLE_MAP = 'voiceRoleMap'
const STORAGE_KEY_VOICE_LIST_CACHE = 'voiceListCache'
const STORAGE_KEY_LAST_AUTH_USER = 'lastAuthenticatedUserId'
const STORAGE_KEY_LAST_GOOD_API_URL = 'lastGoodApiBaseUrl'
const STORAGE_KEY_CUSTOM_FONT_URL = 'customFontUrl'
const STORAGE_KEY_API_DOWN_UNTIL = 'apiDownUntilMap'
const STORAGE_KEY_CUSTOM_FONT_LOCAL_PATH = 'customFontLocalPath'
const GLOBAL_FONT_FAMILY = 'zihunmengquruantangti'
const FIXED_FONT_FILE_NAME = 'cute-candy.ttf'
const CURRENT_LOCAL_FONT_FILE_NAME = 'cheese-candy.ttf'
const FONT_FILE_NAME = '字魂萌趣软糖体(商用需授权).ttf'
const FONT_FOLDER_NAME = '字魂萌趣软糖体(商用需授权)'
const BASE_VOICE_FEMALE_ID = 'voice_001'
const BASE_VOICE_MALE_ID = 'voice_002'
const FRONTEND_HIDDEN_VOICE_IDS = new Set(['voice_003'])

function normalizeBaseUrl(url) {
  if (!url) return ''
  return String(url).trim().replace(/\/+$/, '')
}

function safeGetStorage(key, fallback) {
  try {
    const v = wx.getStorageSync(key)
    return v === undefined || v === null ? fallback : v
  } catch (e) {
    return fallback
  }
}

/** 解析 FastAPI / 业务接口返回的 detail（字符串或校验错误数组） */
function wxApiDetailMsg(body) {
  const b = body || {}
  const d = b.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d
      .map((x) => (x && (x.msg || x.message)) || '')
      .filter(Boolean)
      .join(',')
  }
  return b.message ? String(b.message) : ''
}

/** 与 globalData.userData 初始结构一致，用于退出登录 / 会话失效后清 UI */
function freshDefaultUserData() {
  return {
    avatar: '',
    parentName: '宝宝家长',
    babyName: '小粉宝',
    babyAge: '3',
    email: '',
    phone: ''
  }
}

const AUTO_PARENT_NICKNAMES = [
  '星光家长',
  '月亮家长',
  '暖暖家长',
  '晴空家长',
  '甜橙家长',
  '微风家长',
  '银河家长',
  '向日葵家长',
]

function shouldAutoAssignParentName(name) {
  const n = String(name || '').trim()
  return !n || n === '宝宝家长' || n === '你好家长' || n === '家长'
}

function randomParentNickname() {
  const i = Math.floor(Math.random() * AUTO_PARENT_NICKNAMES.length)
  return AUTO_PARENT_NICKNAMES[i] || '暖暖家长'
}

App({
  globalData: {
    apiBaseUrl: DEFAULT_API_BASE_URL,
    user_id: '',
    openid: '',
    unionid: '',
    authToken: '',
    userData: {
      avatar: '',
      parentName: '宝宝家长',
      babyName: '小粉宝',
      babyAge: '3',
      email: '',
      phone: ''
    },
    stars: 0,
    level: 1,
    booksRead: 0,
    coloringWorks: 0,
    clonedVoices: 0,
    speakerTasks: 0,
    checkInRecord: {},
    rewardsClaimed: {},
    lastCheckInDate: '',
    favorites: [],
    aiStories: [],
    isLoggedIn: false,

    // 声音相关
    voiceId: '',
    globalVoiceName: '基础音色（默认）',
    defaultVoiceId: '',
    defaultVoiceName: '基础音色（默认）',
    voiceList: [],
    voiceRoleMap: {}
  },
  
  onLaunch() {
    this._voiceChangeSubscribers = []
    this._apiDownUntilMap = safeGetStorage(STORAGE_KEY_API_DOWN_UNTIL, {}) || {}
    this._migrateLegacyApiBaseUrl()
    // 恢复系统字体：不再自动加载自定义字体
    this.loadUserData()
    // 真机环境下如果 apiBaseUrl 仍是 127.0.0.1/localhost，会导致连接重置/Failed to fetch
    // 这里直接跳过，直到你在小程序里配置正确的局域网地址后再进入语音页触发刷新。
    const base = this.getApiBaseUrl()
    if (!this._shouldBlockLoopbackRequest(base)) this.refreshVoiceList()
  },

  _isLoopbackBaseUrl(baseUrl) {
      const s = String(baseUrl || "").toLowerCase()
      return s.indexOf("127.0.0.1") !== -1 || s.indexOf("localhost") !== -1
    },

    _isDevtoolsRuntime() {
      try {
        const baseInfo = (typeof wx.getAppBaseInfo === 'function') ? (wx.getAppBaseInfo() || {}) : {}
        const deviceInfo = (typeof wx.getDeviceInfo === 'function') ? (wx.getDeviceInfo() || {}) : {}
        const platform = String(baseInfo.platform || deviceInfo.platform || '').toLowerCase()
        const host = String(baseInfo.host || '').toLowerCase()
        return platform === "devtools" || host === 'devtools'
      } catch (e) {
        return false
      }
    },

    _shouldBlockLoopbackRequest(baseUrl) {
      return this._isLoopbackBaseUrl(baseUrl) && !this._isDevtoolsRuntime()
    },

  _buildFontCandidateUrls(baseUrl) {
    const base = normalizeBaseUrl(baseUrl || this.getApiBaseUrl() || '')
    const fixedName = encodeURIComponent(FIXED_FONT_FILE_NAME)
    // 优先走确定可控的固定英文文件名路径，避免无效候选拖慢
    return [
      `${base}/static/fonts/${fixedName}`,
      `${base}/static/${fixedName}`,
      `${base}/${fixedName}`,
    ]
  },

  _buildLegacyFontCandidateUrls(baseUrl) {
    const base = normalizeBaseUrl(baseUrl || this.getApiBaseUrl() || '')
    const encodedName = encodeURIComponent(FONT_FILE_NAME)
    const encodedFolder = encodeURIComponent(FONT_FOLDER_NAME)
    const fileNames = [
      `${FONT_FOLDER_NAME}.ttf`,
      `${FONT_FOLDER_NAME}.otf`,
      'font.ttf',
      'font.otf',
      'index.ttf',
      'index.otf',
      'regular.ttf',
      'regular.otf',
      'font.woff',
      'font.woff2',
    ].map((n) => encodeURIComponent(n))
    const cands = [
      `${base}/${encodedName}`,
      `${base}/static/${encodedName}`,
      `${base}/static/fonts/${encodedName}`,
      `${base}/fonts/${encodedName}`,
      `${base}/assets/fonts/${encodedName}`,
      `${base}/${encodedFolder}`,
      `${base}/static/${encodedFolder}`,
      `${base}/static/fonts/${encodedFolder}`,
      `${base}/fonts/${encodedFolder}`,
      `${base}/assets/fonts/${encodedFolder}`,
    ]
    const withFolderFiles = []
    const folderBases = [
      `${base}/${encodedFolder}`,
      `${base}/static/${encodedFolder}`,
      `${base}/static/fonts/${encodedFolder}`,
      `${base}/fonts/${encodedFolder}`,
      `${base}/assets/fonts/${encodedFolder}`,
    ]
    folderBases.forEach((fb) => {
      fileNames.forEach((fn) => {
        withFolderFiles.push(`${fb}/${fn}`)
      })
    })
    const allCands = [...cands, ...withFolderFiles]
    const seen = {}
    const deduped = allCands.filter((u) => {
      if (!u || seen[u]) return false
      seen[u] = 1
      return true
    })
    // 仅作为兜底，最多尝试前 6 个
    return deduped.slice(0, 6)
  },

  _normalizeBase(baseUrl) {
    return normalizeBaseUrl(baseUrl || this.getApiBaseUrl() || '')
  },

  _saveApiDownMap() {
    try { wx.setStorageSync(STORAGE_KEY_API_DOWN_UNTIL, this._apiDownUntilMap || {}) } catch (e) {}
  },

  markApiTemporarilyDown(baseUrl, cooldownMs) {
    const base = this._normalizeBase(baseUrl)
    if (!base) return
    const ms = Math.max(3000, Number(cooldownMs || 15000) || 15000)
    if (!this._apiDownUntilMap || typeof this._apiDownUntilMap !== 'object') this._apiDownUntilMap = {}
    this._apiDownUntilMap[base] = Date.now() + ms
    this._saveApiDownMap()
  },

  clearApiDownMark(baseUrl) {
    const base = this._normalizeBase(baseUrl)
    if (!base || !this._apiDownUntilMap || typeof this._apiDownUntilMap !== 'object') return
    if (this._apiDownUntilMap[base]) {
      delete this._apiDownUntilMap[base]
      this._saveApiDownMap()
    }
  },

  isApiTemporarilyDown(baseUrl) {
    const base = this._normalizeBase(baseUrl)
    if (!base) return false
    if (!this._apiDownUntilMap || typeof this._apiDownUntilMap !== 'object') {
      this._apiDownUntilMap = safeGetStorage(STORAGE_KEY_API_DOWN_UNTIL, {}) || {}
    }
    const until = Number((this._apiDownUntilMap && this._apiDownUntilMap[base]) || 0) || 0
    if (!until) return false
    if (Date.now() > until) {
      delete this._apiDownUntilMap[base]
      this._saveApiDownMap()
      return false
    }
    return true
  },

  _loadGlobalFontWithUrl(url) {
    return new Promise((resolve, reject) => {
      const source = `url('${String(url || '').trim()}')`
      wx.loadFontFace({
        family: GLOBAL_FONT_FAMILY,
        source,
        global: true,
        success: () => resolve(url),
        fail: (err) => reject(err || new Error('font load failed'))
      })
    })
  },

  _downloadFontToLocal(url) {
    return new Promise((resolve, reject) => {
      const target = `${wx.env.USER_DATA_PATH}/${CURRENT_LOCAL_FONT_FILE_NAME}`
      wx.downloadFile({
        url: String(url || '').trim(),
        filePath: target,
        timeout: 60000,
        success: (res) => {
          if (Number(res && res.statusCode) === 200) resolve(target)
          else reject(new Error(`download font failed: ${Number(res && res.statusCode) || 0}`))
        },
        fail: (err) => reject(err || new Error('download font failed')),
      })
    })
  },

  _loadGlobalFontWithLocalPath(localPath) {
    return new Promise((resolve, reject) => {
      const source = `url('${String(localPath || '').trim()}')`
      wx.loadFontFace({
        family: GLOBAL_FONT_FAMILY,
        source,
        global: true,
        success: () => resolve(localPath),
        fail: (err) => reject(err || new Error('font local load failed'))
      })
    })
  },

  async _initGlobalFont() {
    // 已停用（恢复系统字体）
    return
    const manualUrl = String(safeGetStorage(STORAGE_KEY_CUSTOM_FONT_URL, '') || '').trim()
    const localPath = String(safeGetStorage(STORAGE_KEY_CUSTOM_FONT_LOCAL_PATH, '') || '').trim()
    if (localPath && String(localPath).indexOf(CURRENT_LOCAL_FONT_FILE_NAME) !== -1) {
      try {
        await this._loadGlobalFontWithLocalPath(localPath)
        this.globalData.globalFontFamily = GLOBAL_FONT_FAMILY
        console.info('[font] loaded from local cache:', localPath)
        return
      } catch (e) {}
    }
    const autoCandidates = this._buildFontCandidateUrls(this.getApiBaseUrl())
    const legacyCandidates = this._buildLegacyFontCandidateUrls(this.getApiBaseUrl())
    // 固定路径优先，历史缓存(常见为旧中文路径)放最后兜底，避免一直命中无效地址
    const candidates = manualUrl ? [...autoCandidates, ...legacyCandidates, manualUrl] : [...autoCandidates, ...legacyCandidates]
    if (!candidates.length) return
    for (let i = 0; i < candidates.length; i += 1) {
      const url = candidates[i]
      try {
        // 先下载到本地再加载，避免开发者工具渲染层对远程字体的 ERR_CACHE_MISS
        const p = await this._downloadFontToLocal(url)
        await this._loadGlobalFontWithLocalPath(p)
        this.globalData.globalFontFamily = GLOBAL_FONT_FAMILY
        try { wx.setStorageSync(STORAGE_KEY_CUSTOM_FONT_URL, url) } catch (e) {}
        try { wx.setStorageSync(STORAGE_KEY_CUSTOM_FONT_LOCAL_PATH, p) } catch (e) {}
        console.warn('[font] downloaded and loaded:', url, '=>', p)
        return
      } catch (e) {
        // 本地下载失败再兜底尝试远程直连
        console.error('[font] download/local load failed:', url, e)
        try {
          await this._loadGlobalFontWithUrl(url)
          this.globalData.globalFontFamily = GLOBAL_FONT_FAMILY
          try { wx.setStorageSync(STORAGE_KEY_CUSTOM_FONT_URL, url) } catch (e2) {}
          try { wx.removeStorageSync(STORAGE_KEY_CUSTOM_FONT_LOCAL_PATH) } catch (e2) {}
          console.warn('[font] loaded from remote url:', url)
          return
        } catch (e2) {
          console.error('[font] remote load failed:', url, e2)
        }
      }
    }
    // 若全部失败，保持系统字体兜底；不阻塞启动流程
    console.error('[font] all candidates failed, fallback to system fonts')
  },

  _readStoredApiBaseUrl() {
    const primary = normalizeBaseUrl(safeGetStorage(STORAGE_KEY_API_URL, ''))
    if (primary) return primary
    const legacy = normalizeBaseUrl(safeGetStorage(LEGACY_STORAGE_KEY_API_URL, ''))
    if (legacy) return legacy
    return ''
  },

  _migrateLegacyApiBaseUrl() {
    const stored = this._readStoredApiBaseUrl()
    let finalBase = stored || normalizeBaseUrl(this.globalData.apiBaseUrl) || DEFAULT_API_BASE_URL
    const lastGood = normalizeBaseUrl(safeGetStorage(STORAGE_KEY_LAST_GOOD_API_URL, ''))
    if (this._shouldBlockLoopbackRequest(finalBase) && lastGood && !this._isLoopbackBaseUrl(lastGood)) {
      finalBase = lastGood
    }
    this.globalData.apiBaseUrl = finalBase
    try {
      wx.setStorageSync(STORAGE_KEY_API_URL, finalBase)
    } catch (e) {}
  },

  setApiBaseUrl(url) {
    const finalBase = normalizeBaseUrl(url) || DEFAULT_API_BASE_URL
    this.globalData.apiBaseUrl = finalBase
    try {
      wx.setStorageSync(STORAGE_KEY_API_URL, finalBase)
      wx.setStorageSync(LEGACY_STORAGE_KEY_API_URL, finalBase)
    } catch (e) {}
    return finalBase
  },

  getApiBaseUrl() {
    const inMemory = normalizeBaseUrl(this.globalData.apiBaseUrl || '')
    if (inMemory) return inMemory
    return this._readStoredApiBaseUrl() || DEFAULT_API_BASE_URL
  },

  getVoiceId() {
    const v = String(safeGetStorage('voiceId', this.globalData.voiceId || '') || '').trim()
    return v
  },

  setVoiceId(voiceId) {
    const v = String(voiceId || '').trim()
    this.globalData.voiceId = v
    try {
      wx.setStorageSync('voiceId', v)
    } catch (e) {}
  },

  subscribeVoiceChange(callback) {
    if (typeof callback !== 'function') return
    if (!Array.isArray(this._voiceChangeSubscribers)) this._voiceChangeSubscribers = []
    this._voiceChangeSubscribers.push(callback)
  },

  unsubscribeVoiceChange(callback) {
    if (!Array.isArray(this._voiceChangeSubscribers) || !callback) return
    this._voiceChangeSubscribers = this._voiceChangeSubscribers.filter((fn) => fn !== callback)
  },

  _notifyVoiceChange() {
    const payload = {
      voiceId: this.globalData.voiceId || '',
      voiceName: this.globalData.globalVoiceName || this.globalData.defaultVoiceName || '基础音色（默认）',
      defaultVoiceId: this.globalData.defaultVoiceId || '',
      defaultVoiceName: this.globalData.defaultVoiceName || '基础音色（默认）',
      voices: Array.isArray(this.globalData.voiceList) ? this.globalData.voiceList : []
    }
    ;(this._voiceChangeSubscribers || []).forEach((fn) => {
      try { fn(payload) } catch (e) {}
    })
  },

  _voiceSortPriority(item) {
    const id = String((item && item.voice_id) || '').trim()
    if (id === BASE_VOICE_FEMALE_ID) return 0
    if (id === BASE_VOICE_MALE_ID) return 1
    const isBuiltin = !!(item && item.is_builtin)
    if (isBuiltin) return 2
    return 10
  },

  _sortVoiceListForDisplay(voices) {
    const list = Array.isArray(voices)
      ? voices.filter((v) => !FRONTEND_HIDDEN_VOICE_IDS.has(String((v && v.voice_id) || '').trim()))
      : []
    list.sort((a, b) => {
      const pa = this._voiceSortPriority(a)
      const pb = this._voiceSortPriority(b)
      if (pa !== pb) return pa - pb
      const ta = String((a && a.trained_at) || '')
      const tb = String((b && b.trained_at) || '')
      if (ta !== tb) return tb.localeCompare(ta)
      const na = String((a && a.name) || (a && a.voice_id) || '')
      const nb = String((b && b.name) || (b && b.voice_id) || '')
      return na.localeCompare(nb)
    })
    return list
  },

  _resolveDefaultVoiceFromList(voices) {
    const list = this._sortVoiceListForDisplay(voices)
    if (!list.length) return null
    return list.find((v) => String(v.voice_id || '') === BASE_VOICE_FEMALE_ID)
      || list.find((v) => String(v.voice_id || '') === BASE_VOICE_MALE_ID)
      || list.find((v) => String(v.name || '').includes('默认'))
      || list[0]
  },



  getVoiceRoleMap() {
    const inMemory = this.globalData && this.globalData.voiceRoleMap
    if (inMemory && typeof inMemory === 'object' && !Array.isArray(inMemory)) return inMemory
    const stored = safeGetStorage(STORAGE_KEY_VOICE_ROLE_MAP, {}) || {}
    const m = (stored && typeof stored === 'object' && !Array.isArray(stored)) ? stored : {}
    this.globalData.voiceRoleMap = m
    return m
  },

  setVoiceRoleVoice(roleKey, voiceId, voiceName) {
    const role = String(roleKey || '').trim()
    if (!role) return
    const map = { ...this.getVoiceRoleMap() }
    map[role] = {
      voiceId: String(voiceId || '').trim(),
      voiceName: String(voiceName || '').trim(),
      updatedAt: Date.now()
    }
    this.globalData.voiceRoleMap = map
    try { wx.setStorageSync(STORAGE_KEY_VOICE_ROLE_MAP, map) } catch (e) {}
  },

  getVoiceByRole(roleKey) {
    const role = String(roleKey || '').trim()
    if (!role) return null
    const map = this.getVoiceRoleMap()
    const item = map[role]
    if (!item || typeof item !== 'object') return null
    return {
      voiceId: String(item.voiceId || '').trim(),
      voiceName: String(item.voiceName || '').trim(),
      updatedAt: Number(item.updatedAt || 0)
    }
  },

  _pruneRoleVoiceMap(voices) {
    const list = Array.isArray(voices) ? voices : []
    const validIds = new Set(list.map((v) => String(v.voice_id || '')))
    const map = this.getVoiceRoleMap()
    const next = {}
    Object.keys(map).forEach((k) => {
      const item = map[k] || {}
      const vid = String(item.voiceId || '').trim()
      if (!vid || validIds.has(vid)) next[k] = item
    })
    this.globalData.voiceRoleMap = next
    try { wx.setStorageSync(STORAGE_KEY_VOICE_ROLE_MAP, next) } catch (e) {}
  },

  /**
   * 正式登录账号切换时：清空本地进度与缓存，避免沿用「未登录测试态」的全局数据。
   * 未登录（游客）不调用；同一 user_id 重复登录不清空。
   */
  resetProgressForNewLoginUser(nextUserId) {
    const next = String(nextUserId || '').trim()
    if (!next) return
    const prev = String(safeGetStorage(STORAGE_KEY_LAST_AUTH_USER, '') || '').trim()
    if (prev === next) return

    // 新账号与本机旧引导状态无关，避免沿用上号的 homeDone 导致首页指引不再出现
    try {
      wx.removeStorageSync(GUIDE_STORAGE_KEY)
    } catch (e) {}

    const keysToRemove = [
      'userStars',
      'booksRead',
      'coloringWorks',
      'clonedVoices',
      'speakerTasks',
      'checkInRecord',
      'rewardsClaimed',
      'lastCheckInDate',
      'favorites',
      'aiStories',
      STORAGE_KEY_VOICE_LIST_CACHE,
      STORAGE_KEY_VOICE_ROLE_MAP,
      'voiceId',
      'globalVoiceName',
      'ar_companion_user_id',
      'selectedMascot',
      'selectedMascotFormKey',
      'selectedMascotUpdatedAt',
      'home_tuning_last_saved',
      'readingRecent',
      'dailyReadingGoalMinutes',
      'todayStarsGoal',
    ]
    keysToRemove.forEach((k) => {
      try { wx.removeStorageSync(k) } catch (e) {}
    })
    try {
      const info = wx.getStorageInfoSync()
      ;(info.keys || []).forEach((k) => {
        if (
          k.startsWith('amusementParkTasks.') ||
          k.startsWith('todayStars.') ||
          k.startsWith('readingMinutes.')
        ) {
          try { wx.removeStorageSync(k) } catch (e) {}
        }
      })
    } catch (e) {}

    this.globalData.stars = 0
    this.globalData.booksRead = 0
    this.globalData.coloringWorks = 0
    this.globalData.clonedVoices = 0
    this.globalData.speakerTasks = 0
    this.globalData.checkInRecord = {}
    this.globalData.rewardsClaimed = {}
    this.globalData.lastCheckInDate = ''
    this.globalData.favorites = []
    this.globalData.aiStories = []
    this.globalData.voiceList = []
    this.globalData.voiceRoleMap = {}
    this.globalData.voiceId = ''
    this.globalData.globalVoiceName = '基础音色（默认）'
    this.updateLevel()
    try {
      wx.setStorageSync('userStars', 0)
      wx.setStorageSync('booksRead', 0)
      wx.setStorageSync('coloringWorks', 0)
      wx.setStorageSync('clonedVoices', 0)
      wx.setStorageSync('speakerTasks', 0)
      wx.setStorageSync('voiceId', '')
      wx.setStorageSync('globalVoiceName', '基础音色（默认）')
    } catch (e) {}
    try { wx.setStorageSync(STORAGE_KEY_LAST_AUTH_USER, next) } catch (e) {}
  },

  refreshVoiceList(callback) {
    const base = this.getApiBaseUrl()
    if (this.isApiTemporarilyDown(base)) {
      const cached = safeGetStorage(STORAGE_KEY_VOICE_LIST_CACHE, []) || []
      if (Array.isArray(cached) && cached.length) {
        const sortedCached = this._sortVoiceListForDisplay(cached)
        this.globalData.voiceList = sortedCached
        this._notifyVoiceChange()
        if (typeof callback === 'function') callback(null, sortedCached)
        return
      }
      if (typeof callback === 'function') callback(new Error('API 暂不可用，稍后重试'))
      return
    }
    if (this._shouldBlockLoopbackRequest(base)) {
      const cached = safeGetStorage(STORAGE_KEY_VOICE_LIST_CACHE, []) || []
      if (Array.isArray(cached) && cached.length) {
        const sortedCached = this._sortVoiceListForDisplay(cached)
        this.globalData.voiceList = sortedCached
        const defaultVoice = this._resolveDefaultVoiceFromList(sortedCached)
        this.globalData.defaultVoiceId = defaultVoice ? String(defaultVoice.voice_id || '') : ''
        this.globalData.defaultVoiceName = defaultVoice
          ? String(defaultVoice.name || defaultVoice.voice_id || '基础音色（默认）')
          : '基础音色（默认）'
        this._notifyVoiceChange()
        if (typeof callback === 'function') callback(null, sortedCached)
        return
      }
      // 无缓存时继续尝试请求（兼容开发者工具直连本机 127.0.0.1）
    }
    const headers = {}
    const tok = this.getAuthToken()
    if (tok) headers.Authorization = `Bearer ${tok}`

    wx.request({
      url: `${base}/voices`,
      method: 'GET',
      header: headers,
      timeout: 10000,
      success: (res) => {
        const voicesRaw = (res && res.data && Array.isArray(res.data.voices)) ? res.data.voices : []
        const voices = this._sortVoiceListForDisplay(voicesRaw)
        this.globalData.voiceList = voices
          this.clearApiDownMark(base)
          try { wx.setStorageSync(STORAGE_KEY_LAST_GOOD_API_URL, base) } catch (e) {}
            try { wx.setStorageSync(STORAGE_KEY_VOICE_LIST_CACHE, voices) } catch (e) {}
          this._pruneRoleVoiceMap(voices)

        const defaultVoice = this._resolveDefaultVoiceFromList(voices)
        this.globalData.defaultVoiceId = defaultVoice ? String(defaultVoice.voice_id || '') : ''
        this.globalData.defaultVoiceName = defaultVoice
          ? String(defaultVoice.name || defaultVoice.voice_id || '基础音色（默认）')
          : '基础音色（默认）'

        const curId = this.getVoiceId()
        const hit = curId ? voices.find((v) => String(v.voice_id || '') === curId) : null
        if (hit) {
          this.globalData.voiceId = String(hit.voice_id || '')
          this.globalData.globalVoiceName = String(hit.name || hit.voice_id || this.globalData.defaultVoiceName)
        } else {
          this.globalData.voiceId = ''
          this.globalData.globalVoiceName = this.globalData.defaultVoiceName
          try { wx.setStorageSync('voiceId', '') } catch (e) {}
        }

        try {
          wx.setStorageSync('globalVoiceName', this.globalData.globalVoiceName || '基础音色（默认）')
        } catch (e) {}

        this._notifyVoiceChange()
        if (typeof callback === 'function') callback(null, voices)
      },
      fail: (err) => {
          this.markApiTemporarilyDown(base, 20000)
          const cached = safeGetStorage(STORAGE_KEY_VOICE_LIST_CACHE, []) || []
          if (Array.isArray(cached) && cached.length && (!Array.isArray(this.globalData.voiceList) || !this.globalData.voiceList.length)) {
            this.globalData.voiceList = this._sortVoiceListForDisplay(cached)
            this._notifyVoiceChange()
          }
          if (typeof callback === 'function') callback(err || new Error('声音列表获取失败'))
        }
    })
  },

  setGlobalVoice(voiceId, voiceName, callback) {
    const done = typeof callback === 'function' ? callback : () => {}
    const id = String(voiceId || '').trim()
    const name = String(voiceName || '').trim() || '基础音色（默认）'

    if (!id) {
      this.globalData.voiceId = ''
      this.globalData.globalVoiceName = this.globalData.defaultVoiceName || '基础音色（默认）'
      try {
        wx.setStorageSync('voiceId', '')
        wx.setStorageSync('globalVoiceName', this.globalData.globalVoiceName)
      } catch (e) {}
      this._notifyVoiceChange()
      done(null)
      return
    }

    const base = this.getApiBaseUrl()
    wx.request({
      url: `${base}/use_voice`,
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      timeout: 15000,
      data: { voice_id: id },
      success: (res) => {
        const d = (res && res.data) || {}
        if (res.statusCode !== 200 || Number(d.code) !== 0) {
          done(new Error((d && d.message) || '切换失败'))
          return
        }
        this.globalData.voiceId = id
        this.globalData.globalVoiceName = name
        try {
          wx.setStorageSync('voiceId', id)
          wx.setStorageSync('globalVoiceName', name)
        } catch (e) {}
        this._notifyVoiceChange()
        done(null, d)
      },
      fail: (err) => done(err || new Error('切换失败'))
    })
  },

  setDefaultVoice(callback) {
    const done = typeof callback === 'function' ? callback : () => {}
    const list = Array.isArray(this.globalData.voiceList) ? this.globalData.voiceList : []
    const def = this._resolveDefaultVoiceFromList(list)
    if (!def || !def.voice_id) {
      done(new Error('未找到基础音色，请先检查声音列表'))
      return
    }
    this.setGlobalVoice(String(def.voice_id || ''), String(def.name || '基础音色（默认）'), done)
  },

  calculateLevel(stars) {
    const n = Number(stars || 0)
    if (n >= 200) return { level: 5, title: '传奇讲述者', icon: '👑', starsToNextLevel: 0 }
    if (n >= 100) return { level: 4, title: '故事大师', icon: '🏆', starsToNextLevel: 200 - n }
    if (n >= 50) return { level: 3, title: '阅读小达人', icon: '⭐', starsToNextLevel: 100 - n }
    if (n >= 20) return { level: 2, title: '故事探险家', icon: '🎒', starsToNextLevel: 50 - n }
    return { level: 1, title: '初级读者', icon: '📖', starsToNextLevel: 20 - n }
  },

  initGlobalData() {
    this.globalData.stars = Number(safeGetStorage('userStars', 0) || 0)
    this.globalData.booksRead = Number(safeGetStorage('booksRead', 0) || 0)
    this.globalData.coloringWorks = Number(safeGetStorage('coloringWorks', 0) || 0)
    this.globalData.clonedVoices = Number(safeGetStorage('clonedVoices', 0) || 0)
    this.globalData.speakerTasks = Number(safeGetStorage('speakerTasks', 0) || 0)
    this.loadUserData()
  },

  loadUserData() {
    const token = String(safeGetStorage('authToken', '') || '').trim()
    const flagged = !!safeGetStorage('isLoggedIn', false)
    // 必须同时有「标记 + token」才算有效登录，避免退出后仍残留 userData / user_id
    const sessionOk = flagged && !!token
    this.globalData.isLoggedIn = sessionOk
    this.globalData.authToken = token

    if (!sessionOk) {
      this.globalData.user_id = ''
      this.globalData.openid = ''
      this.globalData.unionid = ''
      this.globalData.userData = freshDefaultUserData()
      try {
        wx.setStorageSync('isLoggedIn', false)
        wx.setStorageSync('authToken', '')
        wx.setStorageSync('user_id', '')
        wx.setStorageSync('openid', '')
        wx.setStorageSync('unionid', '')
        wx.setStorageSync('userData', this.globalData.userData)
      } catch (e) {}
    } else {
      this.globalData.user_id = String(safeGetStorage('user_id', '') || '')
      this.globalData.openid = String(safeGetStorage('openid', '') || '')
      this.globalData.unionid = String(safeGetStorage('unionid', '') || '')
      this.globalData.userData = safeGetStorage('userData', this.globalData.userData) || this.globalData.userData
      // 冷启动恢复登录时可能没有走过 auth 页的 finishAuthUi，补写后首页指引条件才能满足
      try {
        if (!isMainDone('authDone')) {
          markMainDone('authDone')
        }
      } catch (e) {}
    }

    this.globalData.stars = Number(safeGetStorage('userStars', 0) || 0)
    this.globalData.booksRead = Number(safeGetStorage('booksRead', 0) || 0)
    this.globalData.coloringWorks = Number(safeGetStorage('coloringWorks', 0) || 0)
    this.globalData.clonedVoices = Number(safeGetStorage('clonedVoices', 0) || 0)
    this.globalData.speakerTasks = Number(safeGetStorage('speakerTasks', 0) || 0)
    this.globalData.checkInRecord = safeGetStorage('checkInRecord', {}) || {}
    this.globalData.rewardsClaimed = safeGetStorage('rewardsClaimed', {}) || {}
    this.globalData.lastCheckInDate = safeGetStorage('lastCheckInDate', '') || ''
    this.globalData.favorites = safeGetStorage('favorites', []) || []
    this.globalData.aiStories = safeGetStorage('aiStories', []) || []
    this.globalData.voiceId = String(safeGetStorage('voiceId', '') || '')
    this.globalData.globalVoiceName = String(safeGetStorage('globalVoiceName', this.globalData.globalVoiceName) || this.globalData.globalVoiceName)
    this.globalData.voiceList = safeGetStorage(STORAGE_KEY_VOICE_LIST_CACHE, []) || []
    this.globalData.voiceRoleMap = safeGetStorage(STORAGE_KEY_VOICE_ROLE_MAP, {}) || {}
  },

  /** 退出登录：清空 token、账号缓存与展示用资料 */
  clearLoginSession() {
    this.globalData.isLoggedIn = false
    this.globalData.authToken = ''
    this.globalData.user_id = ''
    this.globalData.openid = ''
    this.globalData.unionid = ''
    this.globalData.userData = freshDefaultUserData()
    try {
      wx.setStorageSync('isLoggedIn', false)
      wx.setStorageSync('authToken', '')
      wx.setStorageSync('user_id', '')
      wx.setStorageSync('openid', '')
      wx.setStorageSync('unionid', '')
      wx.setStorageSync('userData', this.globalData.userData)
    } catch (e) {}
  },

  saveData(key, value) {
    try { wx.setStorageSync(key, value) } catch (e) {}
  },

  getAuthToken() {
    const inMemory = String((this.globalData && this.globalData.authToken) || '').trim()
    if (inMemory) return inMemory
    const fromStorage = String(safeGetStorage('authToken', '') || '').trim()
    if (fromStorage) {
      this.globalData.authToken = fromStorage
      return fromStorage
    }
    return ''
  },

  getUserId() {
    const gid = String((this.globalData && (this.globalData.user_id || this.globalData.openid)) || '').trim()
    if (gid) return gid
    const sid = String(safeGetStorage('user_id', '') || safeGetStorage('openid', '') || '').trim()
    if (sid) {
      this.globalData.user_id = sid
      return sid
    }
    return ''
  },

  _authHeader() {
    const token = this.getAuthToken()
    return token ? { Authorization: `Bearer ${token}` } : {}
  },

  loginWithWechat(done, options) {
    const base = this.getApiBaseUrl()
    const loginOpts = (options && typeof options === 'object') ? options : {}
    const fallbackDev = (why) => {
      this._loginWithDevFallback({ base, why, account: String(loginOpts.account || '').trim() }, done)
    }
    wx.login({
      success: (lr) => {
        const code = String((lr && lr.code) || '').trim()
        if (!code) {
          fallbackDev('wx.login 未获取到 code')
          return
        }
        wx.request({
          url: `${base}/auth/wechat/login`,
          method: 'POST',
          header: { 'Content-Type': 'application/json' },
          data: { code },
          success: (res) => {
            const body = (res && res.data) || {}
            const user = body.user || {}
            const token = String(body.token || '').trim()
            if (res.statusCode !== 200 || !token) {
              fallbackDev(body.detail || body.message || `微信登录失败(${res.statusCode})`)
              return
            }
            const userId = String(user.user_id || user.openid || '').trim()
            this.globalData.authToken = token
            this.globalData.user_id = userId
            this.globalData.openid = String(user.openid || '').trim()
            this.globalData.unionid = String(user.unionid || '').trim()
            this.globalData.isLoggedIn = true
            this.saveData('authToken', token)
            this.saveData('user_id', this.globalData.user_id)
            this.saveData('openid', this.globalData.openid)
            this.saveData('unionid', this.globalData.unionid)
            this.saveData('isLoggedIn', true)
            done && done(null, body)
          },
          fail: (err) => fallbackDev((err && err.errMsg) || '登录请求失败'),
        })
      },
      fail: (err) => fallbackDev((err && err.errMsg) || 'wx.login 失败'),
    })
  },

  _loginWithDevFallback(ctx, done) {
    const base = (ctx && ctx.base) || this.getApiBaseUrl()
    const account = String((ctx && ctx.account) || '').trim()
    let userId = ''
    let openid = ''
    let phone = ''
    let email = ''
    if (/^\d{11}$/.test(account)) {
      phone = account
      userId = `dev_local_phone_${account}`
      openid = userId
    } else if (account.includes('@')) {
      email = account.toLowerCase()
      const slug = email.replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 72)
      userId = `dev_local_email_${slug || 'user'}`
      openid = userId
    } else {
      try {
        let anon = wx.getStorageSync('dev_anonymous_user_id')
        if (!anon || String(anon).length < 8) {
          const ts = Date.now()
          const rnd = Math.random().toString(16).slice(2, 10)
          anon = `dev_local_anon_${ts}_${rnd}`
          wx.setStorageSync('dev_anonymous_user_id', anon)
        }
        userId = String(anon).trim()
        openid = userId
      } catch (e) {
        const ts = Date.now()
        const rnd = Math.random().toString(16).slice(2, 8)
        userId = `dev_wx_user_${ts}_${rnd}`
        openid = userId
      }
    }
    const payload = { user_id: userId, openid }
    if (phone) payload.phone = phone
    if (email) payload.email = email
    wx.request({
      url: `${base}/auth/dev/login`,
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: payload,
      success: (res) => {
        const body = (res && res.data) || {}
        const user = body.user || {}
        const token = String(body.token || '').trim()
        if (res.statusCode !== 200 || Number(body.code) !== 0 || !token) {
          done && done(new Error(body.detail || body.message || 'Dev登录失败'))
          return
        }
        const finalId = String(user.user_id || user.openid || userId).trim()
        this.globalData.authToken = token
        this.globalData.user_id = finalId
        this.globalData.openid = String(user.openid || finalId).trim()
        this.globalData.unionid = String(user.unionid || '').trim()
        this.globalData.isLoggedIn = true
        this.saveData('authToken', token)
        this.saveData('user_id', this.globalData.user_id)
        this.saveData('openid', this.globalData.openid)
        this.saveData('unionid', this.globalData.unionid)
        this.saveData('isLoggedIn', true)
        done && done(null, { ...body, dev_fallback: true, why: (ctx && ctx.why) || '' })
      },
      fail: (err) => done && done(err || new Error('Dev登录请求失败')),
    })
  },

  fetchMyProfile(done) {
    const base = this.getApiBaseUrl()
    wx.request({
      url: `${base}/users/me`,
      method: 'GET',
      header: this._authHeader(),
      success: (res) => {
        const body = (res && res.data) || {}
        if (res.statusCode !== 200 || Number(body.code) !== 0 || !body.user) {
          done && done(new Error(body.detail || body.message || '获取资料失败'))
          return
        }
        const u = body.user || {}
        this.globalData.user_id = String(u.user_id || '').trim()
        this.globalData.openid = String(u.openid || '').trim()
        this.globalData.unionid = String(u.unionid || '').trim()
        this.globalData.userData = {
          ...this.globalData.userData,
          avatar: String(u.avatar || ''),
          parentName: String(u.parent_name || this.globalData.userData.parentName || ''),
          babyName: String(u.baby_name || this.globalData.userData.babyName || ''),
          babyAge: String(u.baby_age || this.globalData.userData.babyAge || ''),
          email: String(u.email || ''),
          phone: String(u.phone || ''),
        }
        const rs = Number(u.reader_stars)
        if (Number.isFinite(rs) && rs >= 0) {
          this.globalData.stars = rs
          this.saveData('userStars', rs)
        }
        this.saveData('user_id', this.globalData.user_id)
        this.saveData('openid', this.globalData.openid)
        this.saveData('unionid', this.globalData.unionid)
        this.saveData('userData', this.globalData.userData)
        if (shouldAutoAssignParentName(this.globalData.userData.parentName)) {
          const autoName = randomParentNickname()
          this.globalData.userData.parentName = autoName
          this.saveData('userData', this.globalData.userData)
          // 非阻塞回写服务端：首次登录自动分配一个更友好的家长昵称
          this.updateMyProfile({ parent_name: autoName }, () => {})
        }
        done && done(null, body)
      },
      fail: (err) => done && done(err || new Error('获取资料失败')),
    })
  },

  updateMyProfile(payload, done) {
    const base = this.getApiBaseUrl()
    const body = payload || {}
    // 显式 JSON 字符串：部分基础库对 PUT + application/json 的 data 对象序列化不稳定，易导致服务端收到空 body
    const dataStr = typeof body === 'string' ? body : JSON.stringify(body)
    wx.request({
      url: `${base}/users/me/profile`,
      method: 'PUT',
      header: { ...this._authHeader(), 'Content-Type': 'application/json' },
      data: dataStr,
      success: (res) => {
        const body = (res && res.data) || {}
        if (res.statusCode !== 200 || Number(body.code) !== 0 || !body.user) {
          const d = body.detail
          const detailStr =
            typeof d === 'string'
              ? d
              : Array.isArray(d)
                ? d.map((x) => (x && (x.msg || x.message)) || '').filter(Boolean).join(',')
                : ''
          done && done(new Error(detailStr || body.message || '保存资料失败'))
          return
        }
        const u = body.user || {}
        this.globalData.userData = {
          ...this.globalData.userData,
          avatar: String(u.avatar || ''),
          parentName: String(u.parent_name || this.globalData.userData.parentName || ''),
          babyName: String(u.baby_name || this.globalData.userData.babyName || ''),
          babyAge: String(u.baby_age || this.globalData.userData.babyAge || ''),
          email: String(u.email || ''),
          phone: String(u.phone || ''),
        }
        const rs2 = Number(u.reader_stars)
        if (Number.isFinite(rs2) && rs2 >= 0) {
          this.globalData.stars = rs2
          this.saveData('userStars', rs2)
        }
        this.saveData('userData', this.globalData.userData)
        done && done(null, body)
      },
      fail: (err) => done && done(err || new Error('保存资料失败')),
    })
  },

  updateLevel() {
    const levelInfo = this.calculateLevel(this.globalData.stars)
    this.globalData.level = levelInfo.level
  },

  addStars(amount) {
    const inc = Number(amount || 0) || 0
    this.globalData.stars += inc
    this.saveData('userStars', this.globalData.stars)
    // 今日星星累计（按日期存储，供首页显示“今日获得进度”）
    try {
      const key = new Date().toISOString().split('T')[0]
      const sk = `todayStars.${key}`
      const prev = Number(wx.getStorageSync(sk) || 0) || 0
      wx.setStorageSync(sk, Math.max(0, prev + inc))
    } catch (e) {}
    this.updateLevel()
  },
  
  checkIn() {
    const todayDate = new Date().toISOString().split('T')[0]
    if (this.globalData.lastCheckInDate === todayDate) return false
    this.globalData.lastCheckInDate = todayDate
    this.addStars(2)
    this.saveData('lastCheckInDate', todayDate)
    return true
  },
  
  login() {
    this.globalData.isLoggedIn = true
    this.saveData('isLoggedIn', true)
  },
  
  register() {
    this.login()
    this.globalData.stars = 0
    this.globalData.booksRead = 0
    this.globalData.coloringWorks = 0
    this.globalData.clonedVoices = 0
    this.globalData.speakerTasks = 0
    this.globalData.checkInRecord = {}
    this.globalData.rewardsClaimed = {}
    this.globalData.lastCheckInDate = ''
    this.globalData.voiceId = ''
    this.globalData.globalVoiceName = '基础音色（默认）'
    this.saveData('userStars', 0)
    this.saveData('booksRead', 0)
    this.saveData('coloringWorks', 0)
    this.saveData('clonedVoices', 0)
    this.saveData('speakerTasks', 0)
    this.saveData('checkInRecord', {})
    this.saveData('rewardsClaimed', {})
    this.saveData('lastCheckInDate', '')
    this.saveData('voiceId', '')
    this.saveData('globalVoiceName', '基础音色（默认）')
  },

  logout() {
    this.globalData.isLoggedIn = false
    this.globalData.authToken = ''
    this.saveData('isLoggedIn', false)
    this.saveData('authToken', '')
    if (typeof this.refreshVoiceList === 'function') {
      this.refreshVoiceList()
    }
  }
})
