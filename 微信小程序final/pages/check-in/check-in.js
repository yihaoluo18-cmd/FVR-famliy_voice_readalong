const app = getApp();
const { reportEggProgress, yearMonthKey } = require("../../utils/pet-growth.js");

// 奖励配置
const REWARDS = [
  { days: 3, stars: 10, icon: '🎁' },
  { days: 7, stars: 30, icon: '🎉' },
  { days: 15, stars: 60, icon: '🏆' },
  { days: 30, stars: 100, icon: '👑' },
];

Page({
  data: {
    currentMonth: '2026年3月',
    currentDay: 15,
    daysInMonth: 31,
    
    // 签到数据
    stars: 0,
    consecutiveDays: 0,
    totalCheckIns: 0,
    todayCheckedIn: false,
    
    // 日历
    calendarDays: [],
    
    // 奖励
    rewards: [],
    
    // 特效
    showConfetti: false,
  },

  onLoad() {
    this.loadData();
    this.generateCalendar();
    this.loadRewards();
  },

  onShow() {
    this.loadData();
    this.generateCalendar();
    this.loadRewards();
    reportEggProgress("checkin_month_sync", {
      total_check_ins_this_month: app.globalData.totalCheckInsThisMonth || 0,
      year_month: yearMonthKey(),
    }).catch(() => {});
  },

  // 加载数据
  loadData() {
    const globalData = app.globalData;
    
    // 获取今天的日期
    const today = new Date();
    const currentDay = today.getDate();
    const currentMonth = `${today.getFullYear()}年${today.getMonth() + 1}月`;
    
    // 检查今日是否已签到
    const lastCheckInDate = globalData.lastCheckInDate || '';
    const todayStr = today.toDateString();
    const todayCheckedIn = lastCheckInDate === todayStr;

    this.setData({
      currentMonth: currentMonth,
      currentDay: currentDay,
      stars: globalData.stars,
      consecutiveDays: globalData.consecutiveDays || 0,
      totalCheckIns: globalData.totalCheckInsThisMonth || 0,
      todayCheckedIn: todayCheckedIn,
    });
  },

  // 生成日历
  generateCalendar() {
    const { currentDay, daysInMonth } = this.data;
    const globalData = app.globalData;
    const checkInRecord = globalData.checkInRecord || {};
    
    const days = [];
    for (let i = 1; i <= daysInMonth; i++) {
      const isToday = i === currentDay;
      const isFuture = i > currentDay;
      const isChecked = isToday ? this.data.todayCheckedIn : !!checkInRecord[i];
      
      days.push({
        day: i,
        isToday,
        isFuture,
        isChecked,
      });
    }

    this.setData({
      calendarDays: days
    });
  },

  // 加载奖励
  loadRewards() {
    const globalData = app.globalData;
    const totalCheckIns = globalData.totalCheckInsThisMonth || 0;
    const rewardsClaimed = globalData.rewardsClaimed || {};

    const rewards = REWARDS.map(reward => {
      const canClaim = totalCheckIns >= reward.days && !rewardsClaimed[reward.days];
      const claimed = !!rewardsClaimed[reward.days];

      return {
        ...reward,
        canClaim,
        claimed,
      };
    });

    this.setData({
      rewards
    });
  },

  // 签到
  handleCheckIn() {
    if (this.data.todayCheckedIn) {
      wx.showToast({
        title: '今天已经签到啦',
        icon: 'none',
      });
      return;
    }

    // 执行签到
    const today = new Date();
    const todayStr = today.toDateString();
    const currentDay = this.data.currentDay;

    // 检查是否连续签到
    const lastCheckInDate = app.globalData.lastCheckInDate;
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const yesterdayStr = yesterday.toDateString();

    let consecutiveDays = app.globalData.consecutiveDays || 0;
    if (lastCheckInDate === yesterdayStr) {
      // 连续签到
      consecutiveDays += 1;
    } else if (lastCheckInDate !== todayStr) {
      // 不连续，重置为1
      consecutiveDays = 1;
    }

    // 更新数据
    const checkInRecord = app.globalData.checkInRecord || {};
    checkInRecord[currentDay] = true;

    app.globalData.lastCheckInDate = todayStr;
    app.globalData.consecutiveDays = consecutiveDays;
    app.globalData.totalCheckInsThisMonth = (app.globalData.totalCheckInsThisMonth || 0) + 1;
    app.globalData.checkInRecord = checkInRecord;
    if (app.addStars) app.addStars(2);

    // 保存到本地
    try {
      wx.setStorageSync('lastCheckInDate', todayStr);
      wx.setStorageSync('consecutiveDays', consecutiveDays);
      wx.setStorageSync('totalCheckInsThisMonth', app.globalData.totalCheckInsThisMonth);
      wx.setStorageSync('checkInRecord', checkInRecord);
    } catch (e) {
      console.log('保存失败', e);
    }

    // 显示成功提示
    wx.showToast({
      title: '签到成功 +2⭐',
      icon: 'success',
    });

    // 震动反馈
    wx.vibrateShort();

    // 显示彩带效果
    this.setData({
      showConfetti: true
    });

    setTimeout(() => {
      this.setData({
        showConfetti: false
      });
    }, 2000);

    // 刷新数据
    this.loadData();
    this.generateCalendar();
    this.loadRewards();

    reportEggProgress("checkin_completed", {
      consecutive_days: consecutiveDays,
      total_check_ins_this_month: app.globalData.totalCheckInsThisMonth || 0,
      year_month: yearMonthKey(),
    }).catch(() => {});
  },

  // 领取奖励
  claimReward(e) {
    const reward = e.currentTarget.dataset.reward;
    
    if (!reward.canClaim) {
      if (reward.claimed) {
        wx.showToast({
          title: '该奖励已领取',
          icon: 'none',
        });
      } else {
        wx.showToast({
          title: `还需签到${reward.days - this.data.totalCheckIns}天`,
          icon: 'none',
        });
      }
      return;
    }

    // 领取奖励
    const rewardsClaimed = app.globalData.rewardsClaimed || {};
    rewardsClaimed[reward.days] = true;
    app.globalData.rewardsClaimed = rewardsClaimed;
    if (app.addStars) app.addStars(reward.stars);

    // 保存到本地
    try {
      wx.setStorageSync('rewardsClaimed', rewardsClaimed);
    } catch (e) {
      console.log('保存失败', e);
    }

    wx.showToast({
      title: `领取成功 +${reward.stars}⭐`,
      icon: 'success',
    });

    // 震动反馈
    wx.vibrateShort();

    // 显示彩带效果
    this.setData({
      showConfetti: true
    });

    setTimeout(() => {
      this.setData({
        showConfetti: false
      });
    }, 2000);

    // 刷新数据
    this.loadData();
    this.loadRewards();
  },
});
