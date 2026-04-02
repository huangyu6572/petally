// pages/promotion/detail/index.js
const { promotionApi } = require('../../../services/api');

Page({
  data: {
    loading: true,
    detail: null,
    claiming: false,
    claimed: false,
  },

  onLoad(options) {
    this.promotionId = options.id;
    this.loadDetail();
  },

  loadDetail() {
    promotionApi.getDetail(this.promotionId)
      .then(res => {
        if (res && res.data) {
          this.setData({ detail: res.data, loading: false });
          promotionApi.track(this.promotionId, 'view', 'detail').catch(() => {});
        }
      })
      .catch(() => {
        this.setData({ loading: false });
        wx.showToast({ title: '加载失败', icon: 'none' });
      });
  },

  claimCoupon() {
    if (this.data.claiming || this.data.claimed) return;
    const app = getApp();
    app.requireLogin(() => {
      this.setData({ claiming: true });
      promotionApi.claimCoupon(this.promotionId)
        .then(() => {
          this.setData({ claiming: false, claimed: true });
          wx.showToast({ title: '领取成功！', icon: 'success' });
          wx.navigateTo({ url: `/pages/promotion/coupon/index` });
        })
        .catch(err => {
          this.setData({ claiming: false });
          const msg = (err && err.message) || '领取失败，请重试';
          wx.showToast({ title: msg, icon: 'none', duration: 2500 });
        });
    });
  },

  goBuy() {
    promotionApi.track(this.promotionId, 'click', 'detail').catch(() => {});
    const url = this.data.detail && this.data.detail.purchase_url;
    if (url) {
      wx.navigateTo({ url: `/pages/promotion/detail/webview?url=${encodeURIComponent(url)}` });
    } else {
      wx.showToast({ title: '暂无购买链接', icon: 'none' });
    }
  },

  onShareAppMessage() {
    promotionApi.share(this.promotionId).catch(() => {});
    const d = this.data.detail;
    return {
      title: d ? d.product_name : 'PetAlly 好物推荐',
      path: `/pages/promotion/detail/index?id=${this.promotionId}`,
      imageUrl: d && d.image_url,
    };
  },
});
