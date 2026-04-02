// pages/profile/index.js
Page({
  data: {
    userInfo: {},
    shortId: '',
    stats: {
      antiFakeCount: 0,
      skinCount: 0,
      couponCount: 0,
    },
  },

  onShow() {
    this._loadUserInfo();
    this._loadStats();
  },

  _loadUserInfo() {
    const app = getApp();
    const { userInfo } = app.globalData;
    if (userInfo) {
      const shortId = userInfo.id ? String(userInfo.id).slice(0, 8) : '—';
      this.setData({ userInfo, shortId });
    }
  },

  _loadStats() {
    const antiFakeHistory = wx.getStorageSync('anti_fake_count') || 0;
    const skinHistory = wx.getStorageSync('skin_analysis_count') || 0;
    const coupons = wx.getStorageSync('user_coupons') || [];
    const activeCoupons = coupons.filter(c => c.status === 'active').length;
    this.setData({
      stats: {
        antiFakeCount: antiFakeHistory,
        skinCount: skinHistory,
        couponCount: activeCoupons,
      },
    });
  },

  goToAntiFakeHistory() {
    wx.navigateTo({ url: '/pages/anti-fake/history/index' });
  },

  goToSkinHistory() {
    wx.navigateTo({ url: '/pages/skin/history/index' });
  },

  goToSkinTrend() {
    wx.navigateTo({ url: '/pages/skin/trend/index' });
  },

  goToCoupon() {
    wx.navigateTo({ url: '/pages/promotion/coupon/index' });
  },

  handleLogout() {
    wx.showModal({
      title: '确认退出',
      content: '退出后需要重新登录才能使用完整功能',
      confirmText: '退出',
      confirmColor: '#e74c3c',
      success: (res) => {
        if (res.confirm) {
          const app = getApp();
          wx.removeStorageSync('access_token');
          wx.removeStorageSync('refresh_token');
          wx.removeStorageSync('token_expire_at');
          app.globalData.isLoggedIn = false;
          app.globalData.userInfo = null;
          wx.reLaunch({ url: '/pages/login/index' });
        }
      },
    });
  },
});
