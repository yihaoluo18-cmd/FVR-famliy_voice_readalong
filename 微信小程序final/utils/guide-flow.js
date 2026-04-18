const GUIDE_STORAGE_KEY = "demoGuideState.v1";
const GUIDE_VERSION = "1.0.0";

function _defaultState() {
  return {
    version: GUIDE_VERSION,
    main: {
      authDone: false,
      homeDone: false,
      voiceDone: false,
      readDone: false,
      playDone: false,
    },
  };
}

function getGuideState() {
  const base = _defaultState();
  try {
    const raw = wx.getStorageSync(GUIDE_STORAGE_KEY);
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return base;
    const main = raw.main && typeof raw.main === "object" ? raw.main : {};
    return {
      version: GUIDE_VERSION,
      main: {
        authDone: !!main.authDone,
        homeDone: !!main.homeDone,
        voiceDone: !!main.voiceDone,
        readDone: !!main.readDone,
        playDone: !!main.playDone,
      },
    };
  } catch (e) {
    return base;
  }
}

function saveGuideState(state) {
  const next = state && typeof state === "object" ? state : _defaultState();
  try {
    wx.setStorageSync(GUIDE_STORAGE_KEY, next);
  } catch (e) {}
  return next;
}

function markMainDone(key) {
  const state = getGuideState();
  if (!state.main || typeof state.main !== "object") state.main = _defaultState().main;
  if (!Object.prototype.hasOwnProperty.call(state.main, key)) return state;
  state.main[key] = true;
  return saveGuideState(state);
}

function isMainDone(key) {
  const state = getGuideState();
  return !!(state.main && state.main[key]);
}

module.exports = {
  GUIDE_VERSION,
  GUIDE_STORAGE_KEY,
  getGuideState,
  saveGuideState,
  markMainDone,
  isMainDone,
};
