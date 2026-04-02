// pages/index/index.js
const { promotionApi } = require('../../services/api');

Page({
  data: {
    recentPromotions: [],
  },

  onLoad() {
    const app = getApp();
    app.requireLogin(() => {
      this.loadRecentPromotions();
    });
  },

  onShow() {
    // Tab 切换回首页也刷新
    if (this.data.recentPromotions.length === 0) {
      this.loadRecentPromotions();
    }
  },

  loadRecentPromotions() {
    promotionApi.getList(1, 5).then(res => {
      if (res && res.data && res.data.items) {
        this.setData({ recentPromotions: res.data.items });
      }
    }).catch(() => {
      // 静默失败，首页不强制提示
    });
  },

  goToAntiFake() {
    wx.switchTab({ url: '/pages/anti-fake/scan/index' });
  },

  goToSkin() {
    wx.switchTab({ url: '/pages/skin/capture/index' });
  },

  goToPromotion() {
    wx.switchTab({ url: '/pages/promotion/list/index' });
  },

  goToPromoDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/promotion/detail/index?id=${id}` });
  },
});
