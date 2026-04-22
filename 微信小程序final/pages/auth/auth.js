const app = getApp();
const { markMainDone, isMainDone } = require("../../utils/guide-flow.js");
const { resolveApiBase } = require("../../utils/api-base.js");

const MASCOT_URL = "https://images.unsplash.com/photo-1772371272174-392cf9cfabae?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=400";

function authApiBase() {
  return resolveApiBase(app);
}

function isValidCnMobile(s) {
  return /^1[3-9]\d{9}$/.test(String(s || "").trim());
}

function isValidEmail(s) {
  const t = String(s || "").trim();
  if (!t || t.length > 120 || !t.includes("@")) return false;
  return /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/.test(t);
}

function isStrongPassword(p) {
  const s = String(p || "");
  return s.length >= 8 && /[A-Za-z]/.test(s) && /\d/.test(s);
}

function detailMsg(body) {
  const b = body || {};
  const d = b.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d
      .map((x) => (x && (x.msg || x.message)) || "")
      .filter(Boolean)
      .join(",");
  }
  return b.message ? String(b.message) : "";
}

function applyTokenAndUser(token, user) {
  const t = String(token || "").trim();
  const u = user && typeof user === "object" ? user : {};
  const userId = String(u.user_id || u.openid || "").trim();
  if (!t || !userId) return false;
  app.globalData.authToken = t;
  app.globalData.user_id = userId;
  app.globalData.openid = String(u.openid || "").trim();
  app.globalData.unionid = String(u.unionid || "").trim();
  app.globalData.isLoggedIn = true;
  app.saveData("authToken", t);
  app.saveData("user_id", userId);
  app.saveData("openid", app.globalData.openid);
  app.saveData("unionid", app.globalData.unionid);
  app.saveData("isLoggedIn", true);
  return true;
}

Page({
  data: {
    mode: "login",
    isLoggedIn: false,
    userData: {},
    stars: 0,
    level: 1,
    levelTitle: "初级读者",
    booksRead: 0,
    clonedVoices: 0,
    coloringWorks: 0,
    mascotUrl: MASCOT_URL,
    showGuide: false,
    guideSteps: [],
    guideStepIndex: 0,
    guideHighlight: "",
    guideTitle: "",
    guideDesc: "",
    showFirstVisitHint: false,
    nudgeRegisterTab: false,
    showForgotPassword: false,
    forgotAccount: "",
    forgotPassword: "",
    forgotPwd2: "",
  },

  onLoad() {
    this.checkLoginStatus();
  },

  onShow() {
    this.checkLoginStatus();
    this.initAuthGuide();
  },

  checkLoginStatus() {
    const globalData = app.globalData;
    const isLoggedIn = globalData.isLoggedIn;

    if (isLoggedIn) {
      const levelInfo = app.calculateLevel(globalData.stars);
      this.setData({
        isLoggedIn: true,
        userData: globalData.userData,
        stars: globalData.stars,
        level: levelInfo.level,
        levelTitle: levelInfo.title,
        booksRead: globalData.booksRead,
        clonedVoices: globalData.clonedVoices,
        coloringWorks: globalData.coloringWorks,
        showFirstVisitHint: false,
        nudgeRegisterTab: false,
      });
    } else {
      let ever = false;
      try {
        ever = !!wx.getStorageSync("ever_logged_in_ok");
      } catch (e) {}
      const firstTime = !ever;
      this.setData({
        isLoggedIn: false,
        mode: firstTime ? "register" : "login",
        showFirstVisitHint: firstTime,
        nudgeRegisterTab: firstTime,
      });
    }
  },

  switchToLogin() {
    this.setData({ mode: "login", showFirstVisitHint: false, nudgeRegisterTab: false });
  },

  switchToRegister() {
    this.setData({ mode: "register", nudgeRegisterTab: false });
  },

  openForgotPassword() {
    this.setData({
      showForgotPassword: true,
      forgotAccount: "",
      forgotPassword: "",
      forgotPwd2: "",
    });
  },

  closeForgotPassword() {
    this.setData({ showForgotPassword: false });
  },

  preventForgotTouchMove() {
    return false;
  },

  preventForgotBubble() {},

  onForgotAccountInput(e) {
    this.setData({ forgotAccount: (e.detail && e.detail.value) || "" });
  },

  onForgotPwdInput(e) {
    this.setData({ forgotPassword: (e.detail && e.detail.value) || "" });
  },

  onForgotPwd2Input(e) {
    this.setData({ forgotPwd2: (e.detail && e.detail.value) || "" });
  },

  onPhoneForReset(e) {
    const detail = (e && e.detail) || {};
    if (!detail.code) {
      const err = String(detail.errMsg || "");
      if (err.indexOf("deny") >= 0 || err.indexOf("cancel") >= 0) {
        wx.showToast({ title: "已取消授权", icon: "none" });
      } else if (err) {
        wx.showToast({ title: "需要授权手机号才能重置", icon: "none" });
      }
      return;
    }
    const account = String(this.data.forgotAccount || "").trim();
    const p1 = String(this.data.forgotPassword || "");
    const p2 = String(this.data.forgotPwd2 || "");
    if (!isValidCnMobile(account)) {
      wx.showToast({ title: "请填写注册时的11位手机号", icon: "none" });
      return;
    }
    if (!isStrongPassword(p1)) {
      wx.showToast({ title: "新密码至少8位且含字母与数字", icon: "none" });
      return;
    }
    if (p1 !== p2) {
      wx.showToast({ title: "两次输入的新密码不一致", icon: "none" });
      return;
    }
    wx.showLoading({ title: "提交中…", mask: true });
    const resetPayload = JSON.stringify({
      account,
      new_password: p1,
      phone_code: detail.code,
    });
    wx.request({
      url: `${authApiBase()}/auth/password/reset`,
      method: "POST",
      header: { "Content-Type": "application/json" },
      data: resetPayload,
      success: (res) => {
        wx.hideLoading();
        const body = (res && res.data) || {};
        if (res.statusCode !== 200 || Number(body.code) !== 0) {
          const msg =
            detailMsg(body) ||
            (res.statusCode === 404 ? "该手机号尚未注册" : "") ||
            (res.statusCode === 503 ? "服务端连不上微信，请检查网络或后台配置" : "") ||
            "重置失败";
          const full = String(msg || "重置失败");
          if (full.length > 20) {
            wx.showModal({
              title: "重置密码失败",
              content: full,
              showCancel: false,
              confirmColor: "#e879a9",
            });
          } else {
            wx.showToast({ title: full, icon: "none" });
          }
          return;
        }
        wx.showToast({ title: "密码已重置，请登录", icon: "success" });
        this.setData({
          showForgotPassword: false,
          mode: "login",
          forgotAccount: "",
          forgotPassword: "",
          forgotPwd2: "",
        });
      },
      fail: () => {
        wx.hideLoading();
        wx.showToast({ title: "网络错误", icon: "none" });
      },
    });
  },

  onFirstVisitHintTap() {
    this.setData({ mode: "register", showFirstVisitHint: false, nudgeRegisterTab: false });
  },

  finishAuthUi(mode) {
    try {
      wx.setStorageSync("ever_logged_in_ok", true);
    } catch (e) {}
    // 须立即写入，避免用户立刻切到首页时 initHomeGuide 因 authDone 仍为 false 而不弹出
    markMainDone("authDone");
    wx.showToast({
      title: mode === "register" ? "注册成功！" : "登录成功！",
      icon: "success",
    });
    
    setTimeout(() => {
      this.closeGuide();
      this.checkLoginStatus();
    }, 400);
  },

  _afterProfileLoaded(mode) {
    try {
      wx.setStorageSync("isLoggedIn", true);
      wx.setStorageSync("userData", app.globalData.userData);
    } catch (e) {}
    if (typeof app.refreshVoiceList === "function") {
      app.refreshVoiceList();
    }
    this.finishAuthUi(mode);
  },

  handleSubmit(e) {
    const formData = e.detail.value || {};
    const { mode } = this.data;
    const account = String(formData.account || "").trim();
    const password = String(formData.password || "");

    if (!isValidCnMobile(account) && !isValidEmail(account)) {
      wx.showToast({
        title: "请填写大陆11位手机号或有效邮箱",
        icon: "none",
      });
      return;
    }

    if (mode === "register") {
      const babyName = String(formData.babyName || "").trim();
      if (!babyName) {
        wx.showToast({ title: "请填写宝宝昵称", icon: "none" });
        return;
      }
      if (!isStrongPassword(password)) {
        wx.showToast({
          title: "密码至少8位且含字母与数字",
          icon: "none",
        });
        return;
      }
      app.globalData.userData.babyName = babyName;
      const regPayload = JSON.stringify({
        account,
        password,
        baby_name: babyName,
        nickname: babyName,
      });
      wx.request({
        url: `${authApiBase()}/auth/register/password`,
        method: "POST",
        header: { "Content-Type": "application/json" },
        data: regPayload,
        success: (res) => {
          const body = (res && res.data) || {};
          if (res.statusCode === 409) {
            let tip = detailMsg(body);
            if (!tip) {
              tip = isValidCnMobile(account)
                ? "当前手机号已经注册，请直接登录"
                : "该邮箱已注册，请直接登录";
            }
            wx.showModal({
              title: "提示",
              content: tip,
              confirmText: "去登录",
              cancelText: "取消",
              confirmColor: "#e879a9",
              success: (r) => {
                if (r.confirm) {
                  this.switchToLogin();
                }
              },
            });
            return;
          }
          if (res.statusCode !== 200 || Number(body.code) !== 0) {
            const msg = detailMsg(body) || body.message || "注册失败";
            wx.showToast({ title: String(msg).slice(0, 36), icon: "none" });
            return;
          }
          const token = String(body.token || "").trim();
          const user = body.user || {};
          if (!applyTokenAndUser(token, user)) {
            wx.showToast({ title: "注册数据异常", icon: "none" });
            return;
          }
          if (typeof app.resetProgressForNewLoginUser === "function") {
            app.resetProgressForNewLoginUser(app.getUserId());
          }
          app.fetchMyProfile((err) => {
            if (err) {
              wx.showToast({ title: "已注册，拉取资料失败", icon: "none" });
              this._afterProfileLoaded("register");
              return;
            }
            this._afterProfileLoaded("register");
          });
        },
        fail: () => {
          wx.showToast({ title: "网络错误，请重试", icon: "none" });
        },
      });
      return;
    }

    // 登录：账号 + 密码
    if (!password) {
      wx.showToast({ title: "请输入密码", icon: "none" });
      return;
    }
    wx.request({
      url: `${authApiBase()}/auth/login/password`,
      method: "POST",
      header: { "Content-Type": "application/json" },
      data: { account, password },
      success: (res) => {
        const body = (res && res.data) || {};
        if (res.statusCode === 401 || res.statusCode === 400) {
          wx.showToast({
            title: "账号或密码错误，或未设置密码可试微信登录",
            icon: "none",
          });
          return;
        }
        if (res.statusCode !== 200 || Number(body.code) !== 0) {
          const msg = detailMsg(body) || "登录失败";
          wx.showToast({ title: String(msg).slice(0, 36), icon: "none" });
          return;
        }
        const token = String(body.token || "").trim();
        const user = body.user || {};
        if (!applyTokenAndUser(token, user)) {
          wx.showToast({ title: "登录数据异常", icon: "none" });
          return;
        }
        if (typeof app.resetProgressForNewLoginUser === "function") {
          app.resetProgressForNewLoginUser(app.getUserId());
        }
        app.fetchMyProfile((err) => {
          if (err) {
            wx.showToast({ title: "已登录，拉取资料失败", icon: "none" });
            this._afterProfileLoaded("login");
            return;
          }
          this._afterProfileLoaded("login");
        });
      },
      fail: () => {
        wx.showToast({ title: "网络错误，请重试", icon: "none" });
      },
    });
  },

  /** 微信一键注册/登录：沿用旧逻辑，直接走 /auth/wechat/login。 */
  handleWechatLogin() {
    wx.showLoading({ title: "登录中…", mask: true });
    app.loginWithWechat((err) => {
      wx.hideLoading();
      if (err) {
        const msg = String((err && err.message) || "微信登录失败");
        wx.showModal({
          title: "微信登录失败",
          content: msg,
          showCancel: false,
          confirmColor: "#e879a9",
        });
        return;
      }
      if (typeof app.resetProgressForNewLoginUser === "function") {
        app.resetProgressForNewLoginUser(app.getUserId());
      }
      app.fetchMyProfile(() => {
        try {
          wx.setStorageSync("ever_logged_in_ok", true);
          wx.setStorageSync("isLoggedIn", true);
          wx.setStorageSync("userData", app.globalData.userData);
        } catch (e2) {}
        if (typeof app.refreshVoiceList === "function") {
          app.refreshVoiceList();
        }
        wx.showToast({ title: "登录成功", icon: "success" });
        wx.vibrateShort();
        markMainDone("authDone");
        setTimeout(() => {
          this.closeGuide();
          this.checkLoginStatus();
        }, 400);
      });
    });
  },

  handleLogout() {
    wx.showModal({
      title: "确认退出",
      content: "确定要退出登录吗？",
      confirmColor: "#e879a9",
      success: (res) => {
        if (res.confirm) {
          if (typeof app.clearLoginSession === "function") {
            app.clearLoginSession();
          } else {
            app.globalData.isLoggedIn = false;
            app.globalData.authToken = "";
            try {
              wx.setStorageSync("isLoggedIn", false);
              wx.setStorageSync("authToken", "");
            } catch (e) {
              console.log("保存失败", e);
            }
          }
          wx.showToast({
            title: "已退出登录",
            icon: "success",
          });
          this.setData({
            isLoggedIn: false,
            mode: "login",
            showFirstVisitHint: false,
            nudgeRegisterTab: false,
          });
          if (typeof app.refreshVoiceList === "function") {
            app.refreshVoiceList();
          }
        }
      },
    });
  },

  handleClearData() {
    wx.showModal({
      title: "⚠️ 警告",
      content: "确定要清除所有数据吗？这将重置为新用户状态。",
      confirmText: "确认清除",
      confirmColor: "#ef4444",
      success: (res) => {
        if (res.confirm) {
          try {
            wx.clearStorageSync();
            app.initGlobalData();
            wx.showToast({
              title: "数据已清除",
              icon: "success",
            });
            setTimeout(() => {
              wx.reLaunch({
                url: "/pages/home/home",
              });
            }, 1000);
          } catch (e) {
            console.log("清除失败", e);
            wx.showToast({
              title: "清除失败",
              icon: "error",
            });
          }
        }
      },
    });
  },

  goToProfileEdit() {
    wx.navigateTo({
      url: "/pages/profile-edit/profile-edit",
    });
  },

  goToFavorites() {
    wx.navigateTo({
      url: "/pages/my-favorites/my-favorites",
    });
  },

  goToVoice() {
    wx.switchTab({
      url: "/pages/voice/voice",
    });
  },

  goToGrowth() {
    wx.navigateTo({
      url: "/pages/growth/growth",
    });
  },

  goToNotification() {
    wx.showToast({
      title: "功能开发中",
      icon: "none",
    });
  },

  initAuthGuide() {
    if (this.data.isLoggedIn) return;
    if (isMainDone("authDone")) return;
    const steps = [
      {
        highlight: "tab",
        title: "新用户请先注册",
        desc: "首次使用建议点「注册」完成手机号或邮箱注册。微信登录需点底部按钮并授权手机号，将登录到已注册的同一账号。",
      },
      {
        highlight: "submit",
        title: "完成后进入主线",
        desc: "提交成功或微信登录成功后会进入个人中心，成长与音色将随账号保存。",
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
      guideHighlight: String(cur.highlight || ""),
      guideTitle: String(cur.title || ""),
      guideDesc: String(cur.desc || ""),
    });
  },

  onGuideNext() {
    const nextIdx = Number(this.data.guideStepIndex || 0) + 1;
    if (nextIdx >= (this.data.guideSteps || []).length) {
      this.closeGuide();
      return;
    }
    this.setData({ guideStepIndex: nextIdx }, () => this.updateGuideStep());
  },

  closeGuide() {
    this.setData({
      showGuide: false,
      guideSteps: [],
      guideStepIndex: 0,
      guideHighlight: "",
      guideTitle: "",
      guideDesc: "",
    });
  },

  noop() {},
});
