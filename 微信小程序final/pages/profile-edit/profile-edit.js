const app = getApp();
const { toMiniprogramAssetUrl } = require("../../utils/asset-url.js");

// 头像选项（使用在线图片链接）
const AVATAR_OPTIONS = [
  "https://images.unsplash.com/photo-1772371272174-392cf9cfabae?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=400",
  "/assets/images/kid4.png",
  "/assets/images/kid5.png",
  "/assets/images/kid7.png",
  "/assets/images/kid6.png",
  "/assets/images/kid1.png",
  "/assets/images/kid0.png",
  "/assets/images/kid2.png",
];

function buildAvatarOptions() {
  return AVATAR_OPTIONS.map((u) => (/^https?:\/\//i.test(u) ? u : toMiniprogramAssetUrl(u)));
}

/** 未上传头像时使用的默认图（与选择器第一项一致） */
function getDefaultAvatar() {
  const opts = buildAvatarOptions();
  return opts[0] || "";
}

function normalizeStoredAvatar(u) {
  const s = String(u || "").trim();
  if (!s) return s;
  if (/^https?:\/\//i.test(s)) return s;
  if (s.startsWith("/assets/")) return toMiniprogramAssetUrl(s);
  return s;
}

Page({
  data: {
    selectedAvatar: '',
    showAvatarPicker: false,
    avatarOptions: buildAvatarOptions(),
    
    formData: {
      parentName: '',
      babyName: '',
      babyAge: 3,
      email: '',
      phone: '',
    },
    
    ageOptions: ['2 岁', '3 岁', '4 岁', '5 岁', '6 岁', '7 岁'],
    ageIndex: 1,
  },

  onLoad() {
    this.loadUserData();
  },

  // 加载用户数据
  loadUserData() {
    const applyLocal = () => {
      const userData = app.globalData.userData;
      const ageIndex = this.data.ageOptions.findIndex(
        opt => parseInt(opt) === userData.babyAge
      );
      const parentName = String(userData.parentName || "").trim();
      let selectedAvatar = normalizeStoredAvatar(userData.avatar);
      if (!selectedAvatar) {
        selectedAvatar = getDefaultAvatar();
      }
      this.setData({
        selectedAvatar,
        formData: {
          parentName,
          babyName: userData.babyName,
          babyAge: userData.babyAge,
          email: userData.email,
          phone: userData.phone,
        },
        ageIndex: ageIndex >= 0 ? ageIndex : 1,
      });
    };
    app.fetchMyProfile((err) => {
      if (err) {
        applyLocal();
        return;
      }
      applyLocal();
    });
  },

  // 切换头像选择器
  toggleAvatarPicker() {
    this.setData({
      showAvatarPicker: !this.data.showAvatarPicker
    });
  },

  // 选择头像
  selectAvatar(e) {
    const url = e.currentTarget.dataset.url;
    this.setData({
      selectedAvatar: url,
      showAvatarPicker: false
    });

 
  },

  onParentNameInput(e) {
    this.setData({ 'formData.parentName': (e.detail && e.detail.value) || '' });
  },

  onBabyNameInput(e) {
    this.setData({ "formData.babyName": (e.detail && e.detail.value) || "" });
  },

  onEmailInput(e) {
    this.setData({ 'formData.email': (e.detail && e.detail.value) || '' });
  },

  onPhoneInput(e) {
    this.setData({ 'formData.phone': (e.detail && e.detail.value) || '' });
  },

  // 年龄改变
  onAgeChange(e) {
    const index = e.detail.value;
    const age = parseInt(this.data.ageOptions[index]);
    
    this.setData({
      ageIndex: index,
      'formData.babyAge': age
    });
  },

  // 保存修改
  handleSave(e) {
    const fd = (e && e.detail && e.detail.value) || {};
    const snap = this.data.formData || {};
    const parentName = String(
      fd.parentName !== undefined && fd.parentName !== null && String(fd.parentName).trim() !== ''
        ? fd.parentName
        : snap.parentName || ''
    ).trim();
    const babyName = String(
      fd.babyName !== undefined && fd.babyName !== null && String(fd.babyName).trim() !== ''
        ? fd.babyName
        : snap.babyName || ''
    ).trim();

    if (!parentName || !babyName) {
      wx.showToast({
        title: '请填写完整信息',
        icon: 'none',
      });
      return;
    }

    const em = String(
      fd.email !== undefined && fd.email !== null ? fd.email : snap.email || ''
    ).trim();
    const ph = String(
      fd.phone !== undefined && fd.phone !== null ? fd.phone : snap.phone || ''
    ).trim();

    let avatarOut = String(this.data.selectedAvatar || "").trim();
    if (!avatarOut) {
      avatarOut = getDefaultAvatar();
    }

    const payload = {
      avatar: avatarOut,
      parent_name: parentName,
      baby_name: babyName,
      baby_age: String(this.data.formData.babyAge || ''),
    };
    if (em) payload.email = em;
    if (ph) payload.phone = ph;

    app.updateMyProfile(payload, (err) => {
      if (err) {
        const raw = (err && err.message) ? String(err.message) : '保存失败，请重试';
        if (raw.indexOf('重新登录') >= 0 || raw.indexOf('失效') >= 0) {
          wx.showModal({
            title: '无法保存',
            content: raw,
            showCancel: false,
            confirmColor: '#e879a9',
          });
        } else {
          wx.showToast({
            title: raw.length > 36 ? raw.slice(0, 36) + '…' : raw,
            icon: 'none',
            duration: 3200,
          });
        }
        return;
      }
      try {
        wx.setStorageSync('userData', app.globalData.userData);
      } catch (e) {}
      wx.showModal({
        title: '✨ 资料保存成功！',
        content: '您的个人资料已更新',
        showCancel: false,
        confirmColor: '#e879a9',
        success: () => {
          wx.navigateBack();
        }
      });

    });
  },
});
