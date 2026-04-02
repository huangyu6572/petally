// pages/promotion/coupon/index.js
// NOTE: This page uses a local coupon list stored from claim responses.
// A dedicated /coupons GET endpoint can be added later for full server-side listing.
const { promotionApi } = require('../../../services/api');

Page({
  data: {
    status: 'active',
    coupons: [],
    loading: false,
  },

  onLoad() {
    this.loadCoupons();
  },

  setStatus(e) {
    const s = e.currentTarget.dataset.status;
    if (s === this.data.status) return;
    this.setData({ status: s, coupons: [] });
    this.loadCoupons();
  },

  loadCoupons() {
    // Load coupon list from storage (populated on claim)
    // or from a future /coupons API endpoint
    this.setData({ loading: true });
    const stored = wx.getStorageSync('user_coupons') || [];
    const filtered = stored.filter(c => c.status === this.data.status);
    this.setData({ coupons: filtered, loading: false });
  },

  goToList() {
    wx.switchTab({ url: '/pages/promotion/list/index' });
  },
});
