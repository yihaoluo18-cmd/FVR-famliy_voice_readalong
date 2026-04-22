const app = getApp();
const { toMiniprogramAssetUrl } = require("../../utils/asset-url.js");
const { isMainDone, markMainDone } = require("../../utils/guide-flow.js");
const { resolveApiBase } = require("../../utils/api-base.js");

const SENTENCES = [
  '很久很久以前，在森林深处有一座会发光的小木屋。',
  '小熊兜兜决定去寻找传说中的魔法星星。',
  '一只会说话的彩色蝴蝶飞到了他的面前。',
  '他深吸一口气，小声说：今天一定会有好消息。',
  '月光洒在树叶上，沙沙作响，像在为勇敢的孩子鼓掌。',
  '清晨的第一缕阳光穿过窗帘，他微笑着说：新的一天开始啦。'
];

const MIN_TRAIN_SENTENCE_COUNT = 5;

function createEmptyRecordFiles() {
  return new Array(SENTENCES.length).fill('');
}

function normalizeRecordFiles(list) {
  const normalized = Array.isArray(list) ? list.slice(0, SENTENCES.length) : [];
  while (normalized.length < SENTENCES.length) normalized.push('');
  return normalized;
}

function countRecordedSentences(list) {
  return normalizeRecordFiles(list).filter(Boolean).length;
}

const RECORD_MIN_SECONDS = 4;
const RECORD_MAX_SECONDS = 35;

const ROLE_PRESETS = [
  { key: 'mom', label: '妈妈', emoji: '👩', quickName: '妈妈温柔讲读' },
  { key: 'dad', label: '爸爸', emoji: '👨', quickName: '爸爸沉稳讲读' },
  { key: 'custom', label: '自定义', emoji: '✨', quickName: '自定义专属讲读' },
];

const VOICE_CLONE_DRAFT_KEY = 'voiceCloneDraftState.v1';
const FIRST_TRAIN_EGG_GUIDE_KEY = 'voiceFirstTrainEggGuideShown.v1';
const SCIENCE_SWITCH_SECONDS = 18;
const SCIENCE_MASCOT_IMAGES = [
  '/assets/images/小狗.png',
  '/assets/images/狐狸.png',
  '/assets/images/小兔.png',
  '/assets/images/小猫.png',
];

function pickScienceMascotImage() {
  const pool = SCIENCE_MASCOT_IMAGES.map((p) => toMiniprogramAssetUrl(p));
  return pool[Math.floor(Math.random() * pool.length)] || toMiniprogramAssetUrl('/assets/images/小狗.png');
}

function normalizeDraftAssetImage(u) {
  const s = String(u || "").trim();
  if (!s) return toMiniprogramAssetUrl("/assets/images/小狗.png");
  if (/^https?:\/\//i.test(s)) return s;
  if (s.startsWith("/assets/")) return toMiniprogramAssetUrl(s);
  return s;
}
const SCIENCE_FALLBACK_TIPS = [
  '科普小课堂：海豚睡觉时会一半大脑休息，一半大脑保持清醒，这样才能记得呼吸。',
  '科普小课堂：月亮本身不会发光，我们看到的月光其实是太阳光的反射。',
  '科普小课堂：竹子其实是草，而且是长得非常快的草本植物。',
  '科普小课堂：彩虹是阳光通过小水滴折射后形成的七彩光带。',
  '科普小课堂：企鹅在陆地上摇摇摆摆，在水里却是游泳高手。',
];
const SCIENCE_INTRO_PREFIX = '在等待声音魔法实战时，我们先来看看一些有趣的知识吧。';
const TRAIN_UI_TARGET_MS = 2 * 60 * 1000; // 约 2 分钟进度体验

function getApiBase() {
  return resolveApiBase(app);
}

Page({
  data: {
    step: 1,
    parentType: 'mom',
    relationOptions: ROLE_PRESETS,
    selectedRelationKey: 'mom',
    customRoleName: '',

    sentences: SENTENCES,
    totalSentences: SENTENCES.length,
    sentenceIdx: 0,
    currentSentence: SENTENCES[0],

    isRecording: false,
    progress: 0,
    pulseClass: 'pulseClass',
    recordingClass: 'recordingClass',
    circleOffset: 351.858,

    recordFiles: createEmptyRecordFiles(),
    recordSeconds: 0,
    recordTimer: null,

    canGenerate: false,
    isGenerating: false,
    trainingTaskId: '',
    trainingMessage: '',
    selectedVoiceName: '基础音色（默认）',
    trainedVoiceId: '',
    voiceNameInput: '',
    isSavingVoiceName: false,

    showApiConfig: false,
    apiBaseInput: '',

    previewAudioPath: '',
    isAudioPlaying: false,
    audioContext: null,

    trainingVoiceName: '',
    scienceTips: [],
    scienceTipIndex: 0,
    scienceTipText: '',
    scienceMascotImage: toMiniprogramAssetUrl('/assets/images/小狗.png'),
    isScienceSpeaking: false,
    scienceAudioContext: null,
    voiceAssetIconBack: toMiniprogramAssetUrl('/assets/icons/back.png'),
    voiceAssetIconSetting: toMiniprogramAssetUrl('/assets/icons/setting.png'),
    voiceAssetMom: toMiniprogramAssetUrl('/assets/images/mom1.png'),
    voiceAssetDad: toMiniprogramAssetUrl('/assets/images/dad1.png'),
    voiceAssetRecordIdle: toMiniprogramAssetUrl('/assets/icons/录音.png'),
    voiceAssetRecordBusy: toMiniprogramAssetUrl('/assets/icons/停止.png'),
    voiceAssetBingo: toMiniprogramAssetUrl('/assets/icons/bingo.png'),
    showGuide: false,
    guideSteps: [],
    guideStepIndex: 0,
    guideHighlight: '',
    guideTitle: '',
    guideDesc: '',
    showTrainingEggGuide: false,
  },

  onLoad() {
    this._pageVisible = true;
    this._pollTimer = null;
    this._scienceTimer = null;
    this._restorePrompted = false;
    this._uploadedLocalPathByIndex = {};
    this._uploadVersionByIndex = {};
    this.recorderManager = wx.getRecorderManager();

    this.recorderManager.onStop((res) => {
      if (this.data.recordTimer) {
        clearInterval(this.data.recordTimer);
        this.data.recordTimer = null;
      }
      const durationFromRecorder = Number((res && res.duration) || 0) / 1000;
      const durationSec = Math.max(Number(this.data.recordSeconds || 0), durationFromRecorder);
      const tempFilePath = String((res && res.tempFilePath) || '');
      if (!tempFilePath || durationSec < RECORD_MIN_SECONDS) {
        this.setData({
          isRecording: false,
          recordSeconds: 0,
          progress: 0,
        });
        wx.showToast({ title: `\u5f55\u97f3\u592a\u77ed\uff0c\u8bf7\u81f3\u5c11\u5f55 ${RECORD_MIN_SECONDS} \u79d2`, icon: 'none' });
        this.checkCanGenerate();
        return;
      }

      const curIdx = this.data.sentenceIdx;

      const files = normalizeRecordFiles(this.data.recordFiles);
      files[curIdx] = tempFilePath;

      const allDone = countRecordedSentences(files) >= MIN_TRAIN_SENTENCE_COUNT && files.every(Boolean);
      const nextIdx = Math.min(curIdx + 1, SENTENCES.length - 1);

      this.setData({
        isRecording: false,
        recordFiles: files,
        previewAudioPath: files[curIdx] || '',
        sentenceIdx: allDone ? curIdx : nextIdx,
        currentSentence: allDone ? SENTENCES[curIdx] : SENTENCES[nextIdx],
        progress: allDone ? 100 : 0,
        step: allDone ? 2 : 1,
      });
      // 每句录完后立刻后台上传，训练阶段只补传失败/缺失句子。
      this._uploadedLocalPathByIndex[curIdx] = '';
      this._uploadSentenceAfterRecord(curIdx, tempFilePath);
      this.checkCanGenerate();
    });

    this.recorderManager.onError((err) => {
      if (this.data.recordTimer) {
        clearInterval(this.data.recordTimer);
        this.data.recordTimer = null;
      }
      this.setData({ isRecording: false, recordSeconds: 0, progress: 0 });
      wx.showToast({ title: `录音失败：${(err && err.errMsg) || '未知错误'}`, icon: 'none' });
    });

    this.setData({
      currentSentence: SENTENCES[0],
      audioContext: wx.createInnerAudioContext(),
      scienceAudioContext: wx.createInnerAudioContext(),
      apiBaseInput: resolveApiBase(app)
    });

    if (app && app.refreshVoiceList) app.refreshVoiceList();
    this._tryRestoreDraftOnEnter();
  },

  onShow() {
    this._pageVisible = true;
    if (this._restorePrompted) return;
    this._tryRestoreDraftOnEnter();
    this.initVoiceGuide();
  },

  onHide() {
    this._pageVisible = false;
    this._stopScienceNarration();
    this._hideTrainingEggGuide();
    this._saveCloneDraft();
  },

  onUnload() {
    this._pageVisible = false;
    this._clearPoll();
    this._stopScienceNarration();
    if (this.data.recordTimer) {
      clearInterval(this.data.recordTimer);
      this.data.recordTimer = null;
    }
    this._saveCloneDraft();
    try {
      if (this.data.audioContext) this.data.audioContext.destroy();
      if (this.data.scienceAudioContext) this.data.scienceAudioContext.destroy();
    } catch (e) {}
  },

  toggleApiConfig() {
    this.setData({ showApiConfig: !this.data.showApiConfig });
  },

  onApiBaseInput(e) {
    const v = (e && e.detail && e.detail.value) ? String(e.detail.value) : '';
    this.setData({ apiBaseInput: v });
  },

  saveApiBase() {
    const v = String(this.data.apiBaseInput || '').trim().replace(/\/+$/, '');
    if (!/^https?:\/\//.test(v)) {
      wx.showToast({ title: '请输入 http/https 地址', icon: 'none' });
      return;
    }
    if (app && app.setApiBaseUrl) app.setApiBaseUrl(v);
    else {
      try { wx.setStorageSync('apiBaseUrl', v); } catch (e) {}
    }
    wx.showToast({ title: 'API地址已保存', icon: 'success' });
    this.setData({ showApiConfig: false });
    if (app && app.refreshVoiceList) app.refreshVoiceList();
  },

  _getPresetByKey(key) {
    const k = String(key || '').trim();
    return ROLE_PRESETS.find((x) => x.key === k) || ROLE_PRESETS[0];
  },

  _getDefaultRelationByParent(parentType) {
    const p = String(parentType || '').trim();
    if (p === 'dad') return 'dad';
    if (p === 'custom') return 'custom';
    return 'mom';
  },

  _resolveDisplayRoleLabel() {
    const key = String(this.data.selectedRelationKey || '').trim();
    if (key === 'custom') {
      const n = String(this.data.customRoleName || '').trim();
      return n || '自定义';
    }
    const preset = this._getPresetByKey(key);
    return String(preset.label || '自定义');
  },

  _resolveRoleBindingKey() {
    const key = String(this.data.selectedRelationKey || '').trim();
    if (key !== 'custom') return key || this._getDefaultRelationByParent(this.data.parentType);
    const n = String(this.data.customRoleName || '').trim();
    return n ? `custom:${n}` : 'custom';
  },

  selectMom() {
    if (this.data.parentType === 'mom') return;
    this._resetForParent('mom');
  },

  selectDad() {
    if (this.data.parentType === 'dad') return;
    this._resetForParent('dad');
  },

  selectCustom() {
    if (this.data.parentType === 'custom') return;
    this._resetForParent('custom');
  },

  onCustomRoleNameInput(e) {
    const v = (e && e.detail && e.detail.value) ? String(e.detail.value) : '';
    this.setData({ customRoleName: v });
  },

  onUsePresetName(e) {
    const name = String((e && e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.name) || '').trim();
    if (!name) return;
    this.setData({ voiceNameInput: name });
  },

  _resetForParent(parentType) {
    this._clearPoll();
    if (this.data.recordTimer) {
      clearInterval(this.data.recordTimer);
      this.data.recordTimer = null;
    }
    const relationKey = this._getDefaultRelationByParent(parentType);
    const preset = this._getPresetByKey(relationKey);
    this.setData({
      parentType,
      step: 1,
      sentenceIdx: 0,
      currentSentence: SENTENCES[0],
      isRecording: false,
      progress: 0,
      recordSeconds: 0,
      recordFiles: createEmptyRecordFiles(),
      canGenerate: false,
      isGenerating: false,
      trainingTaskId: '',
      trainingMessage: '',
      previewAudioPath: '',
      isAudioPlaying: false,
      selectedVoiceName: '基础音色（默认）',
      selectedRelationKey: relationKey,
      customRoleName: relationKey === 'custom' ? this.data.customRoleName : '',
      trainedVoiceId: '',
      voiceNameInput: preset.quickName || '',
      isSavingVoiceName: false,
      trainingVoiceName: '',
      scienceTips: [],
      scienceTipIndex: 0,
      scienceTipText: '',
      scienceMascotImage: pickScienceMascotImage(),
      isScienceSpeaking: false,
    });
    this._uploadedLocalPathByIndex = {};
    this._uploadVersionByIndex = {};
    this._clearCloneDraft();
    wx.vibrateShort();
  },

  _uploadSentenceAfterRecord(sentenceIndex, filePath) {
    const userId = this._buildCloneUserId();
    const idx = Number(sentenceIndex);
    if (!filePath || Number.isNaN(idx)) return;
    const version = Number(this._uploadVersionByIndex[idx] || 0) + 1;
    this._uploadVersionByIndex[idx] = version;
    this._uploadSentence({
      userId,
      sentenceIndex: idx,
      sentenceText: SENTENCES[idx] || '',
      filePath
    }).then(() => {
      // 若期间发生重录，以最新版本为准，避免旧上传覆盖状态。
      if (Number(this._uploadVersionByIndex[idx] || 0) !== version) return;
      this._uploadedLocalPathByIndex[idx] = filePath;
    }).catch(() => {
      if (Number(this._uploadVersionByIndex[idx] || 0) !== version) return;
      this._uploadedLocalPathByIndex[idx] = '';
    });
  },

  startRecording() {
    if (this.data.isRecording || this.data.isGenerating) return;
    wx.getSetting({
      success: (res) => {
        if (!res.authSetting['scope.record']) {
          wx.authorize({
            scope: 'scope.record',
            success: () => this.startRealRecord(),
            fail: () => {
              wx.showModal({
                title: '需要麦克风权限',
                content: '录制声音需要开启麦克风权限',
                confirmText: '去设置',
                success: (r) => { if (r && r.confirm) wx.openSetting(); }
              });
            }
          });
          return;
        }
        this.startRealRecord();
      }
    });
  },

  startRealRecord() {
    if (this.data.recordTimer) {
      clearInterval(this.data.recordTimer);
      this.data.recordTimer = null;
    }
    this.setData({ isRecording: true, recordSeconds: 0, progress: 0 });

    this.recorderManager.start({
      format: 'wav',
      sampleRate: 32000,
      numberOfChannels: 1,
      duration: RECORD_MAX_SECONDS * 1000
    });

    let sec = 0;
    this.data.recordTimer = setInterval(() => {
      sec += 1;
      this.setData({
        recordSeconds: sec,
        progress: Math.min(100, Math.round((sec / RECORD_MAX_SECONDS) * 100))
      });
      if (sec >= RECORD_MAX_SECONDS) this.stopRecord();
    }, 1000);
  },

  stopRecord() {
    if (!this.data.isRecording) return;
    if (this.data.recordSeconds < RECORD_MIN_SECONDS) {
      wx.showToast({ title: '每段至少录 4 秒，音色会更稳定', icon: 'none' });
      return;
    }
    this.recorderManager.stop();
  },

  previewRecording() {
    const ac = this.data.audioContext;
    if (!ac) return;
    const files = this.data.recordFiles || [];
    const path = this.data.previewAudioPath || files.find(Boolean) || '';
    if (!path) {
      wx.showToast({ title: '请先录制', icon: 'none' });
      return;
    }

    if (this.data.isAudioPlaying) {
      ac.pause();
      this.setData({ isAudioPlaying: false });
      return;
    }

    ac.src = path;
    ac.play();
    this.setData({ isAudioPlaying: true, previewAudioPath: path });
    ac.onEnded(() => this.setData({ isAudioPlaying: false }));
  },

  retryRecording() {
    this._resetForParent(this.data.parentType || 'mom');
  },

  checkCanGenerate() {
    const files = normalizeRecordFiles(this.data.recordFiles);
    const canGenerate = countRecordedSentences(files) >= MIN_TRAIN_SENTENCE_COUNT && files.every(Boolean);
    this.setData({ canGenerate, recordFiles: files });
  },

  async startTraining() {
    if (this.data.isGenerating) return;

    const files = normalizeRecordFiles(this.data.recordFiles);
    const validSentenceCount = countRecordedSentences(files);
    if (validSentenceCount < MIN_TRAIN_SENTENCE_COUNT) {
      wx.showToast({ title: `至少需要录制${MIN_TRAIN_SENTENCE_COUNT}句后才能训练`, icon: 'none' });
      return;
    }

    if (!files.every(Boolean)) {
      wx.showToast({ title: '请先完成全部句子录制', icon: 'none' });
      return;
    }

    this.setData({ recordFiles: files, canGenerate: true });

    const initVoiceName = this._resolveInitialVoiceName();
    if (!initVoiceName) {
      wx.showToast({ title: '请先确认音色名称', icon: 'none' });
      return;
    }

    let allowOverwrite = false;
    try {
      const check = await this._checkModelName(initVoiceName);
      if (check && check.exists) {
        const confirmRes = await new Promise((resolve) => {
          wx.showModal({
            title: '名称已存在',
            content: `音色名称“${initVoiceName}”已存在。是否覆盖旧音色？`,
            confirmText: '覆盖旧音色',
            cancelText: '取消',
            success: (r) => resolve(!!(r && r.confirm)),
            fail: () => resolve(false),
          });
        });
        if (!confirmRes) return;
        allowOverwrite = true;
      }
    } catch (e) {}

    this.setData({
      step: 3,
      progress: 8,
      circleOffset: 351.858,
      isGenerating: true,
      trainingMessage: '正在施展声音魔法',
      trainingVoiceName: initVoiceName,
      voiceNameInput: initVoiceName,
    });
    this._maybeShowTrainingEggGuide();
    this._saveCloneDraft();
    wx.vibrateShort();
    this._runTrainPipeline({ voiceName: initVoiceName, allowOverwrite });
  },

  async _runTrainPipeline(options = {}) {
    const userId = this._buildCloneUserId();
    const targetVoiceName = String(options.voiceName || this.data.trainingVoiceName || userId).trim();
    const allowOverwrite = !!options.allowOverwrite;

    try {
      await this._prepareScienceTips();
      this._startScienceNarration();

      await this._uploadAllSentences(userId);
      this._setTrainProgress(58, '已上传完成，开始训练音色...');

      const taskId = await this._startTrainTask(userId, { voiceName: targetVoiceName, allowOverwrite });
      this.setData({ trainingTaskId: taskId, trainingVoiceName: targetVoiceName });
      if (app && typeof app.startGlobalTrainingWatch === 'function') {
        app.startGlobalTrainingWatch({
          taskId,
          voiceName: targetVoiceName,
          source: 'voice_page'
        });
      }
      this._saveCloneDraft();

      const doneInfo = await this._pollTrainStatus(taskId);
      this._setTrainProgress(94, '训练完成，正在刷新音色列表...');

      const voice = await this._resolveTrainedVoice(doneInfo, targetVoiceName);
      if (!voice || !voice.voice_id) throw new Error('训练完成但未找到音色，请稍后在下拉列表刷新查看');
      await this._setGlobalVoice(voice.voice_id, voice.name || voice.voice_id);
      if (app && app.refreshVoiceList) app.refreshVoiceList();

      this._setTrainProgress(100, '训练完成');
      this.completeTraining(voice);
    } catch (err) {
      this._stopScienceNarration();
      if (app && typeof app.clearGlobalTrainingWatch === 'function') {
        app.clearGlobalTrainingWatch({ silent: true });
      }
      this.setData({ isGenerating: false, step: 2 });
      this._saveCloneDraft();
      wx.showToast({ title: (err && err.message) || '训练失败', icon: 'none', duration: 2600 });
    }
  },

  _buildCloneUserId() {
    const fromApp = (app && typeof app.getUserId === 'function' && app.getUserId()) || '';
    const fromGlobal = (app && app.globalData && (app.globalData.user_id || app.globalData.openid)) || '';
    const raw = String(fromApp || fromGlobal || wx.getStorageSync('user_id') || wx.getStorageSync('openid') || '').trim();
    if (raw) return raw;
    return 'wx_clone_user';
  },

  _uploadSentence({ userId, sentenceIndex, sentenceText, filePath }) {
    const base = getApiBase();
    const uploadUrl = `${base}/train/upload_sentence`;
    return new Promise((resolve, reject) => {
      wx.uploadFile({
        url: uploadUrl,
        filePath,
        name: 'audio',
        formData: {
          user_id: userId,
          sentence_index: String(sentenceIndex),
          sentence_text: sentenceText,
          language: '中文'
        },
        success: (res) => {
          let data = {};
          try { data = JSON.parse(res.data || '{}'); } catch (e) {}
          if (res.statusCode === 200 && Number(data.code) === 200) {
            resolve(data);
            return;
          }
          reject(new Error((data && data.message) || `上传失败(${res.statusCode})`));
        },
        fail: (err) => {
          const raw = String((err && err.errMsg) || err || '');
          console.error("[voice] uploadSentence fail", { uploadUrl, raw });
          reject(new Error(`上传失败：${raw || '网络错误'}（接口：${uploadUrl}）`));
        }
      });
    });
  },

  async _uploadAllSentences(userId) {
    const files = this.data.recordFiles || [];
    for (let i = 0; i < files.length; i += 1) {
      const filePath = files[i];
      if (!filePath) throw new Error(`第 ${i + 1} 句录音缺失`);
      if (this._uploadedLocalPathByIndex && this._uploadedLocalPathByIndex[i] === filePath) {
        const pSkip = 16 + Math.round(((i + 1) / files.length) * 42);
        this._setTrainProgress(pSkip, `第 ${i + 1} 句已上传，跳过重复上传`);
        continue;
      }
      this._setTrainProgress(Math.max(16, this.data.progress || 0), `第 ${i + 1} 句上传中...`);
      const uploadResp = await this._uploadSentence({ userId, sentenceIndex: i, sentenceText: SENTENCES[i], filePath });
      this._uploadedLocalPathByIndex[i] = filePath;
      const p = 16 + Math.round(((i + 1) / files.length) * 42);
      const purifyHint = uploadResp && uploadResp.purify_enqueued;
      this._setTrainProgress(
        p,
        purifyHint ? `第 ${i + 1} 句上传成功，正在降噪...` : `第 ${i + 1} 句上传成功`
      );
    }
  },

  _startTrainTask(userId, options = {}) {
    const base = getApiBase();
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${base}/train/start_from_sentences`,
        method: 'POST',
        header: { 'Content-Type': 'application/json' },
        data: {
          user_id: userId,
          model_name: String(options.voiceName || userId || '').trim(),
          allow_overwrite: !!options.allowOverwrite,
          language: '中文',
          scene: '绘本故事',
          emotion: this.data.parentType === 'dad' ? '沉稳' : (this.data.parentType === 'mom' ? '温柔' : '自然')
        },
        success: (res) => {
          const data = (res && res.data) || {};
          if (res.statusCode === 200 && Number(data.code) === 200 && data.task_id) {
            resolve(String(data.task_id));
            return;
          }
          reject(new Error(data.message || '启动训练失败'));
        },
        fail: (err) => reject(this._wrapNetworkError(err, '启动训练失败'))
      });
    });
  },

  _pollTrainStatus(taskId) {
    const base = getApiBase();
    let attempts = 0;
    const maxAttempts = 320;
    const startedAt = Date.now();
    let uiProgress = Math.max(60, Number(this.data.progress || 0));

    const isOomLike = (msg) => {
      const m = String(msg || '').toLowerCase();
      return m.includes('outofmemory') || m.includes('cuda out of memory') || m.includes('torch.outofmemoryerror') || m.includes('显存');
    };

    const nextUiProgress = (backendProgress, elapsedMs) => {
      // 非匀速进度：前快后慢，约 2 分钟到 95~97%
      const t = Math.max(0, elapsedMs);
      const eased = 12 + 84 * (1 - Math.exp(-t / (TRAIN_UI_TARGET_MS * 0.42)));
      const backendMapped = Number.isFinite(backendProgress)
        ? (60 + Math.max(0, Math.min(36, backendProgress * 0.36)))
        : 0;
      const target = Math.max(eased, backendMapped, uiProgress);
      // 每轮小步前进，避免“卡住不动”的体感
      const step = 0.6 + ((attempts % 5) * 0.15);
      uiProgress = Math.min(97, Math.max(uiProgress + step, target));
      return uiProgress;
    };

    return new Promise((resolve, reject) => {
      const run = () => {
        attempts += 1;
        if (attempts > maxAttempts) {
          reject(new Error('训练超时，请稍后重试'));
          return;
        }

        wx.request({
          url: `${base}/train/status?task_id=${encodeURIComponent(taskId)}`,
          method: 'GET',
          success: (res) => {
            const data = (res && res.data) || {};
            const status = String(data.status || '').toLowerCase();
            const backendProgress = Number(data.progress || 0);
            const elapsedMs = Date.now() - startedAt;
            const progress = nextUiProgress(backendProgress, elapsedMs);
            const backendMessage = String(data.message || '').trim();
            this._setTrainProgress(progress, backendMessage || '训练进行中...');

            if (status === 'completed') {
              resolve(data);
              return;
            }
            if (status === 'failed') {
              if (isOomLike(backendMessage)) {
                this._setTrainProgress(
                  Math.min(97, progress + 0.8),
                  '训练资源紧张，正在自动续训，请稍候...'
                );
                this._pollTimer = setTimeout(run, 3500);
                return;
              }
              // 非OOM失败也先保持“训练中”显示，避免前端立刻退出。
              this._setTrainProgress(
                Math.min(97, progress + 0.4),
                '训练任务正在重试中，请稍候...'
              );
              this._pollTimer = setTimeout(run, 3500);
              return;
            }

            this._pollTimer = setTimeout(run, 3000);
          },
          fail: () => {
            this._pollTimer = setTimeout(run, 3500);
          }
        });
      };

      run();
    });
  },

  _fetchVoices() {
    const base = getApiBase();
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${base}/voices`,
        method: 'GET',
        success: (res) => {
          const voices = (res && res.data && Array.isArray(res.data.voices)) ? res.data.voices : [];
          resolve(voices);
        },
        fail: (err) => reject(this._wrapNetworkError(err, '获取音色失败'))
      });
    });
  },

  async _resolveTrainedVoice(doneInfo, expectedName) {
    const voiceId = String((doneInfo && doneInfo.voice_id) || '').trim();
    const voices = await this._fetchVoices();

    if (voiceId) {
      const hit = voices.find(v => String(v.voice_id || '') === voiceId);
      return hit || { voice_id: voiceId, name: expectedName || voiceId };
    }

    const candidates = voices.filter((v) => {
      const n = String(v.name || '').toLowerCase();
      const target = String(expectedName || '').toLowerCase();
      return target ? n === target : false;
    });

    if (!candidates.length) return null;
    candidates.sort((a, b) => String(b.trained_at || '').localeCompare(String(a.trained_at || '')));
    return candidates[0];
  },
  _setGlobalVoice(voiceId, voiceName) {
    const vid = String(voiceId || '').trim();
    if (!vid) return Promise.resolve({ code: 0, message: 'cleared' });

    const current = (app && app.getVoiceId) ? String(app.getVoiceId() || '').trim() : '';
    if (current && current === vid) {
      return Promise.resolve({ code: 0, message: 'already_selected', voice_id: vid, skipped: true });
    }

    return new Promise((resolve, reject) => {
      if (app && app.setGlobalVoice) {
        app.setGlobalVoice(vid, voiceName, (err, data) => {
          if (err) {
            reject(err);
            return;
          }
          resolve(data || { code: 0, voice_id: vid });
        });
        return;
      }

      const base = getApiBase();
      wx.request({
        url: `${base}/use_voice`,
        method: 'POST',
        header: { 'Content-Type': 'application/json' },
        data: { voice_id: vid },
        success: (res) => {
          const data = (res && res.data) || {};
          if (res.statusCode === 200 && Number(data.code) === 0) {
            resolve(data);
            return;
          }
          reject(new Error(data.message || '切换音色失败'));
        },
        fail: (err) => reject(this._wrapNetworkError(err, '切换音色失败')),
      });
    });
  },

  _deleteVoice(voiceId) {
    const base = getApiBase();
    const vid = String(voiceId || '').trim();
    if (!vid) return Promise.resolve();
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${base}/voices/${encodeURIComponent(vid)}`,
        method: 'DELETE',
        success: (res) => {
          const data = (res && res.data) || {};
          if (res.statusCode === 200 && Number(data.code) === 0) {
            resolve(data);
            return;
          }
          reject(new Error(data.message || '删除旧音色失败'));
        },
        fail: (err) => reject(this._wrapNetworkError(err, '删除旧音色失败'))
      });
    });
  },

  _isDomainListError(msg) {
    const m = String(msg || '').toLowerCase();
    return m.includes('not in domain list') || m.includes('url not in domain');
  },

  _wrapNetworkError(err, fallbackTitle) {
    const raw = String((err && err.errMsg) || err || fallbackTitle || '网络请求失败');
    if (this._isDomainListError(raw)) {
      const base = resolveApiBase(app);
      const legacy = String(wx.getStorageSync('readalong.apiBaseUrl') || '').trim();
      const tip = legacy && legacy !== base
        ? `当前接口域名未加入白名单：${base}。检测到旧版地址：${legacy}，请切到该地址后重试。`
        : `当前接口域名未加入白名单：${base}。请在小程序后台开发设置-服务器域名添加该域名，或在开发者工具勾选不校验合法域名。`;
      wx.showModal({
        title: '域名未在白名单',
        content: tip,
        confirmText: (legacy && legacy !== base) ? '切换旧地址' : '复制地址',
        cancelText: '我知道了',
        success: (res) => {
          if (!(res && res.confirm)) return;
          if (legacy && legacy !== base && app && app.setApiBaseUrl) {
            app.setApiBaseUrl(legacy);
            wx.showToast({ title: '已切换旧地址，请重试', icon: 'none' });
            return;
          }
          wx.setClipboardData({ data: base });
        }
      });
      return new Error('接口域名未在小程序白名单，请按提示处理后重试');
    }
    // 兜底：把当前 base 也拼进错误，便于你直接确认真机走的到底哪个地址
    const base = (() => {
      try { return getApiBase(); } catch (e) { return ''; }
    })();
    const baseHint = base ? `（base：${base}）` : '';
    return new Error(`${raw || fallbackTitle || '网络请求失败'}${baseHint}`);
  },

  _renameVoice(voiceId, name) {
    const base = getApiBase();
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${base}/voices/rename`,
        method: 'POST',
        header: { 'Content-Type': 'application/json' },
        data: { voice_id: voiceId, name },
        success: (res) => {
          const data = (res && res.data) || {};
          if (res.statusCode === 200 && Number(data.code) === 0) {
            resolve(data);
            return;
          }
          reject(new Error(data.message || '保存名称失败'));
        },
        fail: (err) => reject(this._wrapNetworkError(err, '保存名称失败'))
      });
    });
  },

  onVoiceNameInput(e) {
    const v = (e && e.detail && e.detail.value) ? String(e.detail.value) : '';
    this.setData({ voiceNameInput: v });
  },

  async saveVoiceName() {
    if (this.data.isSavingVoiceName) return;

    const voiceId = String(this.data.trainedVoiceId || '').trim();
    const name = String(this.data.voiceNameInput || '').trim();
    const roleKey = this._resolveRoleBindingKey();
    const roleLabel = this._resolveDisplayRoleLabel();

    if (!voiceId) {
      wx.showToast({ title: '未找到训练音色', icon: 'none' });
      return;
    }
    if (!name) {
      wx.showToast({ title: '请先输入名称', icon: 'none' });
      return;
    }
    if (name.length > 32) {
      wx.showToast({ title: '名称最多32字符', icon: 'none' });
      return;
    }
    if (this.data.selectedRelationKey === 'custom' && !String(this.data.customRoleName || '').trim()) {
      wx.showToast({ title: '请先填写“这是谁的声音”', icon: 'none' });
      return;
    }

    const oldBound = (app && app.getVoiceByRole) ? app.getVoiceByRole(roleKey) : null;
    const oldVoiceId = String((oldBound && oldBound.voiceId) || '').trim();

    this.setData({ isSavingVoiceName: true });
    try {
      await this._renameVoice(voiceId, name);
      if (app && app.refreshVoiceList) {
        await new Promise((resolve) => app.refreshVoiceList(() => resolve()));
      }
      await this._setGlobalVoice(voiceId, name);

      if (app && app.setVoiceRoleVoice) {
        app.setVoiceRoleVoice(roleKey, voiceId, name);
      }

      if ((roleKey === 'mom' || roleKey === 'dad') && oldVoiceId && oldVoiceId !== voiceId) {
        try {
          await this._deleteVoice(oldVoiceId);
          if (app && app.refreshVoiceList) app.refreshVoiceList();
        } catch (e) {
          // 旧音色删除失败不阻断主流程
        }
      }

      this.setData({ selectedVoiceName: name, voiceNameInput: name });
      markMainDone("voiceDone");
      this.closeGuide();
      wx.showToast({ title: `${roleLabel}音色已保存`, icon: 'success' });
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '保存名称失败', icon: 'none' });
    } finally {
      this.setData({ isSavingVoiceName: false });
    }
  },

  _setTrainProgress(progress, message) {
    const p = Math.round(Math.max(0, Math.min(100, Number(progress || 0))));
    const circleOffset = 351.858 - (351.858 * p) / 100;
    this.setData({
      progress: p,
      circleOffset,
      trainingMessage: String(message || '正在施展声音魔法')
    });
    this._saveCloneDraft();
  },

  _clearPoll() {
    if (this._pollTimer) {
      clearTimeout(this._pollTimer);
      this._pollTimer = null;
    }
  },

  completeTraining(voice) {
    this._clearPoll();
    this._stopScienceNarration();
    this._hideTrainingEggGuide();
    if (app && typeof app.clearGlobalTrainingWatch === 'function') {
      app.clearGlobalTrainingWatch({ silent: true });
    }
    app.globalData.stars = (app.globalData.stars || 0) + 10;
    app.globalData.clonedVoices = (app.globalData.clonedVoices || 0) + 1;

    try {
      wx.setStorageSync('stars', app.globalData.stars);
      wx.setStorageSync('clonedVoices', app.globalData.clonedVoices);
    } catch (e) {}

    const relationKey = this._getDefaultRelationByParent(this.data.parentType);
    const preset = this._getPresetByKey(relationKey);
    const finalName = String((voice && (voice.name || voice.voice_id)) || preset.quickName || '专属音色');
    this.setData({
      isGenerating: false,
      step: 4,
      selectedVoiceName: finalName,
      trainedVoiceId: String((voice && voice.voice_id) || ''),
      voiceNameInput: finalName,
      selectedRelationKey: relationKey
    });
    this._clearCloneDraft();
    wx.vibrateShort();
  },

  _resolveInitialVoiceName() {
    const key = String(this.data.selectedRelationKey || this._getDefaultRelationByParent(this.data.parentType)).trim();
    if (key === 'custom') {
      const custom = String(this.data.customRoleName || '').trim();
      return custom || '';
    }
    const preset = this._getPresetByKey(key);
    return String((preset && preset.label) || '').trim();
  },

  _checkModelName(modelName) {
    const base = getApiBase();
    const n = String(modelName || '').trim();
    if (!n) return Promise.resolve({ exists: false, conflict_info: [] });
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${base}/train/check_model_name?model_name=${encodeURIComponent(n)}`,
        method: 'GET',
        success: (res) => {
          const data = (res && res.data) || {};
          if (res.statusCode === 200 && Number(data.code) === 200) {
            resolve({ exists: !!data.exists, conflict_info: data.conflict_info || [] });
            return;
          }
          reject(new Error(data.message || '名称检查失败'));
        },
        fail: (err) => reject(this._wrapNetworkError(err, '名称检查失败')),
      });
    });
  },

  _buildScienceNarrationText(tipText, withIntro = false) {
    const tip = String(tipText || '').trim();
    if (!tip) return SCIENCE_INTRO_PREFIX;
    return withIntro ? `${SCIENCE_INTRO_PREFIX}${tip}` : tip;
  },

  _prepareScienceTips() {
    const base = getApiBase();
    return new Promise((resolve) => {
      wx.request({
        url: `${base}/train/science_tips?count=12`,
        method: 'GET',
        success: (res) => {
          const data = (res && res.data) || {};
          const tips = Array.isArray(data.tips) ? data.tips.map((x) => String((x && x.text) || '').trim()).filter(Boolean) : [];
          const finalTips = tips.length ? tips : SCIENCE_FALLBACK_TIPS.slice();
          this.setData({
            scienceTips: finalTips,
            scienceTipIndex: 0,
            scienceTipText: this._buildScienceNarrationText(finalTips[0] || ''),
            scienceMascotImage: pickScienceMascotImage(),
          });
          this._scienceIntroSpoken = false;
          this._saveCloneDraft();
          resolve();
        },
        fail: () => {
          const finalTips = SCIENCE_FALLBACK_TIPS.slice();
          this.setData({
            scienceTips: finalTips,
            scienceTipIndex: 0,
            scienceTipText: this._buildScienceNarrationText(finalTips[0] || ''),
            scienceMascotImage: pickScienceMascotImage(),
          });
          this._saveCloneDraft();
          resolve();
        },
      });
    });
  },

  _startScienceNarration() {
    this._stopScienceNarration();
    if (!this._canNarrateScience()) return;
    if (!this.data.scienceTips || !this.data.scienceTips.length) return;
    this._scienceIntroSpoken = false;
    this._nextScienceTip(true);
  },

  _canNarrateScience() {
    return !!(this._pageVisible && this.data.isGenerating);
  },

  _scheduleNextScienceTip() {
    if (!this._canNarrateScience()) return;
    if (this._scienceTimer) clearTimeout(this._scienceTimer);
    this._scienceTimer = setTimeout(() => {
      if (!this._canNarrateScience()) return;
      this._nextScienceTip(false);
    }, Math.max(1200, SCIENCE_SWITCH_SECONDS * 1000));
  },

  _stopScienceNarration() {
    if (this._scienceTimer) {
      clearTimeout(this._scienceTimer);
      this._scienceTimer = null;
    }
    try {
      if (this.data.scienceAudioContext) this.data.scienceAudioContext.stop();
    } catch (e) {}
    this.setData({ isScienceSpeaking: false });
  },

  _nextScienceTip(forceFirst) {
    if (!this._canNarrateScience()) return;
    const tips = this.data.scienceTips || [];
    if (!tips.length) return;
    let idx = Number(this.data.scienceTipIndex || 0);
    if (!forceFirst) idx = (idx + 1) % tips.length;
    const text = tips[idx] || '';
    const narratedText = this._buildScienceNarrationText(text, !this._scienceIntroSpoken);
    this._scienceIntroSpoken = true;
    const img = pickScienceMascotImage();
    this.setData({
      scienceTipIndex: idx,
      scienceTipText: narratedText,
      scienceMascotImage: img,
    });
    this._saveCloneDraft();
    this._playScienceTipAudio(narratedText);
  },
  _playScienceTipAudio(text) {
    if (!this._canNarrateScience()) return;
    const t = String(text || '').trim();
    const ac = this.data.scienceAudioContext;
    if (!t || !ac) return;

    const base = getApiBase().replace(/\/+$/, '');

    if (typeof ac.offEnded === 'function') ac.offEnded();
    if (typeof ac.offError === 'function') ac.offError();
    try { ac.stop(); } catch (e) {}

    this.setData({ isScienceSpeaking: true });
    ac.onEnded(() => {
      this.setData({ isScienceSpeaking: false });
      if (!this._canNarrateScience()) return;
      this._scheduleNextScienceTip();
    });
    ac.onError(() => {
      this.setData({ isScienceSpeaking: false });
      if (!this._canNarrateScience()) return;
      this._scheduleNextScienceTip();
    });

    wx.request({
      url: `${base}/readalong/tts?text=${encodeURIComponent(t)}`,
      method: 'GET',
      timeout: 45000,
      success: (res) => {
        if (!this._canNarrateScience()) {
          this.setData({ isScienceSpeaking: false });
          return;
        }
        const data = (res && res.data) || {};
        const audioUrlRaw = String(data.audio_url || '').trim();
        if (!audioUrlRaw) {
          this.setData({ isScienceSpeaking: false });
          return;
        }
        const audioUrl = /^https?:\/\//i.test(audioUrlRaw)
          ? audioUrlRaw
          : (audioUrlRaw.startsWith('/') ? `${base}${audioUrlRaw}` : `${base}/${audioUrlRaw}`);
        ac.src = audioUrl;
        ac.play();
      },
      fail: () => {
        this.setData({ isScienceSpeaking: false });
        if (!this._canNarrateScience()) return;
        this._scheduleNextScienceTip();
      },
    });
  },

  _saveCloneDraft() {
    const draft = {
      step: this.data.step,
      parentType: this.data.parentType,
      selectedRelationKey: this.data.selectedRelationKey,
      customRoleName: this.data.customRoleName,
      sentenceIdx: this.data.sentenceIdx,
      currentSentence: this.data.currentSentence,
      recordFiles: this.data.recordFiles,
      canGenerate: this.data.canGenerate,
      isGenerating: this.data.isGenerating,
      trainingTaskId: this.data.trainingTaskId,
      trainingMessage: this.data.trainingMessage,
      trainingVoiceName: this.data.trainingVoiceName,
      progress: this.data.progress,
      circleOffset: this.data.circleOffset,
      trainedVoiceId: this.data.trainedVoiceId,
      selectedVoiceName: this.data.selectedVoiceName,
      voiceNameInput: this.data.voiceNameInput,
      scienceTips: this.data.scienceTips,
      scienceTipIndex: this.data.scienceTipIndex,
      scienceTipText: this.data.scienceTipText,
      scienceMascotImage: this.data.scienceMascotImage,
      savedAt: Date.now(),
    };
    try { wx.setStorageSync(VOICE_CLONE_DRAFT_KEY, draft); } catch (e) {}
  },

  _clearCloneDraft() {
    try { wx.removeStorageSync(VOICE_CLONE_DRAFT_KEY); } catch (e) {}
  },

  _tryRestoreDraftOnEnter() {
    this._restorePrompted = true;
    let draft = null;
    try { draft = wx.getStorageSync(VOICE_CLONE_DRAFT_KEY); } catch (e) {}
    if (!draft || typeof draft !== 'object') return;

    const ageMs = Date.now() - Number(draft.savedAt || 0);
    if (ageMs > 24 * 60 * 60 * 1000) {
      this._clearCloneDraft();
      return;
    }

    const hasUsefulState = Number(draft.step || 1) > 1 || (Array.isArray(draft.recordFiles) && draft.recordFiles.some(Boolean));
    if (!hasUsefulState) return;

    wx.showModal({
      title: '继续上次克隆进度？',
      content: '检测到你上次离开前的克隆进度，是否回到上次进行到的步骤？',
      confirmText: '继续',
      cancelText: '重新开始',
      success: (res) => {
        if (!(res && res.confirm)) {
          this._clearCloneDraft();
          return;
        }
        const restoredRecordFiles = normalizeRecordFiles(draft.recordFiles);
        const restoredCanGenerate = countRecordedSentences(restoredRecordFiles) >= MIN_TRAIN_SENTENCE_COUNT
          && restoredRecordFiles.every(Boolean);

        this.setData({
          step: Number(draft.step || 1),
          parentType: String(draft.parentType || 'mom'),
          selectedRelationKey: String(draft.selectedRelationKey || 'mom'),
          customRoleName: String(draft.customRoleName || ''),
          sentenceIdx: Math.max(0, Math.min(Number(draft.sentenceIdx || 0), SENTENCES.length - 1)),
          currentSentence: String(draft.currentSentence || SENTENCES[0]),
          recordFiles: restoredRecordFiles,
          canGenerate: restoredCanGenerate,
          isGenerating: !!draft.isGenerating,
          trainingTaskId: String(draft.trainingTaskId || ''),
          trainingMessage: String(draft.trainingMessage || ''),
          trainingVoiceName: String(draft.trainingVoiceName || ''),
          progress: Number(draft.progress || 0),
          circleOffset: Number(draft.circleOffset || 351.858),
          trainedVoiceId: String(draft.trainedVoiceId || ''),
          selectedVoiceName: String(draft.selectedVoiceName || '基础音色（默认）'),
          voiceNameInput: String(draft.voiceNameInput || ''),
          scienceTips: Array.isArray(draft.scienceTips) ? draft.scienceTips : [],
          scienceTipIndex: Number(draft.scienceTipIndex || 0),
          scienceTipText: String(draft.scienceTipText || ''),
          scienceMascotImage: normalizeDraftAssetImage(draft.scienceMascotImage),
        });

        if (draft.isGenerating && draft.trainingTaskId) {
          this._resumeTrainingFromDraft();
        }
      },
    });
  },

  async _resumeTrainingFromDraft() {
    const taskId = String(this.data.trainingTaskId || '').trim();
    if (!taskId) return;
    this.setData({ step: 3, isGenerating: true });
    this._maybeShowTrainingEggGuide();
    await this._prepareScienceTips();
    this._startScienceNarration();
    try {
      if (app && typeof app.startGlobalTrainingWatch === 'function') {
        app.startGlobalTrainingWatch({
          taskId,
          voiceName: this.data.trainingVoiceName || this._resolveInitialVoiceName(),
          source: 'voice_page_resume'
        });
      }
      const doneInfo = await this._pollTrainStatus(taskId);
      const voice = await this._resolveTrainedVoice(doneInfo, this.data.trainingVoiceName || this._resolveInitialVoiceName());
      if (!voice || !voice.voice_id) throw new Error('训练完成但未找到音色');
      await this._setGlobalVoice(voice.voice_id, voice.name || voice.voice_id);
      this.completeTraining(voice);
    } catch (err) {
      this._stopScienceNarration();
      if (app && typeof app.clearGlobalTrainingWatch === 'function') {
        app.clearGlobalTrainingWatch({ silent: true });
      }
      this.setData({ isGenerating: false, step: 2 });
      wx.showToast({ title: (err && err.message) || '恢复训练失败', icon: 'none' });
    }
  },

  _isFirstTrainingGuideNeeded() {
    let guideShown = false;
    try { guideShown = !!wx.getStorageSync(FIRST_TRAIN_EGG_GUIDE_KEY); } catch (e) {}
    return !guideShown;
  },

  _maybeShowTrainingEggGuide() {
    if (!this.data.isGenerating && this.data.step !== 3) return;
    this.setData({ showTrainingEggGuide: true });
  },

  _hideTrainingEggGuide() {
    if (!this.data.showTrainingEggGuide) return;
    this.setData({ showTrainingEggGuide: false });
  },

  onTapTrainingEggGuide() {
    try { wx.setStorageSync(FIRST_TRAIN_EGG_GUIDE_KEY, 1); } catch (e) {}
    this._hideTrainingEggGuide();
    wx.navigateTo({ url: '/pages/pet-system/pet-system' });
  },

  goVoiceManager() {
    wx.navigateTo({ url: '/pages/voice-manage/voice-manage' });
  },

  goToBooks() {
    wx.switchTab({ url: '/pages/books/books' });
  },

  initVoiceGuide() {
    if (!isMainDone("homeDone")) return;
    if (isMainDone("voiceDone")) return;
    const steps = [
      {
        highlight: 'role',
        title: '先选择声音角色',
        desc: '可以选择妈妈、爸爸或自定义称呼，再开始录音采集。',
      },
      {
        highlight: 'record',
        title: '按步骤完成4个阶段',
        desc: '录音采集 -> 素材确认 -> 训练进度 -> 命名与应用。',
      },
      {
        highlight: 'name',
        title: '最后保存并应用音色',
        desc: '点“保存并应用”后，此阶段引导自动完成。',
      },
    ];
    this.setData({
      showGuide: true,
      guideSteps: steps,
      guideStepIndex: 0,
    });
    this.updateGuideStep();
  },

  updateGuideStep() {
    const list = Array.isArray(this.data.guideSteps) ? this.data.guideSteps : [];
    const idx = Number(this.data.guideStepIndex || 0);
    const cur = list[idx];
    if (!cur) {
      this.closeGuide();
      return;
    }
    this.setData({
      guideHighlight: String(cur.highlight || ''),
      guideTitle: String(cur.title || ''),
      guideDesc: String(cur.desc || ''),
    });
  },

  onGuideNext() {
    const next = Number(this.data.guideStepIndex || 0) + 1;
    if (next >= (this.data.guideSteps || []).length) {
      this.closeGuide();
      return;
    }
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
